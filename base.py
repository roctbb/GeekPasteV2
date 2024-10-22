import psycopg2
import string
import random
import datetime

# conn = psycopg2.connect(host="localhost", port=5432, dbname="postgres", user="postgres", password="1234")
# cur = None

def openConn():
    global conn
    global cur
    conn = psycopg2.connect(host="localhost", port=5432, dbname="postgres", user="postgres", password="1234")
    cur = conn.cursor()

def create_id():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))

def getCode(id):
    openConn()
    cur.execute('SELECT * FROM codes WHERE id = %s', [id])
    code = cur.fetchone()
    return code

def saveCode(code, lang, clientIp):
    date = str(datetime.date.today()).replace('-', '.')
    openConn()
    while True:
        id = create_id()
        cur.execute('SELECT COUNT(*) FROM codes WHERE id = %s', [id])
        if cur.fetchone()[0] == 0:
            break

    cur.execute('INSERT INTO codes (id, lang, code, ip, date, views) VALUES (%s,%s,%s,%s,%s,%s)', [id, lang, code, clientIp, date, 0])
    conn.commit()
    conn.close()
    return id

def addView(id):
    openConn()
    cur.execute('UPDATE codes SET views = views + 1 WHERE id = %s', [id])
    conn.commit()
    conn.close()
