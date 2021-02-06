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

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    output_format = requested_format(request.args, default="html")

    person_record = get_person(person_id)

    if output_format == "json":
        return jsonify(person_record)
    else:
        if "claims" in person_record:
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
                    "object_label"
                ]
            )
            claims_content = Markup(claims_table)
            references = list(set([i["reference"] for i in person_record["claims"]]))
        else:
            claims_content = None
            references = None

        return render_template("person.html", data=person_record, claims=claims_content, references=references)

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
        return render_template("people_search.html", data=search_results, query=query, filters=filters_criteria, api_url=api_url)

@app.route("/identifiers/<id_type>", methods=["GET"])
def query_identifiers(id_type):
    if id_type == "unresolved_dois":
        return jsonify(claim_identifiers(identifier_type="doi"))
    elif id_type == "unresolved_emails":
        return jsonify(claim_identifiers(identifier_type="email"))
    elif id_type == "unresolved_orcids":
        return jsonify(claim_identifiers(identifier_type="orcid"))
    elif id_type == "unresolved_fbms_code":
        return jsonify(claim_identifiers(identifier_type="fbms_code"))
    elif id_type == "all":
        return jsonify(claim_identifiers())

@app.route("/publication", methods=["GET"])
def publication(identifier):
    output_format = requested_format(request.args, default="json")

    if "doi" in request.args:
        cached_doi = get_pub(request.args["doi"])
        if "error" in cached_doi:
            abort(404)
        else:
            if output_format == "json":
                return cached_doi
            else:
                render_template("publication.html", pub_meta=cached_doi)

@app.route("/doi", methods=["GET"])
def pub():
    output_format = requested_format(request.args, default="json")

    if "doi" not in request.args:
        abort(400)
    else:
        cached_doi = get_pub(request.args["doi"])
        if "error" in cached_doi:
            abort(404)
        else:
            if output_format == "json":
                return cached_doi

@app.route("/claims/<info>", methods=["GET"])
def claims_info(info):
    output_format = requested_format(request.args, default="json")

    if info == "stats":
        claims_facets = get_claims_info()
        if output_format == "json":
            return claims_facets

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

@app.route("/cache/<source>/<identifier>", methods=["GET"])
def cached_source_data(source, identifier):
    if source not in claims_sources.keys():
        abort(500)

    cached_record = get_cached_source(source, identifier)

    if cached_record is None:
        abort(500)

    return jsonify(cached_record)

@app.route("/cache/doi/<identifier_prefix>/<identifier_suffix>", methods=["GET"])
def cached_source_doi(identifier_prefix, identifier_suffix):
    identifier = "/".join([
        identifier_prefix,
        identifier_suffix
    ])

    identifier_string = hashlib.md5(identifier.encode('utf-8')).hexdigest()

    cached_record = get_cached_source("doi", identifier_string)

    if cached_record is None:
        abort(500)

    return jsonify(cached_record)