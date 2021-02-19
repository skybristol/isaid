import os
import validators
import re
from urllib.parse import urlparse
import pandas as pd
import psycopg2
from flask import Markup, Flask, jsonify, render_template, request, abort, url_for
from flask_sqlalchemy import SQLAlchemy
import meilisearch
import ast
import hashlib
import requests
from datetime import datetime

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

entity_search_facets = [
        "category",
        "job title",
        "educational affiliation",
        "professional affiliation",
        "employed by",
        "has expertise",
        "addresses subject",
        "published in",
        "funded by",
        "participated in event"
    ]

reference_config = {
    "location": {
        "osm": {
            "title": "Open Street Map Nominatum API",
            "reference": [
                "https://nominatim.org/",
                "https://pypi.org/project/geopy/"
            ],
            "index": "ref_location_osm",
            "identifier_property": "osm_id",
            "label_property": "display_name",
            "query_parameter": "aliases",
        },
        "geonames": {
            "title": "Geonames Geocode Web Service",
            "reference": [
                "http://www.geonames.org/export/geocode.html",
                "https://pypi.org/project/geopy/"
            ],
            "index": "ref_location_geonames",
            "identifier_property": "geonameId",
            "label_property": "name",
            "query_parameter": "aliases",
        },
        "bing": {
            "title": "Bing Maps Locations API",
            "reference": [
                "https://docs.microsoft.com/en-us/bingmaps/rest-services/locations/",
                "https://pypi.org/project/geopy/"
            ],
            "index": "ref_location_bing",
            "identifier_property": "address_hash",
            "label_property": "name",
            "query_parameter": "aliases",
        },
    }
}

claims_sources = {
    "orcid": {
        "reference": "https://orcid.org",
        "title": "Open Researcher and Contributor ID",
        "source_title": "ORCID",
        "index": "cache_orcid",
        "id_prop": "orcid",
        "entity_id": "orcid",
        "example_value": "0000-0003-1682-4031",
        "description": "The ORCID system provides unique persistent identifiers for authors and other contributors to publications and other assets. They are used in the USGS for every person who authors something. The ORCID source provides information about authored works as well as organizational affiliations and other details."
    },
    "doi": {
        "reference": "https://doi.org",
        "title": "Digital Object Identifier",
        "source_title": "DOI",
        "index": "cache_doi",
        "id_prop": "DOI",
        "entity_id": "doi",
        "example_value": "10.5334/dsj-2018-015",
        "description": "The DOI system provides unique persistent identifiers for published articles/reports, datasets, models, and other assets. They are used for USGS reports, articles, datasets, and other scientific assets of importance in assessing the state of science through time."
    },
    "pw": {
        "reference": "https://pubs.usgs.gov",
        "title": "USGS Publications Warehouse",
        "source_title": "Pubs Warehouse",
        "index": "cache_pw",
        "id_prop": "indexId",
        "entity_id": "usgs_pw_index_id",
        "example_value": "ofr20161165",
        "description": "The USGS Publications Warehouse provides a catalog of all USGS authored Series Reports and journal articles published over the course of the institution's history."
    },
    "usgs_profile_inventory": {
        "reference": "https://www.usgs.gov/connect/staff-profiles",
        "title": "USGS Profile Page Inventory",
        "source_title": "USGS Profile Inventory",
        "index": "cache_usgs_profile_inventory",
        "id_prop": "profile",
        "entity_id": "usgs_web_url",
        "example_value": "https://usgs.gov/staff-profiles/layne-adams",
        "description": "The USGS Staff Profiles system provides individual pages for USGS staff members sharing details about their work. The inventory provides a listing that is scraped to pull together the initial set of information from which profile page links are found."
    },
    "usgs_profiles": {
        "reference": "https://www.usgs.gov/connect/staff-profiles",
        "title": "USGS Profile Pages",
        "source_title": "USGS Profile Page",
        "index": "cache_usgs_profiles",
        "id_prop": "profile",
        "entity_id": "usgs_web_url",
        "example_value": "https://usgs.gov/staff-profiles/layne-adams",
        "description": "The USGS Staff Profiles system provides individual pages for USGS staff members sharing details about their work. Individual profile pages are scraped for expertise terms, links to additional works, and other details."
    }
}

def requested_format(args, default="json"):
    if "format" not in args:
        return default
    else:
        if args["format"] not in ["html","json"]:
            abort(400)
        else:
            return args["format"]

def faceted_search(q=str(), facet_filters=None, return_facets=entity_search_facets, limit=20, offset=0):
    search_params = {
        'limit': limit,
        'offset': offset,
        'facetsDistribution': return_facets
    }

    if len(facet_filters) > 0:
        search_params["facetFilters"] = facet_filters

    search_results = search_client.get_index('entities').search(
        q,
        search_params
    )

    return search_results

def entity_identifiers():
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

def arg_stripper(args, leave_out, output_format="url_params"):
    stripped_args = {k:v for k,v in args.items() if k not in leave_out}
    if output_format == "url_params":
        return "&".join([f"{k}={v}" for k, v in stripped_args.items()])
    else:
        return stripped_args

def reference_record(ref_index, ref_id):
    try:
        return search_client.get_index(ref_index).get_document(ref_id)
    except:
        return dict()

def reference_lookup(ref_type, value, expect=1):
    reference_results = list()
    for ref_source, config in reference_config[ref_type].items():
        results = search_client.get_index(config["index"]).search(
            "",
            {
                "facetFilters": [f"{config['query_parameter']}:{value}"]
            }
        )

        for item in results["hits"]:
            item.update({
                "_reference_name": ref_source,
                "_reference_title": config["title"],
                "_date_created": str(datetime.utcnow().isoformat()),
                "_label": item[config["label_property"]],
                "_reference_url": url_for(
                    "reference_data", 
                    ref_type=ref_type, 
                    ref_source=ref_source, 
                    ref_id=item[config["identifier_property"]],
                    _external=True
                )
            })
        reference_results.extend(results["hits"])

    return reference_results

def cached_source_docs():
    documentation = dict()
    for source,docs in claims_sources.items():
        if "example_value" in docs:
            docs["example"] = f"{url_for('cached_source_data', source=source, _external=True)}?id={docs['example_value']}"

        search_result = search_client.get_index(docs['index']).search('', {'limit': 0})
        docs["docs_in_cache"] = search_result['nbHits']

        documentation[source] = docs

    return documentation

def get_cached_source(source, identifier):
    source_record = {
        "_source": claims_sources[source]["title"],
        "_source_reference": claims_sources[source]["reference"],
        "_source_description": claims_sources[source]["description"]
    }

    search_result = search_client.get_index(claims_sources[source]["index"]).search(
        '',
        {
            'filters': f'{claims_sources[source]["id_prop"]} = "{identifier}"',
            'limit': 1
        }
    )

    if len(search_result["hits"]) != 1:
        return None

    source_record.update(search_result["hits"][0])

    return source_record

def claims_by_id(id_value, faceted_identifiers=['email','orcid','usgs_web_url','doi'], return_ids_only=False):
    check_id = actionable_id(id_value, return_resolver=False)

    if check_id is None or list(check_id.keys())[0] not in faceted_identifiers:
        return {"id": id_value, "error": "Not an actionable identifier"}
    
    facet_filters = [
        f"subject_identifier_{list(check_id.keys())[0]}:{list(check_id.values())[0]}",
        f"object_identifier_{list(check_id.keys())[0]}:{list(check_id.values())[0]}",
    ]
    
    preliminary_search_results = search_client.get_index('claims').search(
        '',
        {
            'limit': 1000,
            'facetFilters': [facet_filters],
            'attributesToRetrieve': [
                'subject_identifiers',
                'object_identifiers'
            ]
        }
    )

    if len(preliminary_search_results["hits"]) == 0:
        return {"id": id_value, "error": "No results found for ID"}

    all_identifiers = list()
    for hit in preliminary_search_results["hits"]:
        possible_identifiers = list()
        if "subject_identifiers" in hit and id_value in hit["subject_identifiers"].values():
            for k,v in hit["subject_identifiers"].items():
                if k in faceted_identifiers:
                    possible_identifiers.extend([f"subject_identifier_{k}:{v}",f"object_identifier_{k}:{v}"])
        if "object_identifiers" in hit and id_value in hit["object_identifiers"].values():
            for k,v in hit["object_identifiers"].items():
                if k in faceted_identifiers:
                    possible_identifiers.extend([f"object_identifier_{k}:{v}",f"subject_identifier_{k}:{v}"])
        all_identifiers.extend(possible_identifiers)

    all_identifiers = list(set(all_identifiers))
    
    if return_ids_only:
        return all_identifiers

    better_search_results = search_client.get_index('claims').search(
        '',
        {
            'limit': 10000,
            'facetFilters': [all_identifiers],
            'facetsDistribution': [
                'object_instance_of',
                'subject_instance_of',
                'property_label',
                'claim_source'
            ]
        }
    )

    return better_search_results

def actionable_id(identifier_string, return_resolver=False):
    if validators.url(identifier_string):
        if "/staff-profiles/" in identifier_string.lower():
            return {
                "usgs_web_url": identifier_string
            }

    if validators.email(identifier_string):
        return {
            "email": identifier_string
        }

    identifiers = {
        "doi": {
            "pattern": r"10.\d{4,9}\/[\S]+$",
            "resolver": "https://doi.org/"
        },
        "orcid": {
            "pattern": r"\d{4}-\d{4}-\d{4}-\w{4}",
            "resolver": "https://orcid.org/"
        }
    }
    for k,v in identifiers.items():
        search = re.search(v["pattern"], identifier_string)
        if search:
            d_identifier = {
                k: search.group()
            }
            if return_resolver and v["resolver"] is not None:
                d_identifier["url"] = f"{v['resolver']}{search.group().upper()}"

            return d_identifier

    return

def get_entity(identifier):
    check_id = actionable_id(identifier)

    if check_id is None:
        return

    else:
        facet_filter = f"identifier_{str(next(iter(check_id)))}:{identifier}"

        entity = search_client.get_index('entities').search(identifier, {'facetFilters': [facet_filter]})

        if len(entity["hits"]) == 0:
            return
        
        claims = claims_by_id(identifier)

        return {
            "entity": entity["hits"][0],
            "claims": claims["hits"]
        }