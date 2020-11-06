from flask import Flask, jsonify, render_template, request, flash, redirect, Markup, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from functions import *
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import *

def create_app():
    app = Flask(__name__)
    Bootstrap(app)

    return app

app = create_app()

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
conn = db.engine.connect().connection

nav = Nav()

@nav.navigation()
def isaid_navbar():
    return Navbar(
        'iSAID',
        View('Home', 'home'),
        View('People', 'show_people'),
        Subgroup(
            'Facets',
            View('Expertise', 'show_facets', category='expertise'),
            View('Job Titles', 'show_facets', category='jobtitle'),
            View('Fields of Work', 'show_facets', category='fields_of_work'),
            View('Organizations', 'show_facets', category='organization_name'),
            View('Raw Topics from Data/Models', 'show_facets', category='raw_topics')
        )
    )

nav.init_app(app)

@app.route("/")
def home():
    return render_template("home.html")

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

@app.route("/events", methods=['GET'])
def lookup_events():
    output_format = requested_format(request.args, default="json")
    df_events = get_events()

    if output_format == "json":
        return jsonify(df_events.to_dict(orient="records"))
    else:
        return render_template("events.html", data=df_events)

@app.route("/facets", defaults={"category": None}, methods=["GET"])
@app.route("/facets/<category>", methods=["GET"])
def show_facets(category):
    output_format = requested_format(request.args, default="html")

    if category is None:
        facet_data = get_facets()
    else:
        facet_data = get_facets(categories=[category])

    if output_format == "json":
        return jsonify(facet_data)
    else:
        return render_template("facets.html", data=facet_data, category=category)

@app.route("/people", methods=["GET"])
def show_people():
    output_format = requested_format(request.args, default="html")
    api_url = "/people?format=json"

    if "q" in request.args:
        query = request.args["q"]
        api_url += f"&q={query}"
    else:
        query = str()

    if "filters" in request.args:
        filters_criteria = request.args["filters"].split(",")
        api_url += f"&filters={request.args['filters']}"
        search_results = search_people(query, facet_filters=filters_criteria)
    else:
        filters_criteria = None
        search_results = search_people(query)

    if "include_facets" in request.args:
        json_search_results = search_results
    else:
        json_search_results = search_results["hits"]

    if output_format == "json":
        return jsonify(json_search_results)
    else:
        return render_template("search.html", data=search_results, query=query, filters=filters_criteria, api_url=api_url)
