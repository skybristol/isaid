from flask import Flask, jsonify, render_template, request, flash, redirect, Markup, url_for, abort, send_file
from functions import *
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import *

def create_app():
    app = Flask(__name__)
    Bootstrap(app)
    return app

app = create_app()
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
            View('Job Title', 'show_facets', category='job title'),
            View('Field of Work', 'show_facets', category='field of work'),
            View('Organizations', 'show_facets', category='organization affiliation'),
            View('Groups', 'show_facets', category='group affiliation'),
            View('Educational Institutions', 'show_facets', category='educational affiliation'),
            View('Funding Organizations', 'show_facets', category='funding organization'),
            View('Work Location', 'show_facets', category='work location'),
            View('Collaborative Affiliations', 'show_facets', category='collaborative affiliation')
        )
    )

nav.init_app(app)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    output_format = requested_format(request.args, default="html")

    person_record = get_person(person_id)

    if output_format == "json":
        return jsonify(person_record)
    else:
        claims_table = pd.DataFrame(person_record["claims"]).to_html(
            header=True,
            index=False,
            na_rep="NA",
            justify="left",
            table_id="claims",
            classes=["table"],
            render_links=True,
            columns=[
                "claim_created",
                "claim_source",
                "reference",
                "date_qualifier",
                "property_label",
                "object_instance_of",
                "object_label",
                "object_identifiers"
            ]
        )

        return render_template("person.html", data=person_record, claims=Markup(claims_table))

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
        facet_results = dict()
        for facet_category,facet_dist in search_results["facetsDistribution"].items():
            facet_results[facet_category] = {k:v for k,v in facet_dist.items() if v > 0 and len(k) > 0}
        json_search_results = {
            "search_results": search_results["hits"],
            "facets_distribution": facet_results
        }
    else:
        json_search_results = search_results["hits"]

    if output_format == "json":
        return jsonify(json_search_results)
    else:
        return render_template("search.html", data=search_results, query=query, filters=filters_criteria, api_url=api_url)

