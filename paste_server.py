# coding: utf8
from io import BytesIO

from flask import *
from paste_celery import *
from methods import *
from manage import *
from datetime import datetime, timedelta
from telegram_notifier import send_telegram_message
from config import USER_URL, TASK_URL


@app.route('/', methods=['POST'])
@login_required
def submit():
    lang = request.form.get('lang')
    code = request.form.get('code')
    task_id = request.args.get('task_id')
    course_id = request.args.get('course_id')

    client_ip = request.remote_addr

    if 'file' in request.files:
        file = request.files['file']

        if file.filename.endswith('.zip'):
            lang = "zip"
            content = file.read()

            if len(content) > 200000000:
                flash("Слишком большой файл.", "danger")
                if task_id and course_id:
                    return redirect('/?task_id={}&course_id={}'.format(task_id, course_id))
                return redirect('/?lang=zip')

            code = extract_data_from_zipfile(content)
            if not code:
                flash("Не удалось прочитать архив.", "danger")
                if task_id and course_id:
                    return redirect('/?task_id={}&course_id={}'.format(task_id, course_id))
                return redirect('/?lang=zip')

        if file.filename.endswith('.ipynb'):
            code = file.read().decode('utf-8')
            lang = "ipynb"

    if not code.strip():
        flash("Введите код.", "danger")
        return redirect('/')

    if not lang or lang not in LANGS + ['ipynb', 'zip']:
        flash("Выберите язык.", "danger")
        return redirect('/')


    if task_id and not Task.query.filter_by(id=task_id).first():
        abort(404)

    id = save_code(code, lang, client_ip, user_id=session['user_id'], task_id=task_id, course_id=course_id)

    # Notify if too many submissions for the same task in the last hour (>5)
    try:
        if task_id:
            task = Task.query.filter_by(id=task_id).first()
            if task and task.check_type == 'gpt':
                window_start = datetime.now() - timedelta(hours=1)
                cnt = (Code.query
                       .filter_by(user_id=session['user_id'], task_id=task_id)
                       .filter(Code.created_at >= window_start)
                       .count())
                if cnt >= 6 and cnt % 6 == 0:
                    profile_url = f"{USER_URL}{session['user_id']}"
                    task_link = TASK_URL.format(course_id=course_id, task_id=task_id, user_id=session['user_id']) if course_id and task_id else ""
                    extra_links = f"\nПрофиль: {profile_url}"
                    if task_link:
                        extra_links += f"\nСтраница задания: {task_link}"
                    text = (
                        "🔁 Частые отправки решения (GPT)"
                        f"\nПользователь: {session['user_id']}"
                        f"\nЗадание: {task_id} ({task.name if task and task.name else ''})"
                        f"\nОтправок за последний час: {cnt}"
                        f"\nПоследняя отправка: {APP_URL}/?id={id}" +
                        f"{extra_links}"
                    )
                    send_telegram_message(text)
    except Exception:
        pass

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

    return render_template('similarity_warnings.html', codes=codes, user_url=USER_URL, task_url=TASK_URL)


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
    has_error = False
    prefered_lang = request.args.get('lang')

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

            if code.lang == 'zip':
                code.code = json.loads(code.code)

            return render_template('code.html', code=code, similarities=similarities, user_url=USER_URL, task_url=TASK_URL)

    task_id = request.args.get('task_id')
    course_id = request.args.get('course_id')

    if task_id and course_id and course_id.isnumeric():
        task = Task.query.filter_by(id=task_id).first()

        if task:
            prefered_lang = task.lang
            flash(f"Отправка задания ID {task.id}: {task.name}. Оно будет проверено автоматически.", "info")
    else:
        task = None

    if not task and task_id:
        flash("Задача не найдена в базе.", "warning")
        has_error = True

    return render_template('index.html', task=task, has_error=has_error, prefered_lang=prefered_lang)


@app.route('/zip')
def download_archive():
    code_id = request.args.get('id')

    if code_id:
        code = get_code(code_id)

        if not code or code.lang != 'zip':
            flash("Код не найден.", "danger")
        elif code.task and not is_teacher() and not is_author(code):
            flash("Нет доступа. Это приватный код.", "danger")
        else:
            response = make_response(rebuild_zip(code))
            response.headers['Content-Type'] = 'application/zip'
            response.headers['Content-Disposition'] = f'attachment; filename=paste_{code.id}.zip'

            return response

    return redirect('/')


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


@app.route('/solutions', methods=['GET'])
@login_required
def solutions():
    # Teacher-only page with paginated successful task submissions
    if not is_teacher():
        abort(403)

    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except Exception:
        page = 1

    filter_mode = request.args.get('filter', 'unviewed')  # 'all' or 'unviewed'

    per_page = 50
    base_query = Code.query.filter(Code.task_id.isnot(None), Code.check_state == 'done')
    if filter_mode == 'unviewed':
        base_query = base_query.filter_by(viewed_by_teacher=False)
    query = base_query.order_by(Code.created_at.desc())

    total = query.count()
    codes = query.offset((page - 1) * per_page).limit(per_page).all()

    has_prev = page > 1
    has_next = page * per_page < total

    return render_template('solutions.html',
                           codes=codes,
                           page=page,
                           has_prev=has_prev,
                           has_next=has_next,
                           total=total,
                           per_page=per_page,
                           user_url=USER_URL,
                           task_url=TASK_URL,
                           filter_mode=filter_mode)


@app.route('/solutions/mark_viewed/<code_id>', methods=['POST', 'GET'])
@login_required
def mark_solution_viewed(code_id):
    if not is_teacher():
        abort(403)
    code = get_code(code_id)
    if not code:
        abort(404)
    code.viewed_by_teacher = True
    db.session.commit()

    # redirect back to solutions list keeping page/filter if possible
    ref = request.referrer or url_for('solutions')
    return redirect(ref)


@app.route('/solutions/mark_unviewed/<code_id>', methods=['POST', 'GET'])
@login_required
def mark_solution_unviewed(code_id):
    if not is_teacher():
        abort(403)
    code = get_code(code_id)
    if not code:
        abort(404)
    code.viewed_by_teacher = False
    db.session.commit()
    ref = request.referrer or url_for('solutions')
    return redirect(ref)


@app.route('/my/submissions', methods=['GET'])
@login_required
def my_submissions():
    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except Exception:
        page = 1

    per_page = 50
    query = Code.query.filter_by(user_id=session['user_id']).order_by(Code.created_at.desc())
    total = query.count()
    codes = query.offset((page - 1) * per_page).limit(per_page).all()

    has_prev = page > 1
    has_next = page * per_page < total

    return render_template('my_codes.html',
                           codes=codes,
                           page=page,
                           has_prev=has_prev,
                           has_next=has_next,
                           total=total,
                           per_page=per_page)


if __name__ == '__main__':
    app.run(debug=DEBUG, port=PORT)
