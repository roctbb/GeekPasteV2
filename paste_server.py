# coding: utf8
import difflib
import json
from io import BytesIO

from flask import *
from flask_socketio import join_room, emit
from paste_celery import *
from methods import *
from manage import *
from datetime import datetime, timedelta
from telegram_notifier import send_telegram_message
import jwt
from config import USER_URL, TASK_URL, AUTH_URL, DEFAULT_GPT_RATE_LIMIT, LANGS, JWT_SECRET
from urllib.parse import quote
from sqlalchemy import or_

SOCKET_SUBMISSION_ROOM_PREFIX = "submission:"
SYSTEM_RECENT_CHECKS_KEY = "system:recent_checks"


def _submission_room(code_id):
    return f"{SOCKET_SUBMISSION_ROOM_PREFIX}{code_id}"


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
    github_repo_url = (request.form.get('github_repo_url') or '').strip()
    task_id = request.args.get('task_id')
    course_id = request.args.get('course_id')
    zip_content = None
    task = None

    client_ip = request.remote_addr

    def _return_to_submit_form(default_lang=None):
        if task_id and course_id:
            return redirect('/?task_id={}&course_id={}'.format(task_id, course_id))
        if task_id:
            return redirect('/?task_id={}'.format(task_id))
        if default_lang:
            return redirect(f'/?lang={default_lang}')
        return redirect('/')

    if task_id:
        task = Task.query.filter_by(id=task_id).first()
        if not task:
            abort(404)

    if 'file' in request.files:
        file = request.files['file']

        if file.filename.endswith('.zip'):
            lang = "zip"
            content = file.read()
            zip_content = content

            if len(content) > 200000000:
                flash("Слишком большой файл.", "danger")
                return _return_to_submit_form(default_lang='zip')

            code = extract_data_from_zipfile(content)
            if not code:
                flash("Не удалось прочитать архив.", "danger")
                return _return_to_submit_form(default_lang='zip')

        if file.filename.endswith('.ipynb'):
            code = file.read().decode('utf-8')
            lang = "ipynb"

    if github_repo_url:
        if task and task.lang != 'github':
            flash("Ссылка на GitHub разрешена только для задач с типом сдачи github.", "danger")
            return _return_to_submit_form(default_lang='github')
        if task and task.check_type != 'gpt':
            flash("Ссылка на GitHub поддерживается только для задач с проверкой через нейросеть (GPT).", "danger")
            return _return_to_submit_form(default_lang='github')
        try:
            code = extract_data_from_github_repository(github_repo_url)
            lang = "github"
        except GitHubRepositoryError as e:
            flash(str(e), "danger")
            return _return_to_submit_form(default_lang='github')

    if task and task.lang == 'github' and not github_repo_url:
        flash("Для этой задачи нужно отправить ссылку на GitHub-репозиторий.", "danger")
        return _return_to_submit_form(default_lang='github')

    if not code or not str(code).strip():
        flash("Введите код.", "danger")
        return _return_to_submit_form()

    if not lang or lang not in LANGS + ['ipynb', 'zip', 'github']:
        flash("Выберите язык.", "danger")
        return _return_to_submit_form()

    if task:
        # Проверка лимита для GPT-задач
        if task.check_type == 'gpt':
            allowed, current_count, limit = check_gpt_rate_limit(session['user_id'], task_id, task)
            if not allowed:
                flash(f"Превышен лимит сдач для этой задачи ({limit} в час). Попробуйте позже.", "danger")
                return _return_to_submit_form()

    id = save_code(code, lang, client_ip, user_id=session['user_id'], task_id=task_id, course_id=course_id)
    if lang == 'zip' and zip_content:
        save_original_zip_archive(id, zip_content)

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
    return session.get('role') in ['teacher', 'admin']


def is_admin():
    return session.get('role') == 'admin'


def is_author(code):
    return code and code.user_id == session.get('user_id')


def _short_text(value, limit=220):
    text = '' if value is None else str(value)
    return text if len(text) <= limit else text[:limit - 3] + '...'


def _normalize_celery_task_item(task_item):
    if not isinstance(task_item, dict):
        return None

    source = task_item.get('request') if isinstance(task_item.get('request'), dict) else task_item
    if not isinstance(source, dict):
        return None

    argsrepr = source.get('argsrepr')
    if argsrepr is None:
        raw_args = source.get('args')
        if isinstance(raw_args, str):
            argsrepr = raw_args
        elif raw_args is None:
            argsrepr = ''
        else:
            argsrepr = json.dumps(raw_args, ensure_ascii=False)

    kwargsrepr = source.get('kwargsrepr')
    if kwargsrepr is None:
        raw_kwargs = source.get('kwargs')
        if isinstance(raw_kwargs, str):
            kwargsrepr = raw_kwargs
        elif raw_kwargs is None:
            kwargsrepr = ''
        else:
            kwargsrepr = json.dumps(raw_kwargs, ensure_ascii=False)

    return {
        'id': source.get('id') or '',
        'name': source.get('name') or '',
        'args': _short_text(argsrepr),
        'kwargs': _short_text(kwargsrepr),
        'eta': task_item.get('eta') or source.get('eta') or '',
        'time_start': source.get('time_start') or '',
        'hostname': source.get('hostname') or '',
    }


def _normalize_celery_task_list(task_list):
    normalized = []
    for task_item in task_list or []:
        task_data = _normalize_celery_task_item(task_item)
        if task_data:
            normalized.append(task_data)
    return normalized


def _collect_celery_queue_snapshot():
    inspector = celery.control.inspect(timeout=1.5)

    active_raw = inspector.active() or {}
    reserved_raw = inspector.reserved() or {}
    scheduled_raw = inspector.scheduled() or {}
    stats_raw = inspector.stats() or {}

    worker_names = sorted(set(active_raw.keys()) | set(reserved_raw.keys()) | set(scheduled_raw.keys()) | set(stats_raw.keys()))
    workers = []
    total_active = 0
    total_reserved = 0
    total_scheduled = 0

    for worker_name in worker_names:
        active = _normalize_celery_task_list(active_raw.get(worker_name))
        reserved = _normalize_celery_task_list(reserved_raw.get(worker_name))
        scheduled = _normalize_celery_task_list(scheduled_raw.get(worker_name))
        worker_stats = stats_raw.get(worker_name) or {}
        pool = worker_stats.get('pool') or {}

        total_active += len(active)
        total_reserved += len(reserved)
        total_scheduled += len(scheduled)

        workers.append({
            'name': worker_name,
            'active_count': len(active),
            'reserved_count': len(reserved),
            'scheduled_count': len(scheduled),
            'pool_max_concurrency': pool.get('max-concurrency'),
            'active': active,
            'reserved': reserved,
            'scheduled': scheduled,
        })

    return {
        'fetched_at': datetime.utcnow().isoformat() + 'Z',
        'worker_count': len(workers),
        'totals': {
            'active': total_active,
            'reserved': total_reserved,
            'scheduled': total_scheduled,
        },
        'workers': workers,
    }


def _collect_recent_checks_snapshot(limit=40):
    raw_items = redis_client.lrange(SYSTEM_RECENT_CHECKS_KEY, 0, max(limit - 1, 0))
    events = []
    for raw_item in raw_items:
        try:
            event = json.loads(raw_item)
        except Exception:
            continue
        if isinstance(event, dict):
            events.append(event)

    return {
        'fetched_at': datetime.utcnow().isoformat() + 'Z',
        'count': len(events),
        'events': events,
    }


def _can_access_code_realtime(code):
    if not code:
        return False

    if code.available_without_auth:
        return True

    if not session.get('user_id'):
        return False

    if code.task and not (is_teacher() or is_author(code)):
        return False

    return True


@socketio.on('connect')
def handle_socket_connect():
    code_id = (request.args.get('code_id') or '').strip()
    if not code_id:
        return False

    code = get_code(code_id)
    if not _can_access_code_realtime(code):
        return False

    join_room(_submission_room(code_id))
    emit('submission_status_updated', build_submission_status_payload(code))


def _submission_to_diff_text(code):
    if not code:
        return ''

    raw_code = code.code or ''

    if code.lang == 'zip':
        try:
            files = json.loads(raw_code)
        except Exception:
            return raw_code

        lines = []
        for file_item in files:
            file_name = file_item.get('name') or 'unknown'
            lines.append(f"# FILE: {file_name}")
            if file_item.get('is-binary'):
                lines.append(f"[BINARY FILE] {file_item.get('content', '')}")
            else:
                lines.append(file_item.get('content') or '')
            lines.append('')

        return '\n'.join(lines).strip()

    if code.lang == 'github':
        try:
            payload = json.loads(raw_code)
            files = payload.get('files', [])
            repo_label = payload.get('resolved_repo') or payload.get('repo_url') or 'unknown'
            ref = payload.get('ref') or 'unknown'
        except Exception:
            return raw_code

        lines = [f"# GITHUB: {repo_label} ({ref})", ""]
        for file_item in files:
            file_name = file_item.get('name') or 'unknown'
            lines.append(f"# FILE: {file_name}")
            if file_item.get('is-binary'):
                lines.append(f"[BINARY FILE] {file_item.get('content', '')}")
            else:
                lines.append(file_item.get('content') or '')
            lines.append('')

        return '\n'.join(lines).strip()

    if code.lang == 'ipynb':
        extracted_code = extract_code_from_ipynb(raw_code)
        return extracted_code or raw_code

    return raw_code


def _build_attempts_context(code, compare_to_id=None):
    if not code or not code.task_id or not code.user_id:
        return [], None, None

    attempts = (Code.query
                .filter_by(task_id=code.task_id, user_id=code.user_id)
                .order_by(Code.created_at.asc(), Code.id.asc())
                .all())

    if len(attempts) <= 1:
        return attempts, None, None

    current_attempt_idx = next((idx for idx, attempt in enumerate(attempts) if attempt.id == code.id), None)
    if current_attempt_idx is None:
        return attempts, None, None

    compare_attempt = None
    if compare_to_id:
        compare_attempt = next((attempt for attempt in attempts
                                if attempt.id == compare_to_id and attempt.id != code.id), None)

    if compare_attempt is None and current_attempt_idx > 0:
        compare_attempt = attempts[current_attempt_idx - 1]

    if compare_attempt is None:
        return attempts, None, None

    compare_text = _submission_to_diff_text(compare_attempt).splitlines()
    current_text = _submission_to_diff_text(code).splitlines()

    diff_lines = list(difflib.unified_diff(
        compare_text,
        current_text,
        fromfile=f'Попытка {compare_attempt.id}',
        tofile=f'Попытка {code.id}',
        lineterm=''
    ))

    if not diff_lines:
        return attempts, compare_attempt, 'Изменений не найдено.'

    return attempts, compare_attempt, '\n'.join(diff_lines)


def _queue_mass_recheck(task_id):
    code_ids = [code_id for code_id, in db.session.query(Code.id).filter_by(task_id=task_id).all()]
    if not code_ids:
        return 0

    (Code.query
     .filter_by(task_id=task_id)
     .update({
        Code.check_state: 'not checked',
        Code.check_points: 0,
        Code.check_comments: None,
        Code.checked_at: None
    }, synchronize_session=False))
    db.session.commit()

    for code_id in code_ids:
        socketio.emit('submission_status_updated', {
            'code_id': code_id,
            'check_state': 'not checked',
            'check_points': 0,
            'check_comments': '',
            'is_terminal': False,
            'is_success': False,
        }, room=_submission_room(code_id))
        check_task.delay(code_id)

    return len(code_ids)


def _parse_page_arg(arg_name='page', default=1):
    try:
        page = int(request.args.get(arg_name, default))
        if page < 1:
            page = default
    except Exception:
        page = default
    return page


@app.route('/warnings', methods=['GET'])
@login_required
def warnings():
    if not is_teacher():
        abort(403)

    page = _parse_page_arg('page', 1)
    per_page = 50
    warning_type = request.args.get('type', 'similarity')  # similarity or ai

    if warning_type == 'ai':
        base_query = Code.query.filter_by(has_ai_warning=True)
    else:
        base_query = Code.query.filter_by(has_similarity_warning=True)

    query = (base_query
             .outerjoin(Task)
             .filter(or_(Code.task_id.is_(None), Code.check_points == Task.points))
             .order_by(Code.created_at.desc()))

    total = query.count()
    codes = query.offset((page - 1) * per_page).limit(per_page).all()
    has_prev = page > 1
    has_next = page * per_page < total

    return render_template('similarity_warnings.html',
                           codes=codes,
                           user_url=USER_URL,
                           task_url=TASK_URL,
                           warning_type=warning_type,
                           page=page,
                           has_prev=has_prev,
                           has_next=has_next,
                           total=total,
                           per_page=per_page)


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

    page = request.args.get('page')
    if page and page.isdigit():
        return redirect(f'/warnings?type={warning_type}&page={page}')
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
            similarities_page = _parse_page_arg('similarities_page', 1)
            similarities_per_page = 20
            similarities_total = 0
            similarities_has_prev = False
            similarities_has_next = False
            attempts = []
            compare_attempt = None
            attempts_diff = None
            github_meta = None
            if session.get('user_id') and is_teacher():
                all_similarities = code.get_similar_codes_sorted()
                similarities_total = len(all_similarities)
                start_idx = (similarities_page - 1) * similarities_per_page
                end_idx = start_idx + similarities_per_page
                similarities = all_similarities[start_idx:end_idx]
                similarities_has_prev = similarities_page > 1
                similarities_has_next = similarities_page * similarities_per_page < similarities_total
                compare_to_id = request.args.get('compare_to')
                attempts, compare_attempt, attempts_diff = _build_attempts_context(code, compare_to_id)
            elif not session.get('user_id') or not is_author(code):
                add_view(code)
            else:
                compare_to_id = request.args.get('compare_to')
                attempts, compare_attempt, attempts_diff = _build_attempts_context(code, compare_to_id)

            if code.lang == 'zip':
                code.code = json.loads(code.code)
            elif code.lang == 'github':
                try:
                    github_payload = json.loads(code.code)
                    code.code = github_payload.get('files', [])
                    github_meta = {
                        'repo_url': github_payload.get('repo_url'),
                        'resolved_repo': github_payload.get('resolved_repo'),
                        'ref': github_payload.get('ref')
                    }
                except Exception:
                    pass

            return render_template(
                'code.html',
                code=code,
                similarities=similarities,
                user_url=USER_URL,
                task_url=TASK_URL,
                attempts=attempts,
                compare_attempt=compare_attempt,
                attempts_diff=attempts_diff,
                github_meta=github_meta,
                similarities_page=similarities_page,
                similarities_has_prev=similarities_has_prev,
                similarities_has_next=similarities_has_next,
                similarities_total=similarities_total
            )

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
            original_zip = load_original_zip_archive(code.id)
            response = make_response(original_zip if original_zip is not None else rebuild_zip(code))
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

    page = _parse_page_arg('page', 1)

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
    page = _parse_page_arg('page', 1)

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
    socketio.emit('submission_status_updated', build_submission_status_payload(code), room=_submission_room(code.id))

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


@app.route('/api/admin/celery_queue', methods=['GET'])
@login_required
def admin_celery_queue_api():
    if not is_admin():
        abort(403)

    try:
        return jsonify(_collect_celery_queue_snapshot())
    except Exception as e:
        return jsonify({'error': f'Не удалось получить состояние Celery: {str(e)}'}), 503


@app.route('/api/admin/recent_checks', methods=['GET'])
@login_required
def admin_recent_checks_api():
    if not is_admin():
        abort(403)

    try:
        limit = int(request.args.get('limit', '40'))
    except Exception:
        limit = 40
    limit = max(1, min(limit, 100))

    try:
        return jsonify(_collect_recent_checks_snapshot(limit))
    except Exception as e:
        return jsonify({'error': f'Не удалось получить список проверок: {str(e)}'}), 503


@app.route('/system/status', methods=['GET'])
@login_required
def system_status():
    if not is_admin():
        abort(403)
    return render_template('system_status.html')


@app.route('/tasks', methods=['GET'])
@login_required
def tasks_list():
    if not is_teacher():
        abort(403)
    page = _parse_page_arg('page', 1)
    per_page = 50
    search_query = (request.args.get('q') or '').strip()

    query = Task.query
    if search_query:
        like_query = f'%{search_query}%'
        filters = [
            Task.name.ilike(like_query),
            Task.lang.ilike(like_query),
            Task.check_type.ilike(like_query),
            Task.gpt_model.ilike(like_query),
        ]
        if search_query.isdigit():
            filters.append(Task.id == int(search_query))
        query = query.filter(or_(*filters))

    query = query.order_by(Task.id.desc())
    total = query.count()
    tasks = query.offset((page - 1) * per_page).limit(per_page).all()

    current_list_url = f'/tasks?page={page}'
    if search_query:
        current_list_url += f'&q={quote(search_query)}'

    def _page_url(target_page):
        url = f'/tasks?page={target_page}'
        if search_query:
            url += f'&q={quote(search_query)}'
        return url

    return render_template('tasks.html',
                           tasks=tasks,
                           page=page,
                           has_prev=page > 1,
                           has_next=page * per_page < total,
                           total=total,
                           per_page=per_page,
                           search_query=search_query,
                           new_task_url=f"/tasks/new?next={quote(current_list_url, safe='')}",
                           prev_page_url=_page_url(page - 1),
                           next_page_url=_page_url(page + 1),
                           current_list_url=current_list_url,
                           current_list_url_encoded=quote(current_list_url, safe=''))


@app.route('/tasks/<int:task_id>', methods=['GET'])
@login_required
def tasks_edit_legacy(task_id):
    if not is_teacher():
        abort(403)
    next_url = (request.args.get('next') or '').strip()
    if not (next_url.startswith('/tasks') and '\n' not in next_url and '\r' not in next_url):
        page = _parse_page_arg('page', 1)
        search_query = (request.args.get('q') or '').strip()
        next_url = f'/tasks?page={page}'
        if search_query:
            next_url += f'&q={quote(search_query)}'

    return redirect(f"/tasks/{task_id}/edit?next={quote(next_url, safe='')}")


def _safe_next_tasks_url(raw_value):
    if not raw_value:
        return None
    decoded = raw_value.strip()
    if decoded.startswith('/tasks') and '\n' not in decoded and '\r' not in decoded:
        return decoded
    return None


@app.route('/tasks/new', methods=['GET'])
@login_required
def tasks_new():
    if not is_teacher():
        abort(403)
    next_url = _safe_next_tasks_url(request.args.get('next')) or '/tasks'
    return render_template('task_form.html',
                           task=None,
                           langs=LANGS,
                           next_url=next_url)


@app.route('/tasks/<int:task_id>/edit', methods=['GET'])
@login_required
def tasks_edit(task_id):
    if not is_teacher():
        abort(403)
    task = Task.query.get_or_404(task_id)
    next_url = _safe_next_tasks_url(request.args.get('next')) or '/tasks'
    return render_template('task_form.html',
                           task=task,
                           langs=LANGS,
                           next_url=next_url)


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
    next_url = _safe_next_tasks_url(request.form.get('next')) or '/tasks'
    return redirect(next_url)


@app.route('/tasks/<int:task_id>', methods=['POST'])
@login_required
def tasks_update(task_id):
    if not is_teacher():
        abort(403)
    task = Task.query.get_or_404(task_id)
    _fill_task(task)
    db.session.commit()
    flash(f'Задача #{task.id} обновлена.', 'success')

    if 'mass_recheck' in request.form:
        total = _queue_mass_recheck(task.id)
        if total:
            flash(f'Запущена массовая перепроверка: {total} решений по задаче #{task.id}.', 'info')
        else:
            flash(f'Для задачи #{task.id} пока нет решений для перепроверки.', 'warning')

    next_url = _safe_next_tasks_url(request.form.get('next')) or '/tasks'
    return redirect(next_url)


@app.route('/tasks/<int:task_id>/recheck_all', methods=['POST'])
@login_required
def tasks_recheck_all(task_id):
    if not is_teacher():
        abort(403)

    task = Task.query.get_or_404(task_id)
    total = _queue_mass_recheck(task.id)
    if total:
        flash(f'Запущена массовая перепроверка: {total} решений по задаче #{task.id}.', 'info')
    else:
        flash(f'Для задачи #{task.id} пока нет решений для перепроверки.', 'warning')
    return redirect(request.referrer or '/tasks')


@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def tasks_delete(task_id):
    if not is_teacher():
        abort(403)
    task = Task.query.get_or_404(task_id)
    if task.solutions:
        flash(f'Нельзя удалить задачу #{task_id}: есть {len(task.solutions)} решений.', 'danger')
        return redirect(request.referrer or '/tasks')
    db.session.delete(task)
    db.session.commit()
    flash(f'Задача #{task_id} удалена.', 'success')
    return redirect(request.referrer or '/tasks')



# ── External check API (for GeekAuditor) ──────────────────────────────────────

def _verify_service_token():
    """Verify JWT signed with shared JWT_SECRET from Authorization header."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        abort(401)
    token = auth[7:]
    try:
        jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except Exception:
        abort(401)


@app.route('/api/external/check', methods=['POST'])
def external_check():
    _verify_service_token()
    data = request.get_json()
    if not data:
        abort(400)

    required = ('callback_url', 'callback_id', 'code', 'lang')
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400

    check_type = data.get('check_type', 'tests')
    if check_type not in ('tests', 'gpt'):
        return jsonify({'error': 'Invalid check_type. Expected one of: tests, gpt'}), 400

    # External API is used for code checks in GeekExam/GeekCodeBattle MVP.
    # Keep supported languages explicit to fail fast on bad payloads.
    if data.get('lang') not in ('python', 'cpp'):
        return jsonify({'error': 'Invalid lang. Expected one of: python, cpp'}), 400

    check_config = data.get('check_config', {})
    if check_config is None:
        check_config = {}
    if not isinstance(check_config, dict):
        return jsonify({'error': 'Invalid check_config. Expected JSON object'}), 400

    from paste_celery import external_check_task
    job = external_check_task.delay(
        code=data['code'],
        lang=data['lang'],
        task_text=data.get('task_text', ''),
        check_type=check_type,
        check_config=check_config,
        callback_url=data['callback_url'],
        callback_id=data['callback_id'],
    )
    return jsonify({'status': 'queued', 'job_id': job.id})


if __name__ == '__main__':
    socketio.run(app, debug=DEBUG, port=PORT)
