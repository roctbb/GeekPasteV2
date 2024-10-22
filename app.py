import base
from flask import Flask
from markupsafe import escape
from flask import url_for
from flask import render_template
from flask import request, redirect


app = Flask(__name__)

@app.errorhandler(404)
@app.errorhandler(500)
def not_found(error):
    return render_template('notfound.html', error='Страница не найдена.')

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
        return redirect(f"/{id}")
    if request.method == 'GET':
        return render_template('index.html')

@app.route('/<code_id>')
def code(code_id=None):
    #
    # get coed from db 
    # 
    record = base.getCode(code_id)
    print(record)
    if str(record) == 'None':
        return render_template('notfound.html', error='Страница не найдена.')
    base.addView(code_id)
    return render_template('codepage.html', record=record, id=code_id)