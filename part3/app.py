import os
from flask import Flask, g, render_template, request, redirect, url_for, session
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime
# from werkzeug.security import generate_password_hash, check_password_hash
# chrome://net-internals/#sockets -> To flush socket pools when the flask application stops working



app = Flask(__name__)
app.static_folder = "static"
load_dotenv()
engine = create_engine(os.getenv("DATABASEURI"))
app.secret_key = 'your_secret_key'
# Figure out this app.secret


'''
    Method to connect to database.
'''
def get_db():
    if 'db' not in g:
        print("opened")
        g.db = engine.connect()
    return g.db


'''
    Method to close database connection.
'''
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        print("closed")
        db.close()


@app.route("/")
def index():
    db = get_db()
    cursor = db.execute(text("""
                                SELECT a.author_name, count(at.paper_id), a.author_id FROM paper p
                                LEFT JOIN authored at
                                    ON p.paper_id = at.paper_id
                                LEFT JOIN author a
                                    ON at.author_id = a.author_id
                                GROUP BY(a.author_id, a.author_name)
                             """))
    close_db()
    context = {
        "data": [list(el) for el in cursor]
    }
    return render_template("base.html", **context)


@app.route("/author/<author_id>")
def author_page(author_id):
    db = get_db()
    author_cursor = db.execute(
        text(
            """
                SELECT * 
                FROM author a
                WHERE a.author_id = :author_id
            """
            ), { "author_id": author_id })
    author = [list(el) for el in author_cursor]

    if not author:
        return "Author not found."

    paper_cursor = db.execute(
        text(
            """
                SELECT p.paper_id, p.title,
                    p.date_published, p.url, pb.publication_name,
                    p.abstract
                FROM paper p
                LEFT JOIN publication pb
                    ON p.publication_name = pb.publication_name
                WHERE p.paper_id IN (
                    SELECT paper_id
                    FROM authored a
                    WHERE a.author_id = :author_id
                )
                ORDER BY p.date_published DESC NULLS LAST
            """
        ), { "author_id": author_id }
    )

    affiliations_cursor = db.execute(
        text(
            """
                SELECT i.institution_name
                FROM affiliation a
                LEFT JOIN institution i
                    ON a.institution_id = i.institution_id 
                WHERE a.author_id = :author_id
            """), { "author_id": author_id }
    )
    close_db()
    papers = [list(el) for el in paper_cursor]
    affiliations = [list(el) for el in affiliations_cursor]
    context = {
        "author": author[0],
        "papers": papers,
        "affiliations": affiliations
    }
    return render_template("author.html", **context)

@app.route("/user_collections/<email>")
def user_collections(email):
    if session.get("email") != email:
        return "Unauthorized access."
    db = get_db()
    collections_cursor = db.execute(
        text("""
                SELECT h.collection_name, h.email, h.since, count(i.paper_id) 
                FROM hascollection h
                LEFT JOIN includes i ON
                    h.collection_name = i.collection_name
                    AND h.email = i.email
                WHERE h.email = :email
                GROUP BY h.collection_name, h.email, h.since
             """), 
             {
                "email": email
             }
    )
    close_db()
    collections = [list(el) for el in collections_cursor]
    context = {
        "username": session.get("username"),
        "email": session.get("email"),
        "collections": collections
    }
    return render_template("user_collections.html", **context)

@app.route("/create_collection", methods=["POST"])
def create_collection():
    if session.get("email") != request.form.get("email"):
        return "Unauthorized access."
    db = get_db()
    try:
        db.execute(
            text("""
                    INSERT INTO hascollection (collection_name, email, since)
                    VALUES(:collection_name, :email, :since) RETURNING collection_name
                """),
                {
                    "collection_name": request.form.get("collection_name"),
                    "email": request.form.get("email"),
                    "since": str(datetime.now())[:10]
                }
        )
        db.commit()
        close_db()
        # Redirect to the relevant page, such as the user's collection page
        return redirect(url_for('user_collections', email=request.form.get("email")))
    except Exception:
        close_db()
        return "Failed to create collection."



@app.route("/collections/<email>/<collection_name>")
def collection_page(email, collection_name):
    if session.get("email") != email:
        return "Unauthorized access."
    db = get_db()
    collections_cursor = db.execute(
        text("""
                SELECT * FROM hascollection 
                WHERE email = :email AND collection_name = :collection_name
                ORDER BY since DESC
             """), 
             {
                "email": email,
                "collection_name": collection_name
             }
    )
    collection = [list(el) for el in collections_cursor]
    if not collection:
        close_db()
        return "Collection not found."
    
    collection_papers_cursor = db.execute(
        text(
            """
                SELECT p.paper_id, p.title,
                    p.date_published, p.url, pb.publication_name,
                    p.abstract
                FROM includes i LEFT JOIN paper p
                    ON i.paper_id = p.paper_id
                LEFT JOIN publication pb
                    ON p.publication_name = pb.publication_name
                WHERE i.email = :email AND i.collection_name = :collection_name
                ORDER BY p.date_published DESC NULLS LAST
            """
        ), {
            "email": email,
            "collection_name": collection_name
        }
    )
    collection_papers = [list(el) for el in collection_papers_cursor]
    collection_paper_ids = tuple([el[0] for el in collection_papers])
    if len(collection_paper_ids) == 0:
        context = {
            "email": email,
            "collection_name": collection_name,
            "collection_size": len(collection_papers),
            "collection_papers": collection_papers,
            "since": str(collection[0][2]),
            "from_same_authors_papers": [],
            "cite_collection_papers": [],
            "collection_papers_citations": []
        }
        close_db()
        return render_template("collection.html", **context)
    authors_cursor = db.execute(
        text(
            """
                SELECT DISTINCT(a.author_id)
                FROM authored a
                WHERE a.paper_id IN :paper_ids
            """
        ),
        {
            "paper_ids": collection_paper_ids
        }
    )
    authors = tuple([el[0] for el in authors_cursor])
    from_same_authors_cursor = db.execute(
        text(
            """
                SELECT p.paper_id, p.title,
                    p.date_published, p.url, pb.publication_name,
                    p.abstract
                FROM paper p LEFT JOIN authored a
                    ON a.paper_id = p.paper_id
                LEFT JOIN publication pb
                    ON p.publication_name = pb.publication_name
                WHERE a.author_id IN :authors
                    AND p.paper_id not in :paper_ids
                ORDER BY p.date_published DESC NULLS LAST
            """
        ),
        {
            "authors": authors,
            "paper_ids": collection_paper_ids
        }
    )
    from_same_authors_papers = [list(el) for el in from_same_authors_cursor]

    papers_that_cite_collection_cursor = db.execute(
        text(
            """
                SELECT p.paper_id, p.title,
                    p.date_published, p.url, pb.publication_name,
                    p.abstract
                FROM paper p LEFT JOIN citedby c
                    ON c.paper_citing = p.paper_id
                LEFT JOIN publication pb
                    ON p.publication_name = pb.publication_name
                WHERE c.paper_cited IN :paper_ids
                    AND c.paper_citing NOT IN :paper_ids
                ORDER BY p.date_published DESC NULLS LAST
            """
        ),
        {
            "paper_ids": collection_paper_ids
        }
    )
    cite_collection_papers = [list(el) for el in papers_that_cite_collection_cursor]

    papers_that_collection_cites_cursor = db.execute(
        text(
            """
                SELECT p.paper_id, p.title,
                    p.date_published, p.url, pb.publication_name,
                    p.abstract
                FROM paper p LEFT JOIN citedby c
                    ON c.paper_cited = p.paper_id
                LEFT JOIN publication pb
                    ON p.publication_name = pb.publication_name
                WHERE c.paper_citing IN :paper_ids
                    AND c.paper_cited NOT IN :paper_ids
                ORDER BY p.date_published DESC NULLS LAST
            """
        ),
        {
            "paper_ids": collection_paper_ids
        }
    )
    collection_papers_citations = [list(el) for el in papers_that_collection_cites_cursor]
    context = {
        "email": email,
        "collection_name": collection_name,
        "collection_size": len(collection_papers),
        "collection_papers": collection_papers,
        "since": str(collection[0][2]),
        "from_same_authors_papers": from_same_authors_papers,
        "cite_collection_papers": cite_collection_papers,
        "collection_papers_citations": collection_papers_citations
    }
    close_db()
    return render_template("collection.html", **context)

@app.route("/include/<email>/<collection_name>/<paper_id>")
def include_paper(email, collection_name, paper_id):
    if session.get("email") != email:
        return "Unauthorized access."
    db = get_db()
    try:
        db.execute(
            text(
                """
                    INSERT INTO includes (collection_name, paper_id, email, since)
                    VALUES(:collection_name, :paper_id, :email, :since) RETURNING collection_name
                """
            ),
            {
                "collection_name": collection_name,
                "paper_id": paper_id,
                "email": email,
                "since": str(datetime.now())[:10]
            }
        )
        db.commit()
        close_db()
        return "Paper was added to the collection successfully."
    except Exception:
        close_db()
        return """
                Failed to add paper to collection.
                Paper might already be in the collection.
            """

@app.route("/include", methods=["POST"])
def include_paper_post():
    email = request.form.get("email")
    paper_id = request.form.get("paper_id")
    collection_name = request.form.get("collection_name")
    if session.get("email") != email:
        return "Unauthorized access."
    db = get_db()
    try:
        db.execute(
            text(
                """
                    INSERT INTO includes (collection_name, paper_id, email, since)
                    VALUES(:collection_name, :paper_id, :email, :since) RETURNING collection_name
                """
            ),
            {
                "collection_name": collection_name,
                "paper_id": paper_id,
                "email": email,
                "since": str(datetime.now())[:10]
            }
        )
        db.commit()
        close_db()
        return "Paper was added to the collection successfully."
    except Exception:
        close_db()
        return """
                Failed to add paper to collection.
                Paper might already be in the collection.
            """

def is_authenticated(email, password):
    db = get_db()
    result = db.execute(
        text("SELECT * FROM users WHERE email = :email"),
        {"email": email}
    )
    user = result.fetchone()
    print("FROM AUTH")
    print(user)
    close_db()
    if user:
        print("password is ::", user[2].strip())
        print("password2 is ::", password)
        if user[2].strip()==password.strip():
            return user
    return None



@app.route("/login", methods=["GET", "POST"])
def login():
    error_message = None
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = is_authenticated(email, password)  # Getting the user object
        print("THe user in login")
        print(user)
        if user:
            session["username"] = user[1]  # Assuming 'username' is the user's username field in your database
            # Add any other user info you need to maintain context
            session["email"] = email
            return redirect(url_for("index"))
        else:
            error_message = "Invalid credentials. Please try again."

    return render_template("login.html", error_message=error_message)





@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("index"))




def create_user(email, username, password):
    db = get_db()
    db.execute(
        text("INSERT INTO users (email, username, password_hash) VALUES (:email, :username, :password)"),
        {"email": email, "username": username, "password": password}
    )
    db.commit()
    close_db()



@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
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
            create_user(email, username, password)
            session["username"] = username
            session["email"] = email
            return redirect(url_for("index"))

    return render_template("signup.html", error_message=error_message if "error_message" in locals() else None)



@app.route("/search", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        search_query = request.form.get("search_query")
        db = get_db()
        
        # Search by paper name
        paper_cursor = db.execute(
            text(
                """
                SELECT p.paper_id, p.title,
                    p.date_published, p.url, pb.publication_name,
                    p.abstract
                FROM paper p
                LEFT JOIN publication pb
                    ON p.publication_name = pb.publication_name
                WHERE p.title ILIKE :search_query
                ORDER BY p.date_published DESC NULLS LAST
                """
            ), { "search_query": f"%{search_query}%" }
        )
        papers_by_name = [list(el) for el in paper_cursor]
        
        # Search by author name
        author_cursor = db.execute(
            text(
                """
                SELECT a.author_name, count(at.paper_id), a.author_id FROM paper p
                LEFT JOIN authored at
                    ON p.paper_id = at.paper_id
                LEFT JOIN author a
                    ON at.author_id = a.author_id
                WHERE a.author_name ILIKE :search_query
                GROUP BY(a.author_id, a.author_name)
                """
            ), { "search_query": f"%{search_query}%" }
        )
        authors_by_name = [list(el) for el in author_cursor]
        
        close_db()
        
        context = {
            "search_query": search_query,
            "papers_by_name": papers_by_name,
            "authors_by_name": authors_by_name
        }
        
        return render_template("search_results.html", **context)
    
    return render_template("search.html")





if __name__ == "__main__":
    import click

    @click.command()
    @click.option('--debug', is_flag=True)
    @click.option('--threaded', is_flag=True)
    @click.argument('HOST', default='0.0.0.0')
    @click.argument('PORT', default=8111, type=int)
    def run(debug, threaded, host, port):
        """
            This function handles command line parameters.
            Run the server using:

            python3 server.py

            Show the help text using:

                python3 server.py --help
        """

        HOST, PORT = host, port
        print("running on %s:%d" % (HOST, PORT))
        app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

    run()
