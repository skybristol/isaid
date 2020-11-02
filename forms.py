from wtforms import Form, StringField, SelectField, TextField
from wtforms.validators import DataRequired
from functions import *
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
conn = db.engine.connect().connection

class PersonSearchForm(Form):
#    people = get_people(db_con=conn)
#    person_choices = [(i["identifier_email"], i["displayname"]) for i in people]

#    email = SelectField('Select Person:', choices=person_choices)
    expertise = StringField('Select Type of Expertise', validators=[DataRequired()], render_kw={"placeholder": "expertise"})