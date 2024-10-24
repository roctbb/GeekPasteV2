# coding: utf8
from config import *
from flask import *
from flask_basicauth import BasicAuth
from celeryApp import saveSimilarities
import base

from appServer import app

basic_auth = BasicAuth(app)

@app.errorhandler(404)
@app.errorhandler(500)
def not_found(error):
    return render_template('notfound.html', error='Страница не найдена.')

@app.errorhandler(401)
def wrongPassword(error):
    return render_template('notfound.html', error='Доступ отклонен.\nЕсли вам кажется что это ошибка, обратитесь к администратору сайта')

@app.route('/', methods=['POST', 'GET'])
def index():
    if request.method == 'POST':
        lang = request.form['lang']
        code = request.form['code']
        clientIp = request.remote_addr
        if code.replace(f'\r\n', '').replace(' ', '') == '':
            return render_template('notfound.html', error='Ты не можешь сохранить пустой код.')
        else:
            code = request.form['code']
        id = base.saveCode(code, lang, clientIp)
        saveSimilarities.delay(id)
        return redirect(f"/{id}")
    if request.method == 'GET':
        return render_template('index.html')

@basic_auth.required
def check_code(code_id=None):
    #
    # get coed from db 
    # 
    
    
    code = base.getCode(code_id)
    if str(code) == 'None':
        return render_template('notfound.html', error=f'Объект с id={code_id} не найден.')
    similarities = base.getSavedSimilarities(code_id)
    if not similarities:
        return render_template('notfound.html', error=f'Этот код еще проверяется, попробуйте позже.')
    
    similarities = sorted(similarities, key=lambda x: x.percent, reverse=True)
    for i in range(len(similarities)):
        code2 = base.getCode(similarities[i].id)
        s = similarities[i].percent
        similarities[i] = [code2, s, i]

    return render_template('similarityCheck.html', record=code, similars=similarities)

@app.route('/<code_id>')
def code(code_id=None):
    if code_id.startswith('check='):
        return check_code(code_id[6:])

    record = base.getCode(code_id)
    if str(record) == 'None':
        return render_template('notfound.html', error='Страница не найдена.')
    # base.addView(code_id)
    return render_template('codepage.html', record=record, id=code_id)
