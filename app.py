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
#        View('People', 'show_people'),
#        Subgroup(
#            'Facets',
#            View('Expertise', 'show_facets', category='expertise'),
#            View('Job Title', 'show_facets', category='job title'),
#            View('Field of Work', 'show_facets', category='field of work'),
#            View('Organizations', 'show_facets', category='organization affiliation'),
#            View('Groups', 'show_facets', category='group affiliation'),
#            View('Educational Institutions', 'show_facets', category='educational affiliation'),
#            View('Funding Organizations', 'show_facets', category='funding organization'),
#            View('Work Location', 'show_facets', category='work location'),
#            View('Collaborative Affiliations', 'show_facets', category='collaborative affiliation')
#        )
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
        elif arg in entity_search_facets:
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
        facets_in_search = [i for i in entity_search_facets if i in search_results["facetsDistribution"].keys()]

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

@app.route("/entity", methods=['GET'])
def lookup_entity():
    if "id" not in request.args:
        abort(500)

    output_format = requested_format(request.args, default="html")

    entity = get_entity(request.args["id"])

    if entity is None:
        abort(404)

    if output_format == "json":
        return jsonify(entity)
    else:
        if entity["entity"]["category"] == "person":
            authored_works = list()
            for work in [i for i in entity["claims"] if i["property_label"] == "author of"]:
                d_work = {
                    "title": work["object_label"]
                }
                if "object_identifier_doi" in work:
                    d_work["url"] = f"https://doi.org/{work['object_identifier_doi']}"
                authored_works.append(d_work)

            if authored_works:
                entity["authored_works"] = authored_works

            edited_works = list()
            for work in [i for i in entity["claims"] if i["property_label"] == "editor of"]:
                d_work = {
                    "title": work["object_label"]
                }
                if "object_identifier_doi" in work:
                    d_work["url"] = f"https://doi.org/{work['object_identifier_doi']}"
                edited_works.append(d_work)

            if edited_works:
                entity["edited_works"] = edited_works

        claims_table = pd.DataFrame(entity["claims"]).to_html(
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
                "object_label"
            ]
        )
        claims_content = Markup(claims_table)

        cached_source_links = list()
        for source_title in entity["entity"]["sources"]:
            cache_source = next(({k:v} for k, v in claims_sources.items() if v["source_title"] == source_title), None)
            if cache_source is not None:
                source_name = list(cache_source.keys())[0]
                entity_id_prop = cache_source[source_name]["entity_id"]
                if entity_id_prop in entity["entity"]["identifiers"]:
                    cached_source_links.append({
                        "name": source_name,
                        "link": url_for(
                            "cached_source_data", 
                            source=source_name, 
                            id=entity["entity"]["identifiers"][entity_id_prop],
                            _external=True
                        )
                    })
        return render_template("entity.html", data=entity, claims=claims_content, cached_source_links=cached_source_links)

@app.route("/identifiers/<identifier_source>/<id_type>", methods=["GET"])
def query_identifiers(identifier_source, id_type):
    if identifier_source not in ["claims","entities"]:
        abort(404)

    if id_type not in ["all","email","orcid","doi"]:
        abort(404)
    
    if identifier_source == "entities":
        identifiers = entity_identifiers(identifier_type=id_type)
    else:
        if "unresolved" in request.args:
            unresolved = request.args["unresolved"]
        else:
            unresolved = False
        identifiers = claim_identifiers(identifier_type=id_type, unresolved=unresolved)

    if identifiers is None:
        abort(500)

    return jsonify(identifiers)

@app.route("/reference/<ref_type>/<ref_source>/<ref_id>", methods=["GET"])
def reference_data(ref_type, ref_source, ref_id):
    index_name = f"ref_{ref_type}_{ref_source}"
    return jsonify(reference_record(index_name, ref_id))

@app.route("/reference/lookup/<ref_type>", methods=["GET"])
def reference_search(ref_type):
    if "q" not in request.args:
        abort(500)
    
    results = reference_lookup(ref_type, request.args["q"])

    return jsonify(results)

@app.route('/cache', methods=["GET"])
def cache_route_doc():
    return jsonify(cached_source_docs())

@app.route("/cache/<source>", methods=["GET"])
def cached_source_data(source):
    if source not in claims_sources.keys():
        abort(500)

    if "id" not in request.args:
        abort(500)

    cached_record = get_cached_source(source, request.args["id"])

    if cached_record is None:
        abort(404)

    return jsonify(cached_record)

@app.route("/source_data", methods=["GET"])
def data_source_route_doc():
    return jsonify(get_source_data("data_sources"))

@app.route("/source_data/<source>", methods=["GET"])
def source_data(source):
    limit = 1000
    offset = 0
    if "limit" in request.args:
        limit = request.args["limit"]

    if "offset" in request.args:
        offset = request.args["offset"]

    source_data = get_source_data(source, limit=limit, offset=offset)

    return jsonify(source_data)

@app.route("/entity_claims")
def entity_claims():
    if "id" not in request.args:
        abort(500)

    entity_results = claims_by_id(request.args["id"])

    return jsonify(entity_results)
