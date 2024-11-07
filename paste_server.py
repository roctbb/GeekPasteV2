# coding: utf8
from flask import *
from paste_celery import *
from methods import *
from manage import *


@app.route('/', methods=['POST'])
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

    task_id = request.args.get('task_id')
    course_id = request.args.get('course_id')
    if task_id and not Task.query.filter_by(id=task_id).first():
        abort(404)

    id = save_code(code, lang, client_ip, user_id=session['user_id'], task_id=task_id, course_id=course_id)
    save_similarities.delay(id)
    if task_id:
        check_task.delay(id)

    flash("Теперь код доступен по адресу: https://paste.geekclass.ru/?id=" + str(id), 'success')

    return redirect(f"/?id={id}")


def is_teacher():
    return session['role'] in ['teacher', 'admin']


def is_author(code):
    return code.user_id == session['user_id']


@app.route('/warnings', methods=['GET'])
@login_required
def warnings():
    if not is_teacher():
        abort(403)

    codes = Code.query.filter_by(has_similarity_warning=True).order_by(Code.created_at.desc()).all()

    codes = list(filter(lambda c: not c.task_id or c.check_points == c.task.points, codes))

    return render_template('similarity_warnings.html', codes=codes, user_url=USER_URL)


@app.route('/warnings/uncheck/<code_id>', methods=['GET'])
@login_required
def uncheck_warning(code_id):
    if not is_teacher():
        abort(403)

    code = get_code(code_id)

    if code:
        code.has_similarity_warning = False
        db.session.commit()

    return redirect('/warnings')


@app.route('/', methods=['GET'])
@login_required
def index():
    code_id = request.args.get('id')

    if code_id:
        code = get_code(code_id)

        if not code:
            flash("Код не найден.", "danger")
        elif code.task and not is_teacher() and not is_author(code):
            flash("Нет доступа. Это приватный код.", "danger")
        else:
            similarities = []
            if is_teacher():
                similarities = code.get_similar_codes_sorted()
            elif not is_author(code):
                add_view(code)

            return render_template('code.html', code=code, similarities=similarities, user_url=USER_URL)

    task_id = request.args.get('task_id')
    course_id = request.args.get('course_id')

    if task_id and course_id:
        task = Task.query.filter_by(id=task_id).first()

        if not task:
            flash("Задача не найдена в базе.", "warning")
        else:
            flash(f"Отправка задания ID {task.id}: {task.name}. Оно будет проверено автоматически.", "info")
    else:
        task = None

    return render_template('index.html', task=task)


@app.route('/raw', methods=['GET'])
@login_required
def raw():
    code_id = request.args.get('id')

    if code_id:
        code = get_code(code_id)

        if not code:
            flash("Код не найден.", "danger")
        else:
            response = make_response(code.code)
            response.headers['Content-Type'] = 'text/plain'
            return response

    return redirect('/')


if __name__ == '__main__':
    app.run(debug=DEBUG, port=PORT)
