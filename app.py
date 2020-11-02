from flask import Flask, jsonify, render_template, request, flash, redirect
from flask_sqlalchemy import SQLAlchemy
from functions import *
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import Navbar, View

def create_app():
    app = Flask(__name__)
    Bootstrap(app)

    return app

app = create_app()

app.config["SECRET_KEY"] = "SomethingSuperSecret"

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

db = SQLAlchemy(app)
conn = db.engine.connect().connection

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/people")
def people():
    return jsonify(get_people(db_con=conn))

@app.route("/terms/<term_source>", methods=['GET'])
def terms(term_source):
    return jsonify(lookup_terms(term_type=term_source))

@app.route("/person/<person_id>", methods=['GET'])
def lookup_person(person_id):
    query_parameter = lookup_parameter_person(person_id)

    if "format" in request.args:
        output_format = args["format"]
    else:
        output_format="html"

    if "collections" in request.args:
        datasets = args["collections"].split(",")
    else:
        datasets = ["directory", "assets", "claims"]

    if output_format == "json":
        person_content = dict()
        for data_section in datasets:
            person_content[data_section] = package_json(
                collection=data_section,
                query_param=query_parameter,
                query_param_value=person_id,
                db_con=conn
            )
        
        return jsonify(person_content)

    else:
        person_content = str()
        for data_section in datasets:
            person_content = person_content + package_html(
                collection=data_section,
                query_param=query_parameter,
                query_param_value=person_id,
                base_url=request.base_url,
                db_con=conn
            )

        return render_template("person.html", html_content=person_content)

from forms import PersonSearchForm

@app.route('/search', methods=['GET', 'POST'])
def search():
    search = PersonSearchForm(request.form)
    if request.method == 'POST':
        return search_results(search)
    return render_template('search.html', form=search)

@app.route('/results')
def search_results(search):
    if search.data["email"] is not None:
        return redirect(f'/person/{search.data["email"]}')
    
    results = []
    search_string = search.data['search']
    if search.data['search'] == '':
        pass 
    if not results:
        flash(type(search))
        return redirect('/search')
    else:
        # display results
        return render_template('results.html', results=results)


nav = Nav()

@nav.navigation()
def isaid_navbar():
    return Navbar(
        'iSAID',
        View('Home', 'home'),
        View('People', 'people')
    )

nav.init_app(app)

