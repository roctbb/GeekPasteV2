from flask import Flask
from alchemy import db
from config import *
from flask_migrate import Migrate

app = Flask(__name__)
app.config['BASIC_AUTH_USERNAME'] = LOGIN
app.config['BASIC_AUTH_PASSWORD'] = PASSWORD
app.config["SQLALCHEMY_DATABASE_URI"] = CONNECTION_STRING
db.init_app(app)

migrate = Migrate(app, db)
