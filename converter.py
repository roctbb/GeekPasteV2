import datetime
from sqlalchemy import *
from alchemy import *
from config import *
from app import app
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'database.sqlite')

def openSQConn():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    return conn, cur

def getAllCodeSQ(lang=False):
    conn, cur = openSQConn()
    if lang:
        cur.execute('SELECT * FROM codes WHERE lang = ?', [lang])
        n = cur.fetchall()
    else:
        cur.execute('SELECT * FROM codes')
        n = cur.fetchall()
    return n


with app.app_context():
    db.create_all()

def getCode(id):
    return CodesTable.query.get(id)
    

def saveCode(id, code, lang, clientIp):
    code = CodesTable(id=id, code=code, lang=lang, ip=clientIp, date=str(datetime.date.today()).replace('-', '.'), views=0)
    db.session.add(code)
    db.session.commit()

def getAllCode(lang=None):
    if not lang:
        return CodesTable.query.all()
    return CodesTable.query.filter_by(lang=lang).all()


def addView(id):
    query = CodesTable.query.get(id)
    query.views += 1
    db.session.commit()

with app.app_context():
    n = getAllCodeSQ()
    l = len(n)
    for i in range(l):
        if i % 10 == 0:
            print(f'{i}/{l}')
        if n[i][2]:
            saveCode(n[i][2], n[i][1], n[i][0], '0.0.0.0')