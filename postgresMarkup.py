import psycopg2
import string
import random
import datetime
from config import *

def openConn():
    conn = psycopg2.connect(host=CONNHOST, port=CONNPORT, dbname=CONNDBNAME, user=CONNUSER, password=CONNPASSWORD)
    cur = conn.cursor()
    return conn, cur

conn, cur = openConn()
cur.execute("""
        CREATE TABLE codes (
            id TEXT,
            lang TEXT,
            code TEXT,
            ip TEXT,
            date TEXT,
            views BIGINT
        )
        """)
cur.execute("""
        CREATE TABLE similarities (
            id TEXT,
            id2 TEXT,
            percent TEXT
        )
        """)
conn.commit()
conn.close()