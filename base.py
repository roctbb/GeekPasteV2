import string
import random
import datetime
from sqlalchemy import *
from alchemy import *
from config import *

def create_id():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))

def getCode(id):
    return CodesTable.query.get(id)
    

def saveCode(code, lang, clientIp):
    id = create_id()
    while getCode(id):
        id = create_id()

    code = CodesTable(id=id, code=code, lang=lang, ip=clientIp, date=str(datetime.date.today()).replace('-', '.'), views=0)
    db.session.add(code)
    db.session.commit()

    return id

def getAllCode(lang=None):
    if not lang:
        return CodesTable.query.all()
    return CodesTable.query.filter_by(lang=lang).all()


def addView(id):
    query = CodesTable.query.get(id)
    query.views += 1
    db.session.commit()

def saveSimilarity(id, id2, percent):
    pkid = create_id()
    while getSavedSimilarities(pkid):
        pkid = create_id(pkid)
    similarity = SimilaritiesTable(id=id, id2=id2, pkid=pkid, percent=percent)
    db.session.add(similarity)
    db.session.commit()

def getSavedSimilarities(id):
    n = SimilaritiesTable.query.where(SimilaritiesTable.id == id)
    if n == None:
        return None
    else:
        return n.all()

def getAllSimilarities():
    return SimilaritiesTable.query.all()

