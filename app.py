from flask import (
    Flask, 
    jsonify, 
    render_template, 
    request, 
    flash, 
    redirect, 
    Markup, 
    url_for, 
    abort, 
    send_file,
    escape
)
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import *
import hashlib

from functions import *

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
        View('Search', 'search_entities'),
    )

nav.init_app(app)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/search", methods=['GET'])
def search_entities():
    output_format = requested_format(request.args, default="html")

    query_string = str()
    facet_filters = list()
    
    for arg in request.args:
        if arg == "q":
            query_string = escape(request.args["q"])
        elif arg in facets:
            for item in request.args.getlist(arg):
                facet_filters.append(f"{arg}:{item}")
            
    limit = 20
    if "limit" in request.args:
        if request.args["limit"].isnumeric():
            limit = int(request.args["limit"])

    offset = 0
    if "offset" in request.args:
        if request.args["offset"].isnumeric():
            offset = int(request.args["offset"])
    
    search_results = faceted_search(
        q=query_string,
        facet_filters=facet_filters,
        limit=limit,
        offset=offset
    )

    if "facetsDistribution" in search_results:
        facets_in_search = [i for i in facets if i in search_results["facetsDistribution"].keys()]

        sorted_facets = dict()
        for facet, distribution in search_results["facetsDistribution"].items():
            sorted_facets[facet] = dict()
            for item in sorted(distribution, key=str.lower):
                if int(search_results["facetsDistribution"][facet][item]) > 0:
                    sorted_facets[facet][item] = search_results["facetsDistribution"][facet][item]
    else:
        facets_in_search = None
        sorted_facets = None

    previous_link = None
    if offset > 0:
        previous_offset = offset - limit
        previous_link = f"{url_for('search_entities')}?{arg_stripper(request.args, ['offset'])}&offset={previous_offset}"

    next_link = None
    next_offset = offset + limit
    if next_offset < search_results["nbHits"]:
        next_link = f"{url_for('search_entities')}?{arg_stripper(request.args, ['offset'])}&offset={next_offset}"

    base_url = f"{url_for('search_entities')}?{arg_stripper(request.args, ['offset'])}"
    base_url_no_q = f"{url_for('search_entities')}?{arg_stripper(request.args, ['q'])}"

    if output_format == "json":
        return jsonify(search_results)
    else:
        return render_template(
            "search.html", 
            search_results=search_results, 
            facets_in_search=facets_in_search, 
            sorted_facets=sorted_facets, 
            facet_filters=facet_filters,
            offset=offset,
            next_link=next_link,
            previous_link=previous_link,
            base_url=base_url,
            base_url_no_q=base_url_no_q
        )


