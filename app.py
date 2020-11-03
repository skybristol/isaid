from flask import Flask, jsonify, render_template, request, flash, redirect, Markup, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from functions import *
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import Navbar, View, Subgroup

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
        View('People', 'people'),
        Subgroup(
            'Descriptors',
            View('Expertise', 'terms', claim_type='expertise'),
            View('Job Titles', 'terms', claim_type='job title'),
            View('Organization Affiliation', 'terms', claim_type='organization affiliation')
        )
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

    if "search_type" in request.args and "search_term" in request.args:
        search_type=request.args["search_type"]
        search_term=request.args["search_term"]

    people_records = get_people(search_type=search_type, search_term=search_term)

    if output_format == "html":
        return render_template("people.html", data=people_records, search_type=search_type, search_term=search_term)
    else:
        return jsonify(people_records.to_dict(orient='records'))

@app.route("/claims/<claim_type>", methods=['GET'])
def terms(claim_type):
    output_format = requested_format(request.args, default="html")

    df = lookup_terms(claim_type)

    if output_format == "json":
        d_results = df.to_dict(orient="records")
        return jsonify(data=d_results)
    else:
        return render_template("claims.html", data=df, claim_type=claim_type)

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    output_format = requested_format(request.args, default="html")

    query_parameter = lookup_parameter_person(person_id)

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

