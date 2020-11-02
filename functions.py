import os
import validators
import re
from urllib.parse import urlparse
import pandas as pd
import psycopg2
from flask import Markup, Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
conn = db.engine.connect().connection

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

def get_data(collection, query_param, query_param_value, db_con, target_output="json"):
    selection_properties = {
        "table_name": isaid_data_collections[collection]["table_name"],
        "query_param": query_param,
        "query_param_value": query_param_value
    }

    if target_output == "html":
        selection_properties["select_properties"] = ','.join(isaid_data_collections[collection]["display_properties"])
    else:
        selection_properties["select_properties"] = '*'

    sql = '''
        SELECT %(select_properties)s
        FROM %(table_name)s
        WHERE %(query_param)s = '%(query_param_value)s'
    ''' % selection_properties
    
    df = pd.read_sql_query(sql, con=db_con)

    return df

def package_json(collection, query_param, query_param_value, db_con):
    df = get_data(collection, query_param, query_param_value, db_con)
    return df.to_dict(orient="records")

def package_html(
    collection, 
    query_param, 
    query_param_value,
    db_con, 
    include_title=True, 
    include_description=True, 
    markup=True,
    base_url=None
):
    index_in_html=False
    header_in_html=True

    df = get_data(collection, query_param, query_param_value, db_con, target_output="html")

    if df.empty:
        return str()
    
    if isaid_data_collections[collection]["display_transpose"]:
        index_in_html=True
        header_in_html=False
        df = df.transpose()
    
    if isaid_data_collections[collection]["sort_by"] is not None:
        df = df.sort_values(
            by=isaid_data_collections[collection]["sort_by"],
            ascending=False
        )
    
    html_content = str()

    if include_title:
        html_content = html_content + f"<h2>{isaid_data_collections[collection]['title']}</h2>"

    if include_description:
        html_content = html_content + f"<p>{isaid_data_collections[collection]['description']}</p>"
    
    if base_url is not None:
        html_content = html_content + f"<p><a href='{base_url}?collections={collection}&format=json'>View as JSON</a></p>"

    html_content = html_content + df.to_html(
        render_links=True,
        na_rep="NA",
        justify="left",
        header=header_in_html,
        index=index_in_html,
        classes=["table"]
    )

    if markup:
        html_content = Markup(html_content)

    return html_content

def get_people(search_type=None, search_term=None):
    d_search = {
        "search_type": search_type,
        "search_term": search_term
    }

    if search_type in ["expertise", "job title", "organization"] and search_term is not None:
        sql = '''
            SELECT subject_displayname AS full_name, subject_identifier_email AS email, COUNT(*) as total_occurrences
            FROM identified_claims_m
            WHERE property_label = '%(search_type)s'
            AND object_label LIKE '*%(search_term)s*'
            GROUP BY subject_displayname, subject_identifier_email
            ORDER BY subject_displayname
        ''' % d_search
    elif search_type in ["name"] and search_term is not None:
        sql = '''
            SELECT displayname AS full_name, identifier_email AS email
            FROM people
            WHERE displayname LIKE '%%%s%%'
            ORDER BY displayname
        ''' % search_term
    else:
        sql = '''
            SELECT displayname AS full_name, identifier_email AS email
            FROM people
            ORDER BY displayname
        '''
    df = pd.read_sql_query(sql, con=conn)
    return df

def lookup_terms(term_type="expertise"):
    sql = '''
        SELECT DISTINCT object_label
        FROM claims
        WHERE property_label = '%s'
        AND object_label <> ''
    ''' % term_type

    return pd.read_sql_query(sql, con=conn).to_dict(orient="records")
   