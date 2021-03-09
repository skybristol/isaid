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
        "usgs_organizational_units",
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

def entity_identifiers(identifier_type="all"):
    entity_facets = search_client.get_index('entities').get_attributes_for_faceting()
    identifier_facets = [i for i in entity_facets if "identifier_" in i]

    if identifier_type == "all":
        facets_distribution = identifier_facets
    else:
        facets_distribution = [i for i in identifier_facets if i.split("_")[-1] == identifier_type]

    if len(facets_distribution) == 0:
        return

    results = search_client.get_index('entities').search(
        '',
        {
            "limit": 0,
            "facetsDistribution": facets_distribution
        }
    )

    identifiers = dict()
    for k, v in results["facetsDistribution"].items():
        identifiers[k] = list(v.keys())

    return identifiers

def claim_identifiers(identifier_type="all", unresolved=True):
    claim_facets = search_client.get_index('claims').get_attributes_for_faceting()
    identifier_facets = [i for i in claim_facets if "_identifier_" in i]

    if identifier_type == "all":
        facets_distribution = identifier_facets
    else:
        facets_distribution = [i for i in identifier_facets if i.split("_")[-1] == identifier_type]

    if len(facets_distribution) == 0:
        return

    results = search_client.get_index('claims').search(
        "", 
        {
            "limit": 0, 
            "facetsDistribution": facets_distribution
        }
    )
    
    if unresolved:
        entity_ids = entity_identifiers()
        all_resolved_ids = list()
        for identifiers in entity_ids.values():
            all_resolved_ids.extend(identifiers)
    
    identifiers = dict()
    for k, v in results["facetsDistribution"].items():
        if unresolved:
            identifiers[k] = [i for i in list(v.keys()) if i not in all_resolved_ids]
        else:
            identifiers[k] = list(v.keys())
            
    return identifiers

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

def source_a_recordset(recordset, source_meta):
    infusion_meta = {f"_source_{k}":v for k,v in source_meta.items() if k in ["source_id","name","reference"]}

    for record in recordset:
        record.update(infusion_meta)

    return recordset

def get_source_data(source, limit=1000, offset=0):
    data_sources = json.load(open('data_sources.json', 'r'))
    source_meta = next((i for i in data_sources if i["source_id"] == source), None)
    if source_meta is None:
        return data_sources

    if source == "usgs_profiles":
        recordset = package_source_usgs_profiles(limit, offset)

        return source_a_recordset(recordset, source_meta)

    elif source == "mission_areas":
        recordset = source_meta["data_source"]

        return source_a_recordset(recordset, source_meta)
    
    elif source == "sipp_centers":
        recordset = package_source_sipp_centers(source_meta["lookup_values"])

        return source_a_recordset(recordset, source_meta)

    elif source == "sb_people":
        recordset = package_source_sciencebase_directory_people(limit, offset)

        return source_a_recordset(recordset, source_meta)
    
    elif source == "orcid":
        recordset = package_source_orcid_records(limit, offset)

        return source_a_recordset(recordset, source_meta)

    elif source == "doi":
        recordset = package_source_doi_records(source_meta, limit, offset)

        return source_a_recordset(recordset, source_meta)


def sb_location(sb_doc):
    if "primaryLocation" not in sb_doc:
        return
    
    location_record = dict()

    if sb_doc["primaryLocation"]["building"] is not None:
        location_record["name"] = sb_doc["primaryLocation"]["building"]
    else:
        location_name_parts = [
            sb_doc["primaryLocation"]["streetAddress"]["line1"],
            sb_doc["primaryLocation"]["streetAddress"]["city"],
            sb_doc["primaryLocation"]["streetAddress"]["state"],
        ]
        location_record["name"] = ", ".join([i for i in location_name_parts if i is not None])

    if "name" not in location_record or len(location_record["name"]) == 0:
        return

    if sb_doc["primaryLocation"]["buildingCode"] is not None:
        location_record["buildingCode"] = sb_doc["primaryLocation"]["buildingCode"]
        
    location_record["address"] = sb_doc["primaryLocation"]["streetAddress"]["line1"]
    location_record["city"] = sb_doc["primaryLocation"]["streetAddress"]["city"]
    location_record["state"] = sb_doc["primaryLocation"]["streetAddress"]["state"]
    location_record["zip"] = sb_doc["primaryLocation"]["streetAddress"]["zip"]
    
    return location_record

def doi_in_string(string):
    search = re.search(r"10.\d{4,9}\/[\S]+$", string)
    if search is None:
        return

    return search.group()

def package_source_usgs_profiles(limit, offset):
    profile_inventory = search_client.get_index('cache_usgs_profile_inventory').search('', {'limit': 10000, 'attributesToRetrieve': ['profile','title']})['hits']
    staff_profiles = search_client.get_index('cache_usgs_profiles').get_documents({'limit': limit, 'offset': offset})

    identified_profiles = [i for i in staff_profiles if i["email"] is not None or i["orcid"] is not None]
    identified_profiles.sort(key=lambda x:x['email'])
    most_likely_profile = dict()
    for k,v in groupby(identified_profiles,key=lambda x:x['email']):
        profiles = list([(i["profile"],i["content_size"]) for i in v])
        if len(profiles) > 1:
            most_likely_profile[k] = sorted(profiles,key=lambda x:(-x[1],x[0]))[0][0]

    for person in identified_profiles:
        inventory_person = next((i for i in profile_inventory if i["profile"] == person["profile"]), None)
        person.update({"title": inventory_person["title"]})

    ignore_emails = [
        None,
        "ask@usgs.gov",
        'usgs_yes@usgs.gov',
        'astro_outreach@usgs.gov',
        'gs-w-txpublicinfo@usgs.gov',
        'library@usgs.gov'
    ]
    unique_emails = list(set([i["email"] for i in staff_profiles if i["email"] not in ignore_emails]))
    unique_emails.sort()

    unique_identified_profiles = list()
    for email in unique_emails:
        if email in most_likely_profile.keys():
            unique_identified_profiles.append(next(i for i in identified_profiles if i["profile"] == most_likely_profile[email]))
        else:
            unique_identified_profiles.append(next(i for i in staff_profiles if i["email"] == email))

    duplicate_orcids = [item for item, count in collections.Counter([i["orcid"] for i in unique_identified_profiles if i["orcid"] is not None]).items() if count > 1]
    for profile in [i for i in unique_identified_profiles if i["orcid"] in duplicate_orcids]:
        profile.update({"orcid": None})

    for profile in [p for p in unique_identified_profiles if p["profile_image_url"] is not None and "placeholder-profile" in p["profile_image_url"]]:
        profile.update({"profile_image_url": None})

    for profile in [p for p in unique_identified_profiles if p["body_content_links"] is not None]:
        for link in profile["body_content_links"]:
            link.update({"doi": doi_in_string(link["link_href"])})

    return unique_identified_profiles

def package_source_sipp_centers(sipp_labels):
        sipp_center_records = search_client.get_index('cache_sipp_usgs_centers').get_documents({'limit': 500})

        for center in sipp_center_records:
            update = {
                "MissionAreaName": None,
                "Region": None
            }
            if center["MissionArea"] not in ["REG","ADMIN","DO"]:
                update["MissionAreaName"] = sipp_labels["MissionArea"][center["MissionArea"]]

            if center["RegionCode"] != "HQ":
                update["Region"] = sipp_labels["RegionCode"][center["RegionCode"]]
            center.update(update)

        return sipp_center_records

def package_source_sciencebase_directory_people(limit, offset):
    sb_people = search_client.get_index('cache_sb_people').get_documents({'limit': limit, 'offset': offset})
    sb_orgs = search_client.get_index('cache_sb_orgs').get_documents({'limit': 10000})

    summarized_people = list()
    for person in [p for p in sb_people if p["email"] is not None]:
        summarized_person = {
            "uri": person["link"]["href"],
            "_date_cached": person["_date_cached"],
            "firstName": None,
            "middleName": None,
            "lastName": person["lastName"],
            "displayName": person["displayName"],
            "email": person["email"],
            "jobTitle": None,
            "organization": None,
            "fbms_code": None,
            "active": person["active"],
            "supervisor_name": None,
            "supervisor_email": None,
            "url": person["url"],
            "orcId": None
        }
        if "orcId" in person:
            summarized_person["orcId"] = person["orcId"]

        if "firstName" in person:
            summarized_person["firstName"] = person["firstName"]

        if "middleName" in person:
            summarized_person["middleName"] = person["middleName"]

        if "jobTitle" in person:
            summarized_person["jobTitle"] = person["jobTitle"]

        if "organization" in person:
            summarized_person["organization"] = {
                "name": person["organization"]["displayText"],
                "uri": None,
                "url": None,
                "location": None,
                "fbms_code": None,
                "sipp_CenterCode": None
            }
            org_doc = next((i for i in sb_orgs if i["id"] == person["organization"]["id"]), None)
            if org_doc is not None:
                summarized_person["organization"]["url"] = org_doc["url"]
                summarized_person["organization"]["uri"] = org_doc["link"]["href"]
                summarized_person["organization"]["location"] = sb_location(org_doc)
                if "extensions" in org_doc and "usgsOrganizationExtension" in org_doc["extensions"]:
                    summarized_person["organization"]["fbms_code"] = org_doc["extensions"]["usgsOrganizationExtension"]["fbmsCode"]
                    summarized_person["organization"]["sipp_CenterCode"] = org_doc["extensions"]["usgsOrganizationExtension"]["centerCode"]

        if person["extensions"]["usgsPersonExtension"]["orgCode"] is not None:
            summarized_person["fbms_code"] = person["extensions"]["usgsPersonExtension"]["orgCode"]

        if person["extensions"]["personExtension"]["supervisorId"] is not None:
            supervisor_doc = next((i for i in sb_people if i["id"] == person["extensions"]["personExtension"]["supervisorId"]), None)
            if supervisor_doc is not None:
                summarized_person["supervisor_email"] = supervisor_doc["email"]
                summarized_person["supervisor_name"] = supervisor_doc["displayName"]

        summarized_person["location"] = sb_location(person)

        summarized_people.append(summarized_person)

    return summarized_people

def package_source_orcid_records(limit, offset):
    new_field_mapping = {
        "creator": "CreativeWorks",
        "funder": "Funders"
    }

    orcid_records = search_client.get_index('cache_orcid').get_documents({'limit': limit, 'offset': offset})

    for record in orcid_records:
        if "name" in record:
            record.update({"_display_name": record["name"]})
        else:
            if "givenName" in record and "familyName" in record:
                record.update({"_display_name": f'{record["givenName"]} {record["familyName"]}'})
            else:
                record.update({"_display_name": None})

        record.update({
            "CreativeWorks": None,
            "Funders": None,
            "link": None
        })
        if "@id" in record:
            record.update({"link": record["@id"]})
        
        if "@reverse" in record:
            for k,v in record["@reverse"].items():
                if isinstance(v, dict):
                    record["@reverse"].update({k: [v]})
                elif isinstance(v, list):
                    record["@reverse"].update({k: v})
                record[new_field_mapping[k]] = list()
                for item in [i for i in record["@reverse"][k] if "name" in i and i["name"] is not None]:
                    if "@id" in item:
                        item["link"] = item["@id"]
                    else:
                        item["link"] = None
                    if "identifier" in item:
                        if isinstance(item["identifier"], dict):
                            item.update({"identifier": [item["identifier"]]})
                        for ident in item["identifier"]:
                            item.update({f"identifier_{ident['propertyID']}": ident["value"]})
                        del item["identifier"]
                    record[new_field_mapping[k]].append(item)
            del record["@reverse"]

        if "alumniOf" in record:
            if isinstance(record["alumniOf"], dict):
                record.update({"alumniOf": [record["alumniOf"]]})
            for item in record["alumniOf"]:
                if "identifier" in item:
                    if isinstance(item["identifier"], dict):
                        item.update({"identifier": [item["identifier"]]})
                    for ident in item["identifier"]:
                        item.update({f"identifier_{ident['propertyID']}": ident["value"]})
                    del item["identifier"]
        else:
            record.update({"alumniOf": None})

        if "affiliation" in record:
            if isinstance(record["affiliation"], dict):
                record.update({"affiliation": [record["affiliation"]]})
            for item in record["affiliation"]:
                if "identifier" in item:
                    if isinstance(item["identifier"], dict):
                        item.update({"identifier": [item["identifier"]]})
                    for ident in item["identifier"]:
                        item.update({f"identifier_{ident['propertyID']}": ident["value"]})
                    del item["identifier"]
        else:
            record.update({"affiliation": None})

        if "alternateName" in record:
            if isinstance(record["alternateName"], str):
                record.update({"alternateName": [record["alternateName"]]})
        else:
            record.update({"alternateName": None})

    return orcid_records

def package_source_doi_records(source_meta, limit, offset):
    doi_records = search_client.get_index('cache_doi').get_documents({'limit': limit, 'offset': offset})

    doi_records = [i for i in doi_records if "title" in i and len(i["title"]) > 0]

    for record in doi_records:
        record.update({
            "_issued_year": record["issued"]["date-parts"][0][0]
        })
        for key in [k for k,v in record.items() if k not in source_meta["evaluated_properties"]]:
            del(record[key])

    return doi_records