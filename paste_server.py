# coding: utf8
from io import BytesIO

from flask import *
from paste_celery import *
from methods import *
from manage import *
from datetime import datetime, timedelta
from telegram_notifier import send_telegram_message
from config import USER_URL, TASK_URL, AUTH_URL, DEFAULT_GPT_RATE_LIMIT, LANGS
from urllib.parse import quote


def check_gpt_rate_limit(user_id, task_id, task=None):
    """
    Проверяет, не превысил ли пользователь лимит на GPT-сдачи для конкретной задачи.
    Возвращает (allowed: bool, current_count: int, limit: int)
    """
    # Получаем лимит для задачи из БД или используем стандартный
    if task is None:
        task = Task.query.filter_by(id=task_id).first()

    limit = task.gpt_rate_limit if task and task.gpt_rate_limit is not None else DEFAULT_GPT_RATE_LIMIT

    # Ключ в Redis: gpt_limit:user_id:task_id
    redis_key = f"gpt_limit:{user_id}:{task_id}"

    try:
        # Получаем текущее количество сдач
        current_count = redis_client.get(redis_key)
        current_count = int(current_count) if current_count else 0

        if current_count >= limit:
            return False, current_count, limit

        # Увеличиваем счетчик и устанавливаем TTL атомарно
        pipe = redis_client.pipeline()
        pipe.incr(redis_key)

        # Устанавливаем TTL только если ключ новый (первая сдача)
        if current_count == 0:
            pipe.expire(redis_key, 3600)  # TTL 1 час

        results = pipe.execute()
        new_count = results[0]

        return True, new_count, limit
    except Exception as e:
        # В случае ошибки Redis разрешаем сдачу
        print(f"Redis error in rate limiting: {e}")
        return True, 0, limit


def get_gpt_rate_limit_info(user_id, task_id, task=None):
    """
    Получает информацию о текущем состоянии лимита для пользователя и задачи.
    Возвращает (current_count: int, limit: int, time_left_seconds: int)
    """
    # Получаем лимит для задачи из БД или используем стандартный
    if task is None:
        task = Task.query.filter_by(id=task_id).first()

    limit = task.gpt_rate_limit if task and task.gpt_rate_limit is not None else DEFAULT_GPT_RATE_LIMIT

    redis_key = f"gpt_limit:{user_id}:{task_id}"

    try:
        current_count = redis_client.get(redis_key)
        current_count = int(current_count) if current_count else 0

        # Получаем оставшееся время до сброса
        ttl = redis_client.ttl(redis_key)
        ttl = ttl if ttl > 0 else 0

        return current_count, limit, ttl
    except Exception as e:
        print(f"Redis error in rate limit info: {e}")
        return 0, limit, 0


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

    # Проверяем существование задачи и лимиты для GPT-задач
    if task_id:
        task = Task.query.filter_by(id=task_id).first()
        if not task:
            abort(404)

        # Проверка лимита для GPT-задач
        if task.check_type == 'gpt':
            allowed, current_count, limit = check_gpt_rate_limit(session['user_id'], task_id, task)
            if not allowed:
                flash(f"Превышен лимит сдач для этой задачи ({limit} в час). Попробуйте позже.", "danger")
                return redirect('/?task_id={}&course_id={}'.format(task_id, course_id))

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

    warning_type = request.args.get('type', 'similarity')  # similarity or ai

    if warning_type == 'ai':
        codes = Code.query.filter_by(has_ai_warning=True).order_by(Code.created_at.desc()).all()
    else:
        codes = Code.query.filter_by(has_similarity_warning=True).order_by(Code.created_at.desc()).all()

    codes = list(filter(lambda c: not c.task_id or c.check_points == c.task.points, codes))

    return render_template('similarity_warnings.html', codes=codes, user_url=USER_URL, task_url=TASK_URL, warning_type=warning_type)


@app.route('/warnings/uncheck/<code_id>', methods=['GET'])
@login_required
def uncheck_warning(code_id):
    if not is_teacher():
        abort(403)

    warning_type = request.args.get('type', 'similarity')
    code = get_code(code_id)

    if code:
        if warning_type == 'ai':
            code.has_ai_warning = False
        else:
            code.has_similarity_warning = False
        db.session.commit()

    return redirect(f'/warnings?type={warning_type}')


@app.route('/', methods=['GET'])
def index():
    # Handle JWT token if present
    token = request.args.get('token')
    if token:
        try:
            make_jwt_auth(token)
            return redirect(url_for(request.endpoint, **{k: v for k, v in request.args.items() if k != 'token'}))
        except:
            pass

    code_id = request.args.get('id')
    has_error = False
    prefered_lang = request.args.get('lang')

    if code_id:
        code = get_code(code_id)

        if not code:
            flash("Код не найден.", "danger")
        elif not code.available_without_auth and not session.get('user_id'):
            redirect_url = request.url if request.url.startswith('https://') else request.url.replace('http://', 'https://')
            return redirect(AUTH_URL + quote(redirect_url, safe=''))
        elif code.task and not code.available_without_auth and not (session.get('user_id') and (is_teacher() or is_author(code))):
            flash("Нет доступа. Это приватный код.", "danger")
        else:
            similarities = []
            if session.get('user_id') and is_teacher():
                similarities = code.get_similar_codes_sorted()
            elif not session.get('user_id') or not is_author(code):
                add_view(code)

            if code.lang == 'zip':
                code.code = json.loads(code.code)

            return render_template('code.html', code=code, similarities=similarities, user_url=USER_URL, task_url=TASK_URL)

    # For creating new pastes, require login
    if not session.get('user_id'):
        return redirect(AUTH_URL + quote(request.url, safe=''))

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

    # Получаем информацию о лимите для GPT-задачи
    gpt_limit_info = None
    if task and task.check_type == 'gpt':
        current_count, limit, time_left = get_gpt_rate_limit_info(session['user_id'], task_id, task)
        gpt_limit_info = {
            'current_count': current_count,
            'limit': limit,
            'time_left': time_left
        }

    return render_template('index.html', task=task, has_error=has_error, prefered_lang=prefered_lang, gpt_limit_info=gpt_limit_info)


@app.route('/zip')
def download_archive():
    # Handle JWT token if present
    token = request.args.get('token')
    if token:
        try:
            make_jwt_auth(token)
            return redirect(url_for(request.endpoint, **{k: v for k, v in request.args.items() if k != 'token'}))
        except:
            pass

    code_id = request.args.get('id')

    if code_id:
        code = get_code(code_id)

        if not code or code.lang != 'zip':
            flash("Код не найден.", "danger")
        elif not code.available_without_auth and not session.get('user_id'):
            redirect_url = request.url if request.url.startswith('https://') else request.url.replace('http://', 'https://')
            return redirect(AUTH_URL + quote(redirect_url, safe=''))
        elif code.task and not code.available_without_auth and not (session.get('user_id') and (is_teacher() or is_author(code))):
            flash("Нет доступа. Это приватный код.", "danger")
        else:
            response = make_response(rebuild_zip(code))
            response.headers['Content-Type'] = 'application/zip'
            response.headers['Content-Disposition'] = f'attachment; filename=paste_{code.id}.zip'

            return response

    return redirect('/')


@app.route('/raw', methods=['GET'])
def raw():
    # Handle JWT token if present
    token = request.args.get('token')
    if token:
        try:
            make_jwt_auth(token)
            return redirect(url_for(request.endpoint, **{k: v for k, v in request.args.items() if k != 'token'}))
        except:
            pass

    code_id = request.args.get('id')

    if code_id:
        code = get_code(code_id)

        if not code:
            flash("Код не найден.", "danger")
        elif not code.available_without_auth and not session.get('user_id'):
            redirect_url = request.url if request.url.startswith('https://') else request.url.replace('http://', 'https://')
            return redirect(AUTH_URL + quote(redirect_url, safe=''))
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
    task_id = request.args.get('task_id')  # filter by task

    per_page = 50
    base_query = Code.query.filter(Code.task_id.isnot(None), Code.check_state == 'done')
    if filter_mode == 'unviewed':
        base_query = base_query.filter_by(viewed_by_teacher=False)
    if task_id:
        base_query = base_query.filter_by(task_id=task_id)
    query = base_query.order_by(Code.created_at.desc())

    total = query.count()
    codes = query.offset((page - 1) * per_page).limit(per_page).all()

    has_prev = page > 1
    has_next = page * per_page < total

    # Get list of all tasks for filter dropdown
    tasks = Task.query.order_by(Task.id).all()

    return render_template('solutions.html',
                           codes=codes,
                           page=page,
                           has_prev=has_prev,
                           has_next=has_next,
                           total=total,
                           per_page=per_page,
                           user_url=USER_URL,
                           task_url=TASK_URL,
                           filter_mode=filter_mode,
                           tasks=tasks,
                           selected_task_id=task_id)


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


@app.route('/solutions/download/<code_id>')
@login_required
def download_solution(code_id):
    if not is_teacher():
        abort(403)
    code = get_code(code_id)
    if not code or code.lang != 'ipynb':
        abort(404)
    return Response(code.code, mimetype='application/x-ipynb+json', headers={'Content-Disposition': f'attachment; filename=solution_{code_id}.ipynb'})


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


@app.route('/recheck', methods=['POST'])
@login_required
def recheck_task():
    if not is_teacher():
        abort(403)

    code_id = request.args.get('id')
    code = get_code(code_id)

    if not code:
        flash("Код не найден.", "danger")
        return redirect('/')

    if not code.task:
        flash("Это не решение задачи.", "danger")
        return redirect(f'/?id={code_id}')

    # Сбрасываем состояние проверки
    code.check_state = 'not checked'
    code.check_points = 0
    code.check_comments = None
    code.checked_at = None
    db.session.commit()

    # Запускаем проверку заново
    check_task.delay(code_id)

    flash("Задача отправлена на повторную проверку.", "info")
    return redirect(f'/?id={code_id}')


@app.route('/api/gpt_rate_limit', methods=['GET'])
@login_required
def gpt_rate_limit_api():
    """
    API endpoint для получения информации о лимите GPT-сдач.
    Параметры: task_id
    Возвращает: JSON с информацией о текущем состоянии лимита
    """
    task_id = request.args.get('task_id')

    if not task_id:
        return jsonify({'error': 'task_id is required'}), 400

    task = Task.query.filter_by(id=task_id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    if task.check_type != 'gpt':
        return jsonify({'error': 'This task is not a GPT task'}), 400

    current_count, limit, time_left = get_gpt_rate_limit_info(session['user_id'], task_id, task)

    return jsonify({
        'current_count': current_count,
        'limit': limit,
        'time_left_seconds': time_left,
        'can_submit': current_count < limit
    })


@app.route('/tasks', methods=['GET'])
@login_required
def tasks_list():
    if not is_teacher():
        abort(403)
    tasks = Task.query.order_by(Task.id.desc()).all()
    return render_template('tasks.html', tasks=tasks, langs=LANGS, edit_task=None)


@app.route('/tasks/<int:task_id>', methods=['GET'])
@login_required
def tasks_edit(task_id):
    if not is_teacher():
        abort(403)
    edit_task = Task.query.get_or_404(task_id)
    tasks = Task.query.order_by(Task.id.desc()).all()
    return render_template('tasks.html', tasks=tasks, langs=LANGS, edit_task=edit_task)


def _fill_task(task):
    new_id = request.form.get('id')
    if new_id and new_id.strip():
        task.id = int(new_id)
    task.name = request.form.get('name') or None
    task.lang = request.form.get('lang') or None
    task.points = int(request.form['points']) if request.form.get('points') else None
    task.check_type = request.form.get('check_type') or 'tests'
    task.text = request.form.get('text') or None
    task.gpt_model = request.form.get('gpt_model') or None
    task.gpt_rate_limit = int(request.form['gpt_rate_limit']) if request.form.get('gpt_rate_limit') else None
    task.bypass_similarity_check = 'bypass_similarity_check' in request.form


@app.route('/tasks', methods=['POST'])
@login_required
def tasks_create():
    if not is_teacher():
        abort(403)
    task = Task()
    _fill_task(task)
    db.session.add(task)
    db.session.commit()
    flash(f'Задача #{task.id} создана.', 'success')
    return redirect('/tasks')


@app.route('/tasks/<int:task_id>', methods=['POST'])
@login_required
def tasks_update(task_id):
    if not is_teacher():
        abort(403)
    task = Task.query.get_or_404(task_id)
    _fill_task(task)
    db.session.commit()
    flash(f'Задача #{task.id} обновлена.', 'success')
    return redirect('/tasks')


@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def tasks_delete(task_id):
    if not is_teacher():
        abort(403)
    task = Task.query.get_or_404(task_id)
    if task.solutions:
        flash(f'Нельзя удалить задачу #{task_id}: есть {len(task.solutions)} решений.', 'danger')
        return redirect('/tasks')
    db.session.delete(task)
    db.session.commit()
    flash(f'Задача #{task_id} удалена.', 'success')
    return redirect('/tasks')


if __name__ == '__main__':
    app.run(debug=DEBUG, port=PORT)
