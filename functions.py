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
import requests

people_index = 'entities'
pubs_index = 'entities'
claims_index = 'entity_claims'
GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

search_client = meilisearch.Client(
    os.environ["MEILI_HTTP_ADDR"], 
    os.environ["MEILI_KEY"]
)

facet_categories_people = search_client.get_index(people_index).get_attributes_for_faceting()

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

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
    unique_facet_terms = get_facets(unique_terms=True)

    query_param = lookup_parameter_person(criteria)

    entity_doc = {
        "criteria": criteria,
        "query parameter": query_param,
        "error": "No results found"
    }

    if query_param == "identifier_email":
        try:
            entity_id = hashlib.md5(criteria.encode('utf-8')).hexdigest()
            entity_doc = search_client.get_index(people_index).get_document(entity_id)
        except:
            entity_doc = None

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

        entity_package["person_unique_terms"] = dict()
        for facet in unique_facet_terms.keys():
            if facet in entity_doc and next((i for i in entity_doc[facet] if i in unique_facet_terms[facet]), None) is not None:
                entity_package["person_unique_terms"][facet] = [i for i in entity_doc[facet] if i in unique_facet_terms[facet]]

        filters = " OR ".join(
            [
                f'subject_identifier_{k} = "{v}"' for k, v
                in entity_doc["identifiers"].items() if k in ["email","orcid"]
            ]
        )

        r_claims = search_client.get_index('entity_claims').search(
            "",
            {
                'limit': 1000,
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
                    if "object_identifiers" in item and item["object_identifiers"] is not None and "url" in item["object_identifiers"]:
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

def get_facets(categories=facet_categories_people, unique_terms=False):
    facet_results = search_client.get_index(people_index).search('', {
        'limit': 0,
        'facetsDistribution': categories,
    })

    if unique_terms:
        unique_facet_values = dict()
        for k, v in facet_results["facetsDistribution"].items():
            unique_facet_values[k] = [facet for facet, count in v.items() if count == 1]
        return unique_facet_values

    return facet_results

def search_people(q=str(), facet_filters=None, return_facets=facet_categories_people, response_type="person_docs"):
    if response_type == "facet_frequency":
        search_limit = 0
    else:
        search_limit = 10000

    facet_filters_list = ["instance_of:Person"]

    if facet_filters is not None:
        facet_filters_list = facet_filters_list + facet_filters

    search_results = search_client.get_index(people_index).search(q, {
        "limit": search_limit,
        "facetsDistribution": return_facets,
        "facetFilters": facet_filters_list
    })

    if response_type == "facet_frequency":
        search_response = dict()
        for facet in return_facets:
            search_response[facet] = {k:v for k,v in search_results["facetsDistribution"][facet].items() if v > 0}
    else:
        search_response = search_results

    return search_response

def entity_identifiers():
    offset=0
    identifiers = list()
    entities = search_client.get_index('entities').get_documents(
        {
            "limit": 500000,
            "attributesToRetrieve": "identifier_orcid,identifier_email,identifier_sbid,identifier_doi,identifier_fbms_code,identifier_url"
        }
    )
    for entity in entities:
        identifiers.extend([v for k,v in entity.items()])
    
    return identifiers

def claim_identifiers(unresolved=True, identifier_type="all"):
    id_facet_results = search_client.get_index('entity_claims').search(
        "", 
        {
            "limit": 0, 
            "facetsDistribution": [
                "subject_identifier_orcid",
                "subject_identifier_email",
                "subject_identifier_sbid",
                "object_identifier_doi",
                "object_identifier_fbms_code",
                "object_identifier_url"
            ]
        }
    )
    
    if unresolved:
        entity_ids = entity_identifiers()
    
    id_listing = dict()

    for id_type,identifiers in id_facet_results["facetsDistribution"].items():
        id_position = id_type.split("_")[0]
        id_name = id_type.split("_")[-1]
        id_list = list(identifiers.keys())

        if id_position not in id_listing:
            id_listing[id_position] = dict()
        if unresolved:
            id_listing[id_position][id_name] = [i for i in id_list if i not in entity_ids]
        else:
            id_listing[id_position][id_name] = id_list
            
    if identifier_type != "all":
        filtered_ids = list()
        for id_position, id_types in id_listing.items():
            for id_type, ids in id_types.items():
                if id_type == identifier_type:
                    filtered_ids.extend(ids)
        id_listing = list(set(filtered_ids))
            
    
    return id_listing

def get_pub(doi):
    results = search_client.get_index(pubs_index).search(
        doi,
        {
            'filters': f'identifier_doi = "{doi}"'
        }
    )
    if len(results["hits"]) == 1:
        return results["hits"][0]
    elif len(results["hits"]) > 1:
        return {
            "doi": doi,
            "error": "More than one result returned for a single DOI. Something's wrong in the database."
        }
    else:
        return {
            "doi": doi,
            "error": "No results found in cache."
        }

def get_claims_info():
    claims_facets = search_client.get_index('entity_claims').search(
        "", 
        {
            "limit": 0, "facetsDistribution": ["*"]
        }
    )
    return claims_facets["facetsDistribution"]
