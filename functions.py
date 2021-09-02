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
from itertools import groupby
import collections
import json
from pylinkedcmd import isaid

search_client = meilisearch.Client(
    os.environ["SEARCH_CLIENT"], 
    os.environ["SEARCH_CLIENT_KEY"]
)

search_index = 'entities_new'

facets = search_client.get_index(search_index).get_attributes_for_faceting()
facets.sort()

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
        "example_value": "https://www.usgs.gov/staff-profiles/david-j-wald",
        "description": "The USGS Staff Profiles system provides individual pages for USGS staff members sharing details about their work. The inventory provides a listing that is scraped to pull together the initial set of information from which profile page links are found."
    },
    "usgs_profiles": {
        "reference": "https://www.usgs.gov/connect/staff-profiles",
        "title": "USGS Profile Pages",
        "source_title": "USGS Profile Page",
        "index": "cache_usgs_profiles",
        "id_prop": "profile",
        "entity_id": "usgs_web_url",
        "example_value": "https://www.usgs.gov/staff-profiles/david-j-wald",
        "description": "The USGS Staff Profiles system provides individual pages for USGS staff members sharing details about their work. Individual profile pages are scraped for expertise terms, links to additional works, and other details."
    },
    "usgs_web_science_centers": {
        "reference": "https://www.usgs.gov/usgs-science-centers",
        "title": "USGS Science Center Listing",
        "source_title": "USGS Science Center Web Page",
        "index": "cache_usgs_science_centers",
        "id_prop": "url",
        "entity_id": "org_id",
        "example_value": "https://www.usgs.gov/centers/asc",
        "description": "The USGS is organized into Science Centers located across the landscape. This cache is from a web scrape of the USGS Science Center listing on the USGS web."
    },
    "usgs_web_science_center_locations": {
        "reference": "https://www.usgs.gov/usgs-science-centers",
        "title": "USGS Science Center Locations",
        "source_title": "USGS Science Center Location",
        "index": "cache_usgs_web_locations",
        "id_prop": "location_name",
        "entity_id": "org_id",
        "example_value": "Juneau Biology Office",
        "description": "This cache comes from the USGS Web listing of facility locations part of a given Science Center. It is used to help show or provide search for where USGS is located on the landscape."
    },
    "usgs_web_science_center_subjects": {
        "reference": "https://www.usgs.gov/usgs-science-centers",
        "title": "USGS Science Center Subjects Addressed",
        "source_title": "USGS Science Center Subject",
        "index": "cache_usgs_web_sc_subjects",
        "id_prop": "subject_link",
        "entity_id": "org_id",
        "example_value": "https://www.usgs.gov/centers/asc/science-topics/birds",
        "description": "This cache comes from the USGS Web site listing of science themes and topics addressed by USGS Science Centers. It is used to help characterize the types of research subjects addressed by USGS"
    },
    "usgs_web_employees": {
        "reference": "https://www.usgs.gov/usgs-science-centers",
        "title": "USGS Science Center Employee Directory",
        "source_title": "USGS Science Center Employee Listing",
        "index": "cache_usgs_web_employees",
        "id_prop": "email",
        "entity_id": "email",
        "example_value": "czimmerman@usgs.gov",
        "description": "This cache contains basic listing of employees as provided by USGS Science Center employee directories. It is used as an additional method of filling in the blanks on who works where in the USGS."
    },
    "sciencebase_people": {
        "reference": "https://www.sciencebase.gov/directory/people",
        "title": "ScienceBase Directory People",
        "source_title": "ScienceBase Directory",
        "index": "cache_sb_people",
        "id_prop": "email",
        "entity_id": "email",
        "example_value": "sbristol@usgs.gov",
        "description": "The ScienceBase Directory provides a conduit to select information from an internal USGS personnel directory along with some records of other people of interest. It is cached to provide an additional source of disambiguating information for people and some properties used in claims."
    },
    "sciencebase_organizations": {
        "reference": "https://www.sciencebase.gov/directory/organizations",
        "title": "ScienceBase Directory Organizations",
        "source_title": "ScienceBase Directory",
        "index": "cache_sb_orgs",
        "id_prop": "id",
        "entity_id": "org_id",
        "example_value": "64239",
        "description": "The ScienceBase Directory provides a conduit to select information on organizational entities that may be of interest in some of our work. It uses only an internal identifier scheme at this point."
    },
}

attributesToRetrieve = [
    'identifier',
    'name',
    'url',
    'email',
    'orcid',
    'USGS Mission Areas',
    'USGS Regions',
    'USGS Science Centers',
    'USGS Science Topics',
    'Science Disciplines',
    'Geologic Time Periods',
    'USGS Institutional Structures',
    'USGS Business Categories',
    'Locations Addressed',
    'USGS Job Titles',
    'Entity Type',
    'Climate Change Terms',
    'description',
    'source',
    'image',
    'active',
    'type',
    'status',
    'year_published',
    'doi'
]


def requested_format(args, default="json"):
    if "format" not in args:
        return default
    else:
        if args["format"] not in ["html","json"]:
            abort(400)
        else:
            return args["format"]

def faceted_search(q=str(), facet_filters=None, return_facets=facets, limit=20, offset=0):
    search_params = {
        'limit': limit,
        'offset': offset,
        'facetsDistribution': return_facets,
        'attributesToRetrieve': attributesToRetrieve
    }

    if len(facet_filters) > 0:
        search_params["facetFilters"] = facet_filters

    search_results = search_client.get_index(search_index).search(
        q,
        search_params
    )

    return search_results

def get_entity(identifier):
    try:
        document = search_client.get_index(search_index).get_document(identifier)
    except Exception as e:
        return

    return {k:v for k,v in document.items() if k in attributesToRetrieve}

def arg_stripper(args, leave_out, output_format="url_params"):
    stripped_args = {k:v for k,v in args.items() if k not in leave_out}
    if output_format == "url_params":
        return "&".join([f"{k}={v}" for k, v in stripped_args.items()])
    else:
        return stripped_args

def doi_in_string(string):
    search = re.search(r"10.\d{4,9}\/[\S]+$", string)
    if search is None:
        return

    return search.group()

