from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from functions import *
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import Navbar, View

def create_app():
    app = Flask(__name__)
    Bootstrap(app)

    return app

app = create_app()

DB_URL = os.getenv("DATABASE_URL").replace("postgresql:", "postgresql+psycopg2:")
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
conn = db.engine.connect().connection

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/people")
def people():
    return jsonify(get_people(db_con=conn))

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    query_parameter = lookup_parameter_person(person_id)

    args = request.args

    if "format" in args:
        output_format = args["format"]
    else:
        output_format="html"

    if "collections" in args:
        datasets = args["collections"].split(",")
    else:
        datasets = ["directory", "assets", "claims"]

    if output_format == "json":
        person_content = dict()
        for data_section in datasets:
            person_content[data_section] = package_json(
                collection=data_section,
                query_param=query_parameter,
                query_param_value=person_id,
                db_con=conn
            )
        
        return jsonify(person_content)

    else:
        person_content = str()
        for data_section in datasets:
            person_content = person_content + package_html(
                collection=data_section,
                query_param=query_parameter,
                query_param_value=person_id,
                base_url=request.base_url,
                db_con=conn
            )

        return render_template("person.html", html_content=person_content)

nav = Nav()

@nav.navigation()
def isaid_navbar():
    return Navbar(
        'iSAID',
        View('Home', 'home'),
        View('People', 'people')
    )

nav.init_app(app)