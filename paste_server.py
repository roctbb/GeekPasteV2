# coding: utf8
from flask import *
from flask_basicauth import BasicAuth
from paste_celery import save_similarities
from methods import *
from manage import app

basic_auth = BasicAuth(app)


@app.errorhandler(404)
@app.errorhandler(500)
def not_found(error):
    return render_template('notfound.html', error='Страница не найдена.')


@app.errorhandler(401)
def wrong_password(error):
    return render_template('notfound.html',
                           error='Доступ отклонен.\nЕсли вам кажется что это ошибка, обратитесь к администратору сайта')


@app.route('/', methods=['POST', 'GET'])
def index():
    if request.args.get('id'):
        return redirect(f"/{request.args.get('id')}")

    if request.method == 'POST':
        lang = request.form['lang']
        code = request.form['code']
        client_ip = request.remote_addr
        if not code.strip():
            return render_template('notfound.html', error='Ты не можешь сохранить пустой код.')
        id = save_code(code, lang, client_ip)
        save_similarities.delay(id)
        return redirect(f"/{id}")
    if request.method == 'GET':
        return render_template('index.html')


@app.route('/check/<code_id>', methods=['GET'])
@basic_auth.required
def check_code(code_id=None):
    code = get_code(code_id)

    if not code:
        return render_template('notfound.html', error=f'Объект с id={code_id} не найден.')

    similarities = code.similarities

    if not similarities:
        return render_template('notfound.html', error=f'Этот код еще проверяется, попробуйте позже.')

    similarities = code.get_similar_codes_sorted()

    return render_template('similarityCheck.html', code=code, similarities=similarities)


@app.route('/<code_id>')
def code(code_id=None):
    if code_id.startswith('check='):
        return check_code(code_id[6:])

    code = get_code(code_id)
    if not code:
        return render_template('notfound.html', error='Страница не найдена.')
    return render_template('code.html', code=code)


if __name__ == '__main__':
    app.run(debug=DEBUG)
