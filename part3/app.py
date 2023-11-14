import os
from flask import Flask, g, render_template, request, redirect, url_for, session
from sqlalchemy import create_engine, text
from dotenv import load_dotenv


app = Flask(__name__)
app.static_folder = "static"
load_dotenv()
engine = create_engine(os.getenv("DATABASEURI"))


'''
    Method to connect to database.
'''
def get_db():
    if 'db' not in g:
        g.db = engine.connect()
    return g.db


'''
    Method to close database connection.
'''
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


@app.route("/")
def index():
    db = get_db()
    cursor = db.execute(text("SELECT * FROM author"))
    close_db()
    context = {
        "data": [ list(el) for el in cursor ]
    }
    return render_template("base.html", **context)


@app.route("/author/<author_id>")
def author_page(author_id):
    db = get_db()
    author_cursor = db.execute(
        text(
            f"""
                SELECT * 
                FROM author a
                WHERE a.author_id = '{ author_id }'
            """
            ))
    author = [list(el) for el in author_cursor]

    if not author:
        return "Author not found."
    
    paper_cursor = db.execute(
        text(
            f"""
                SELECT p.paper_id, p.title,
                    p.date_published, p.url, pb.publication_name,
                    p.abstract
                FROM paper p
                LEFT JOIN publication pb
                    ON p.publication_name = pb.publication_name
                WHERE p.paper_id IN (
                    SELECT paper_id
                    FROM authored a
                    WHERE a.author_id = '{ author_id }'
                )
            """
        )
    )

    affiliations_cursor = db.execute(
        text(
            f"""
                SELECT i.institution_name
                FROM affiliation a
                LEFT JOIN institution i
                    ON a.institution_id = i.institution_id 
                WHERE a.author_id = '{ author_id }'
            """
        )
    )
    close_db()
    papers = [list(el) for el in paper_cursor]
    affiliations = [list(el) for el in affiliations_cursor]
    print(affiliations)
    context = {
        "author": author[0],
        "papers": papers,
        "affiliations": affiliations
    }
    return render_template("author.html", **context)



def is_authenticated(username, password):
    # Implement your authentication logic here
    # For simplicity, let's assume you have a table 'users' with columns 'username' and 'password'
    db = get_db()
    result = db.execute(
        text("SELECT * FROM users WHERE username = :username AND password = :password"),
        {"username": username, "password": password}
    )
    user = result.fetchone()
    db.close()
    return user is not None



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if is_authenticated(username, password):
            session["username"] = username
            return redirect(url_for("index"))
        else:
            error_message = "Invalid credentials. Please try again."

    return render_template("login.html", error_message=error_message if "error_message" in locals() else None)


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("index"))



def create_user(username, password):
    # Implement your user creation logic here
    db = get_db()
    db.execute(
        text("INSERT INTO users (username, password) VALUES (:username, :password)"),
        {"username": username, "password": password}
    )
    db.commit()
    db.close()


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Check if the username already exists
        db = get_db()
        result = db.execute(
            text("SELECT * FROM users WHERE username = :username"),
            {"username": username}
        )
        existing_user = result.fetchone()

        if existing_user:
            error_message = "Username already exists. Please choose a different one."
        else:
            create_user(username, password)
            session["username"] = username
            return redirect(url_for("index"))

    return render_template("signup.html", error_message=error_message if "error_message" in locals() else None)

