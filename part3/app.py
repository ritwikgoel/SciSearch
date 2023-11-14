import os
from flask import Flask, g, render_template
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
