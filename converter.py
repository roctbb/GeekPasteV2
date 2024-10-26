from tqdm import tqdm
from manage import app
from methods import *
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'database.sqlite')


def get_sqlite_connection():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    return conn, cur


def get_sqlite_codes():
    conn, cur = get_sqlite_connection()
    cur.execute('SELECT * FROM codes')
    return cur.fetchall()


with app.app_context():
    codes = get_sqlite_codes()
    codes_length = len(codes)
    for i in tqdm(range(codes_length)):
        if codes[i][2] and codes[i][0] in LANGS and len(str(codes[i][1])) > 30:
            save_code(codes[i][1], codes[i][0], None, id=codes[i][2])
