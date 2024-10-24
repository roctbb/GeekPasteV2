from flask import Flask
from alchemy import db
from config import *

app = Flask(__name__)
app.config['BASIC_AUTH_USERNAME'] = USERFORCOPYCHECK
app.config['BASIC_AUTH_PASSWORD'] = PASSWORDFORCOPYCHECK
app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql://{CONNUSER}:{CONNPASSWORD}@{CONNHOST}:{CONNPORT}/{CONNDBNAME}"
db.init_app(app)

with app.app_context():
    db.create_all()