# coding: utf8
from flask import *
from paste_celery import save_similarities
from methods import *
from manage import *

@app.route('/submit', methods=['POST'])
@login_required
def submit():
    lang = request.form.get('lang')
    code = request.form.get('code')
    client_ip = request.remote_addr

    if not code.strip():
        flash("Введите код.", "danger")
        return redirect('/')

    if not lang or lang not in LANGS:
        flash("Выберите язык.", "danger")
        return redirect('/')

    id = save_code(code, lang, client_ip, user_id=session['user_id'])
    save_similarities.delay(id)

    flash("Теперь код доступен по адресу: https://paste.geekclass.ru/?id=" + str(id), 'success')

    return redirect(f"/?id={id}")


@app.route('/', methods=['GET'])
@login_required
def index():
    code_id = request.args.get('id')

    if code_id:
        code = get_code(code_id)

        add_view(code)

        if not code:
            flash("Код не найден.", "danger")
        else:
            return render_template('code.html', code=code)

    return render_template('index.html')


@app.route('/raw', methods=['GET'])
def raw():
    code_id = request.args.get('id')

    if code_id:
        code = get_code(code_id)

        if not code:
            flash("Код не найден.", "danger")
        else:
            return f"<pre>{code.code}</pre>"

    return redirect('/')


@app.route('/check', methods=['GET'])
@login_required
def check_code():
    code_id = request.args.get('id')

    if session['role'] not in ['teacher', 'admin']:
        abort(403)

    if not code_id:
        flash("Выберите код для проверки.", "danger")
        return redirect('/')

    code = get_code(code_id)

    if not code:
        flash("Код не найден.", "danger")
        return redirect('/')

    similarities = code.get_similar_codes_sorted()

    return render_template('check.html', code=code, similarities=similarities)


if __name__ == '__main__':
    app.run(debug=DEBUG, port=PORT)
