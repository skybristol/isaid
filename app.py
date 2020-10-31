from flask import Flask
from flask import render_template

app = Flask(__name__)


@app.route("/")
def hello_world():
    return render_template("index.html")

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    return person_id