from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *

db = SQLAlchemy()

class CodesTable(db.Model):
    __tablename__ = 'codes'

    id = db.Column(db.String(), primary_key=True)
    lang = db.Column(db.String())
    code = db.Column(db.String())
    ip = db.Column(db.String())
    date = db.Column(db.String())
    views = db.Column(db.Integer())


class SimilaritiesTable(db.Model):
    __tablename__ = 'similarities'

    id = db.Column(db.String())
    id2 = db.Column(db.String())
    pkid = db.Column(db.String(), primary_key=True)
    percent = db.Column(db.Integer())