from flask import Flask, jsonify, render_template, request, flash, redirect, Markup, url_for
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

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
#app.config["SECRET_KEY"] = "SomethingSuperSecret"
#app.config['WTF_CSRF_ENABLED'] = True
db = SQLAlchemy(app)
conn = db.engine.connect().connection

nav = Nav()

@nav.navigation()
def isaid_navbar():
    return Navbar(
        'iSAID',
        View('Home', 'home'),
        View('People', 'people')
    )

nav.init_app(app)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/people")
def people():
    if "format" in request.args:
        output_format = request.args["format"]
    else:
        output_format="html"
    
    search_type=None
    search_term=None

    if "name" in request.args:
        search_type="name"
        search_term=request.args["name"]

    people_records = get_people(search_type=search_type, search_term=search_term)

    if output_format == "html":
        return render_template("people.html", data=people_records)
    else:
        return jsonify(people_records.to_dict(orient='records'))

@app.route("/terms/<term_source>", methods=['GET'])
def terms(term_source):
    return jsonify(lookup_terms(term_type=term_source))

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    query_parameter = lookup_parameter_person(person_id)

    if "format" in request.args:
        output_format = request.args["format"]
    else:
        output_format="html"

    if "collections" in request.args:
        datasets = request.args["collections"].split(",")
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

