from flask import Flask

from json2html import *
import pylinkedcmd

cmd_isaid = pylinkedcmd.pylinkedcmd.Isaid()

app = Flask(__name__)


@app.route("/")
def hello_world():
    return "iSAID"

@app.route("/orgs")
def get_orgs():
    orgs = cmd_isaid.get_organizations()
    return json2html.convert(json=orgs)
