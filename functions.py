import os
import validators
import re
from urllib.parse import urlparse
import pandas as pd
import psycopg2
from flask import Markup, Flask, jsonify, render_template, request, abort
from flask_sqlalchemy import SQLAlchemy
import meilisearch
import ast
import hashlib

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
conn = db.engine.connect().connection
people_index = 'entities_people'

search_client = meilisearch.Client(
    os.environ["MEILI_HTTP_ADDR"], 
    os.environ["MEILI_KEY"]
)

facet_categories_people = search_client.get_index(people_index).get_attributes_for_faceting()

isaid_data_collections = {
    "directory": {
        "table_name": "people_with_org_info",
        "title": "Directory/Contact Information",
        "description": "Properties pulled from the ScienceBase Directory for USGS employees and other people",
        "display_properties": [
            "displayname",
            "jobtitle",
            "url",
            "organization_name",
            "organization_url",
            "region",
            "city",
            "state"
        ],
        "display_transpose": True,
        "sort_by": None
    },
    "assets": {
        "table_name": "identified_contacts",
        "title": "Publications and Other Assets",
        "description": "Scientific assets such as publications, datasets, models, instruments, and "
                        "other articles. Linked to people through roles such as author/creator.",
        "display_properties": [
            "additionaltype",
            "contact_type",
            "contact_role",
            "name",
            "datepublished",
            "url"
        ],
        "display_transpose": False,
        "sort_by": "datepublished"
    },
    "claims": {
        "table_name": "identified_claims_m",
        "title": "Statements About a Person",
        "description": "Statements or assertions about a person or asset that characterize the entities in "
                        "various ways, including the connections between entities.",
        "display_properties": [
            "property_label",
            "object_instance_of",
            "object_label",
            "claim_source",
            "claim_created",
            "date_qualifier",
            "reference"
        ],
        "display_transpose": False,
        "sort_by": ["property_label", "object_label"]
    },
    "wikidata_entities": {
        "title": "WikiData Entity",
        "description": "An entity in WikiData representing a person or scientific asset."
    },
    "wikidata_claims": {
        "title": "WikiData Claims",
        "description": "Statements or assertions about a person or other entity in WikiData that characterize "
                        "them in various ways, including the connections between entities."
    }
}

def lookup_parameter_person(person_id):
    if validators.email(person_id):
        query_parameter = "identifier_email"
    else:
        if re.match(r"\d{4}-\d{4}-\d{4}-\d{4}", person_id):
            query_parameter = "identifier_orcid"
        elif re.match(r"Q\d*", person_id):
            query_parameter = "identifier_wikidata"
        else:
            query_parameter = None
    
    return query_parameter

def get_person(criteria):
    query_param = lookup_parameter_person(criteria)

    entity_doc = {
        "criteria": criteria,
        "query parameter": query_param,
        "error": "No results found"
    }

    if query_param == "identifier_email":
        try:
            entity_id = hashlib.sha224(criteria.encode('utf-8')).hexdigest()
            entity_doc = search_client.get_index(people_index).get_document(entity_id)
        except:
            try:
                entity_id = hashlib.md5(criteria.encode('utf-8')).hexdigest()
                entity_doc = search_client.get_index(people_index).get_document(entity_id)
            except:
                pass

    elif query_param == "identifier_orcid":
        results = search_client.get_index('entities_people').search(
            criteria, 
            {'filters': f'identifier_orcid = {criteria}'}
        )

        if len(results["hits"]) == 1:
            entity_doc = results["hits"][0]

    if "error" in entity_doc:
        entity_package = entity_doc
    else:
        entity_package = {
            "entity": entity_doc
        }
        entity_package["entity"]["sources"] = [entity_doc["entity_source"]]

        filters = " OR ".join(
            [
                f'subject_identifier_{k} = "{v}"' for k, v
                in entity_doc["identifiers"].items() if k in ["email","orcid"]
            ]
        )

        r_claims = search_client.get_index('entity_claims').search(
            "",
            {
                'filters': f'{filters}'
            }
        )

        if len(r_claims["hits"]) > 0:
            entity_package["claims"] = r_claims["hits"]

            authored_works = [i for i in r_claims["hits"] if i["property_label"] == "author of"]
            if authored_works: 
                entity_package["authored works"] = list()
                for item in authored_works:
                    work_package = {
                        "title": item["object_label"]
                    }
                    if "object_identifiers" in item and "url" in item["object_identifiers"]:
                        work_package["link"] = item["object_identifiers"]["url"]
                    entity_package["authored works"].append(work_package)

            claim_sources = list(set([i["claim_source"] for i in r_claims["hits"]]))
            if claim_sources:
                entity_package["entity"]["sources"].extend([i for i in claim_sources if i != entity_package["entity"]["entity_source"]])

    return entity_package

def requested_format(args, default="json"):
    if "format" not in args:
        return default
    else:
        if args["format"] not in ["html","json"]:
            abort(400)
        else:
            return args["format"]

def get_facets(categories=facet_categories_people):
    facet_results = search_client.get_index(people_index).search('', {
        'limit': 0,
        'facetsDistribution': categories,
    })

    return facet_results

def search_people(q=str(), facet_filters=None, return_facets=facet_categories_people, response_type="person_docs"):
    if response_type == "facet_frequency":
        search_limit = 0
    else:
        search_limit = 10000

    if facet_filters is None:
        search_results = search_client.get_index(people_index).search(q, {
            "limit": search_limit,
            "facetsDistribution": return_facets
        })
    else:
        search_results = search_client.get_index(people_index).search(q, {
            "limit": search_limit,
            "facetsDistribution": return_facets,
            "facetFilters": facet_filters
        })

    if response_type == "facet_frequency":
        search_response = dict()
        for facet in return_facets:
            search_response[facet] = {k:v for k,v in search_results["facetsDistribution"][facet].items() if v > 0}
    else:
        search_response = search_results

    return search_response

