from flask import Flask, Markup
from flask import render_template
import os
import validators
import re
from urllib.parse import urlparse
import requests
import pandas as pd

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("home.html")

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    if validators.email(person_id):
        query_parameter = "identifier_email"
    else:
        if re.match(r"\d{4}-\d{4}-\d{4}-\d{4}", person_id):
            query_parameter = "identifier_orcid"
        elif re.match(r"Q\d*", person_id):
            query_parameter = "identifier_wikidata"
        else:
            return "Unparseable ID"

    search_result = assemble_person_record(parameter_name=query_parameter, parameter_value=person_id)

    directory_header = "<h2>Directory/Contact Information</h2>"

    directory_table = pd.DataFrame(search_result["directory"])[[
            "displayname",
            "jobtitle",
            "url",
            "organization_name",
            "organization_url",
            "region",
            "city",
            "state"
    ]].transpose().to_html(
        render_links=True,
        header=False,
        na_rep="NA",
        justify="left"
    )

    asset_header = "<h2>Publications and Other Assets</h2>"

    asset_table = pd.DataFrame(search_result["assets"])[[
        "additionaltype",
        "contact_type",
        "contact_role",
        "name",
        "datepublished",
        "url"
    ]].sort_values(
        by="datepublished",
        ascending=False
    ).to_html(
        render_links=True,
        na_rep="NA",
        justify="left",
        index=False
    )

    person_content = Markup(directory_header + directory_table + asset_header + asset_table)

    return render_template("person.html", html_content=person_content)


isaid_data_collections = {
    "directory": {
        "title": "Directory",
        "description": "Properties pulled from the ScienceBase Directory for USGS employees and other people"
    },
    "assets": {
        "title": "Assets",
        "description": "Scientific assets such as publications, datasets, models, instruments, and "
                        "other articles. Linked to people through roles such as author/creator."
    },
    "claims": {
        "title": "Claims",
        "description": "Statements or assertions about a person or asset that characterize the entities in "
                        "various ways, including the connections between entities."
    },
    "wikidata_entities": {
        "title": "WikiData Entity",
        "description": "An entity in WikiData representing a person or scientific asset."
    },
    "wikidata_claims": {
        "title": "WikiData Claims",
        "descriptions": "Statements or assertions about a person or other entity in WikiData that characterize "
                        "them in various ways, including the connections between entities."
    }
}


def execute_query(query, api=None):
    if api is None:
        api = os.getenv("ISAID_API")

    r = requests.post(
        api,
        json={"query": query},
        headers={"content-type": "application/json"},
        verify=False
    )

    if r.status_code != 200:
        raise ValueError("Query could not be processed.")

    return r.json()

def assemble_person_record(parameter_name, parameter_value, datatypes=None):
    where_clause = '(where: {%s: {%s: "%s"}})' % (
        parameter_name,
        "_eq",
        parameter_value
    )

    if datatypes is None:
        datatypes = [k for k, v in isaid_data_collections.items()]
    else:
        datatypes = [i for i in datatypes if i in [k for k, v in isaid_data_collections.items()]]

    query_sections = dict()

    query_sections["directory"] = '''
        directory %(where_clause)s {
            cellphone
            city
            date_cached
            description
            displayname
            email
            firstname
            generationalqualifier
            identifier_email
            identifier_orcid
            identifier_sbid
            identifier_wikidata
            jobtitle
            lastname
            middlename
            note
            organization_name
            organization_uri
            organization_url
            region
            usgs_mission_areas
            usgs_programs
            personaltitle
            professionalqualifier
            state
            url
        }
    ''' % {"where_clause": where_clause}

    query_sections["assets"] = '''
        assets %(where_clause)s {
            additionaltype
            contact_role
            contact_type
            datecreated
            datemodified
            datepublished
            identifier_email
            identifier_orcid
            identifier
            identifier_sbid
            identifier_wikidata
            name
            publication
            publisher
            url
        }
    ''' % {"where_clause": where_clause}

    query_sections["claims"] = '''
        claims %(where_clause)s {
            claim_created
            claim_source
            date_qualifier
            object_instance_of
            object_label
            object_qualifier
            property_label
            reference
            subject_instance_of
            subject_label
            subject_identifier_email
            subject_identifier_orcid
            subject_identifier_sbid
            subject_identifier_wikidata
            object_identifier_email
            object_identifier_orcid
            object_identifier_sbid
            object_identifier_wikidata
        }
    ''' % {"where_clause": where_clause.replace("identifier_", "subject_identifier_")}

    query_sections["wikidata_entities"] = '''
        wikidata_entities %(where_clause)s {
            aliases_en
            description_en
            identifier_wikidata
            label_en
            modified
            type
        }
    ''' % {"where_clause": where_clause}

    query_sections["wikidata_claims"] = '''
        wikidata_claims %(where_clause)s {
            property_description
            property_entity_description
            property_entity_label
            property_id
            property_label
            property_value
        }
    ''' % {"where_clause": where_clause}

    query = '''
    {
    '''

    for data_type in datatypes:
        query = '''
        %s
        %s
        ''' % (query, query_sections[data_type])

    query = '''
    %s
    }
    ''' % (query)

    try:
        query_response = execute_query(query)
    except ValueError as e:
        return e

    if "errors" in query_response.keys():
        return query_response
    else:
        return query_response["data"]

