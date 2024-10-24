from celery import Celery
import checker
from config import *
from base import *
from appServer import app as app1

app = Celery('app', broker=CELERYBROKER)

@app.task()
def saveSimilarities(id):
    with app1.app_context():
        code = getCode(id)
        if str(code) == 'None':
            return
        allCode = getAllCode(code.lang)
        if len(allCode) == 1:
            return
        for code2 in allCode:
            if code2.id == code.id:
                continue
            if code.ip != '0.0.0.0':
                if code2.ip == code.ip:
                    continue
            n = checker.similarity(code.code, code2.code)
            if n > 50:
                saveSimilarity(code.id, code2.id, n)
