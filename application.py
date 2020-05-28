import os
import requests, json

from flask import Flask, session, flash, redirect, render_template, request, jsonify
from flask_session import Session

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required


app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config['SECRET_KEY'] = 'you-will-never-guess'
app.debug = True
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
    """ App main page"""

    if "user_id" in session:
        return render_template("search.html")
    else:
        return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """ Register user """

    session.clear()

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Must provide password")

        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("Must confirm password")

        # Ensure password matches the confirmation
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Password doesn't match")

        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))

        # Try to add new user to database. If adding isn't successful, return apology
        try:
            new_user = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)",
                            {"username": username, "hash": hash})

            db.commit()

        except:
            return apology("This username already exists")
            return redirect("/register")

        flash("Registration is successful!")

        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """ Log user in """

    username = request.form.get("username")

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
           return apology("Must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Must provide password")

        # Check if the user exists in database and if the password matches
        user = db.execute("SELECT * from users WHERE username = :username", 
                            {"username": username}).fetchone()

        if not user:
            return apology("This user doesn't exist")

        if not check_password_hash(user[2], request.form.get('password')):
            return apology("The password doesn't match")

        flash("Welcome back!")

        #Create session
        session["user_id"] = user[0]
        session["user_name"] = user[1]

        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """ Log the user out """

    session.clear()

    return redirect("/")


@app.route("/search", methods = ["GET", "POST"])
@login_required
def search():
    """ Search books """

    if request.method == "POST":

        # Ensure query is submitted
        if not request.form.get("query"):
           return apology("Query must be provided")
        
        query = request.form.get("query")

        books = db.execute("SELECT isbn, title, author, year FROM books WHERE \
                        isbn iLIKE :query OR \
                        title iLIKE :query OR \
                        author iLIKE :query",
                        {"query": '%' + query + '%'}).fetchall()
        
        if len(books) == 0:
            return apology("Nothing found")

        return render_template("results.html", books=books, search_count = len(books))
    
    else:
        return redirect("/")
    
   
@app.route("/book/<isbn>", methods = ["GET", "POST"])
@login_required
def show_book(isbn):

    """ Get book details and reviews"""

    res = db.execute("SELECT book_id FROM books WHERE isbn = :isbn",{"isbn": isbn}).fetchone()

    book_id = res[0]

    # Show book details and reviews
    if request.method == "GET":

        book = db.execute("SELECT title, isbn, author, year FROM books WHERE \
                            isbn = :isbn", {"isbn": isbn}).fetchone()

        """ Get info from Goodreads """

        response = requests.get("https://www.goodreads.com/book/review_counts.json",
                             params={"key": 'y1qzRUCeXftKF0FYrWT1qg', "isbns": isbn}).json()

        book_goodreads = response['books'][0]

        """ Get reviews """

        reviews = db.execute("SELECT users.username, reviews.review, reviews.rating FROM \
                             users JOIN reviews on users.user_id = reviews.user_id \
                                 WHERE isbn = :isbn",
                                {"isbn" : isbn}).fetchall()

        
        return render_template("book.html", book=book, book_goodreads=book_goodreads, reviews=reviews)

    # Add a review
    elif request.method == "POST":

        current_user = session["user_id"]

        row = db.execute("SELECT * FROM reviews WHERE user_id = :user_id \
                            AND isbn = :isbn",
                            {"user_id" : current_user,
                            "isbn": isbn}).fetchall()

        if len(row) > 0:
            return apology("Only one review per book!")

        rating = int(request.form.get("rating"))
        text = request.form.get("review")

        db.execute("INSERT INTO reviews (user_id, book_id, isbn, review, rating) \
                    VALUES (:user_id, :book_id, :isbn, :review, :rating)", 
                    {"user_id" : current_user,
                    "book_id": book_id,
                    "isbn": isbn,
                    "review": text,
                    "rating": rating})

        db.commit()

        flash("Thank you for the review!")

        return redirect("/book/" + isbn)


@app.route("/api/<isbn>", methods=["GET", "POST"])
@login_required
def use_api(isbn):

    """ Get book info """

    row = db.execute("SELECT b.title, b.author, b.year, \
                    b.isbn, COUNT(r.review) as review_count, \
                    AVG(r.rating) as average_rating \
                    FROM books b LEFT JOIN reviews r \
                    on b.isbn = r.isbn WHERE b.isbn = :isbn \
                    GROUP BY b.title, b.author, b.year, b.isbn",
                     {"isbn": isbn}).fetchone()

    if not row:
        return apology("There is no book with such ISBN in our database", code=404)

    res = dict(row.items())

    if res['average_rating']:
        res['average_rating'] = float('{:.2f}'.format(res['average_rating']))
    else:
        res['average_rating'] = None

    return jsonify(res)

