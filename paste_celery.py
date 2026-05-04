import requests
import time
import jwt
import os
import json
from celery import Celery
import checker
from config import *
from methods import *
from manage import app, socketio, redis_client
from datetime import datetime

celery = Celery('app', broker=CELERY_BROKER)
CELERY_MAIN_QUEUE = os.getenv('CELERY_MAIN_QUEUE', 'paste_queue')
CELERY_SIMILARITY_QUEUE = os.getenv('CELERY_SIMILARITY_QUEUE', 'similarity_queue')

celery.conf.task_default_queue = CELERY_MAIN_QUEUE
celery.conf.task_routes = {
    'paste_celery.save_similarities': {'queue': CELERY_SIMILARITY_QUEUE},
    'paste_celery.check_task': {'queue': CELERY_MAIN_QUEUE},
    'paste_celery.external_check_task': {'queue': CELERY_MAIN_QUEUE},
}
celery.conf.worker_max_tasks_per_child = 100
celery.conf.worker_max_memory_per_child = 200_000  # 200 MB, then restart
celery.conf.worker_prefetch_multiplier = 1
celery.conf.task_track_started = True

# Reliability mode for delivery from Redis broker:
# - late ack: task is acked only after successful execution
# - reject_on_worker_lost: requeue task if worker process dies mid-task
# - visibility_timeout: prevent early redelivery of long-running checks
celery.conf.task_acks_late = True
celery.conf.task_reject_on_worker_lost = True
celery.conf.broker_transport_options = {
    'visibility_timeout': int(os.getenv('CELERY_VISIBILITY_TIMEOUT', '7200'))
}
SYSTEM_RECENT_CHECKS_KEY = 'system:recent_checks'
SYSTEM_RECENT_CHECKS_LIMIT = int(os.getenv('SYSTEM_RECENT_CHECKS_LIMIT', '200'))


def _make_callback_service_token():
    payload = {'service': 'geekpaste', 'iat': int(time.time())}
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def _submission_room(code_id):
    return f"submission:{code_id}"


def _emit_submission_status(code):
    if not code:
        return
    try:
        socketio.emit(
            'submission_status_updated',
            build_submission_status_payload(code),
            room=_submission_room(code.id),
        )
    except Exception as e:
        app.logger.warning("socket_emit_failed code_id=%s error=%s", getattr(code, 'id', None), str(e))


def _short_text(value, limit=220):
    text = '' if value is None else str(value)
    return text if len(text) <= limit else text[:limit - 3] + '...'


def _push_system_check_event(event_type, payload):
    try:
        event = {
            'type': event_type,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        if payload:
            event.update(payload)
        redis_client.lpush(SYSTEM_RECENT_CHECKS_KEY, json.dumps(event, ensure_ascii=False))
        redis_client.ltrim(SYSTEM_RECENT_CHECKS_KEY, 0, max(SYSTEM_RECENT_CHECKS_LIMIT - 1, 0))
    except Exception as e:
        app.logger.warning("system_check_event_failed type=%s error=%s", event_type, str(e))




@celery.task()
def save_similarities(id):
    with app.app_context():
        code = get_code(id)

        if not code or not code.user_id or code.similarity_checked:
            return

        if code.task and code.task.bypass_similarity_check:
            return

        raw_code = code.code or ''
        raw_size = len(raw_code)
        if raw_size > MAX_SIMILARITY_CODE_SIZE:
            code.similarity_checked = True
            db.session.commit()
            _push_system_check_event('similarity_check', {
                'status': 'skipped_too_large',
                'code_id': code.id,
                'task_id': code.task_id,
                'user_id': code.user_id,
                'code_size': raw_size,
                'code_size_limit': MAX_SIMILARITY_CODE_SIZE,
            })
            db.session.expire_all()
            return

        # Use yield_per to avoid loading all records into memory at once
        query = Code.query.filter(Code.user_id.isnot(None), Code.user_id != code.user_id)

        current_code = raw_code
        if code.lang == 'ipynb':
            current_code = extract_code_from_ipynb(code.code)

        # Collect all similarities above threshold for summary notification
        found_similarities = []

        # Process in batches to avoid memory overflow
        batch_count = 0
        for alternative in query.yield_per(100):
            alternative_code = alternative.code
            if alternative.lang == 'ipynb':
                alternative_code = extract_code_from_ipynb(alternative.code)

            n = checker.similarity(current_code, alternative_code)

            if n >= SIMILARITY_LEVEL:
                save_similarity(code, alternative, n, send_notification=False)
                found_similarities.append((alternative, n))

            batch_count += 1
            if batch_count % 500 == 0:
                db.session.expire_all()
                code = get_code(id)  # re-fetch after expire

        # Send single summary notification for all similarities
        if found_similarities:
            send_similarity_summary_notification(code, found_similarities)

        code.similarity_checked = True
        db.session.commit()
        _push_system_check_event('similarity_check', {
            'status': 'warning' if code.has_similarity_warning else 'clean',
            'code_id': code.id,
            'task_id': code.task_id,
            'user_id': code.user_id,
            'matches_count': len(found_similarities),
            'has_similarity_warning': bool(code.has_similarity_warning),
        })

        # Explicitly clean up session to free memory
        db.session.expire_all()


@celery.task()
def check_task(id):
    with app.app_context():
        code = get_code(id)
        task = code.task

        if not task:
            return

        if task.check_type == 'tests':
            check_task_with_tests(task, code)

        if task.check_type == 'gpt':
            check_task_with_gpt(task, code)

        # Auto-mark as viewed by teacher if bypass flag is set on the task
        if task.bypass_similarity_check and code.check_state == 'done':
            code.viewed_by_teacher = True

        code.checked_at = datetime.now()
        db.session.commit()
        _emit_submission_status(code)
        _push_system_check_event('code_check', {
            'status': code.check_state or '',
            'code_id': code.id,
            'task_id': code.task_id,
            'user_id': code.user_id,
            'check_type': task.check_type if task else '',
            'points': code.check_points or 0,
            'max_points': task.points if task and task.points is not None else None,
            'comments': _short_text(code.check_comments),
        })

        if SUBMIT_URL and code.course_id:
            requests.post(SUBMIT_URL, json={
                "points": code.check_points,
                "comments": code.check_comments,
                "solution": APP_URL + f"/?id={code.id}",
                "course_id": code.course_id,
                "token": generate_jwt(code.user_id, code.task_id)
            })

        # Clean up session
        db.session.expire_all()


@celery.task(bind=True, max_retries=3)
def external_check_task(self, code, lang, task_text, check_type, check_config, callback_url, callback_id):
    """Check code/text submitted from GeekAuditor and send result via callback."""
    with app.app_context():
        def _limit_text(value, limit):
            text = '' if value is None else str(value)
            if len(text) <= limit:
                return text
            return text[:limit]

        result = {
            'callback_id': callback_id,
            'job_id': self.request.id,
            'status': 'error',
            'points': 0,
            'max_points': 1,
            'comment': '',
            'details': []
        }
        app.logger.info(
            "external_check_started callback_id=%s job_id=%s check_type=%s lang=%s",
            callback_id,
            self.request.id,
            check_type,
            lang,
        )
        try:
            if check_type == 'tests':
                tests = check_config.get('tests', [])
                max_points = len(tests) if tests else 1
                passed = 0
                details = []

                if lang == 'brainfuck':
                    from runner import BrainfuckExecutor, SolutionException, ExecutionException
                    executor = BrainfuckExecutor(code)
                    run_fn = executor.run
                    container = None
                else:
                    from runner import ExecutionContainer, SolutionException, ExecutionException
                    container = ExecutionContainer(lang, '', code)
                    run_fn = container.run

                try:
                    for t in tests:
                        try:
                            per_test_time_limit = t.get('time_limit', check_config.get('time_limit', 5))
                            output = run_fn(t.get('input', ''), time_limit=per_test_time_limit).strip()
                            expected = str(t.get('expected', '')).strip()
                            ok = output == expected
                            if ok:
                                passed += 1
                            details.append({'input': t.get('input'), 'expected': expected, 'got': output, 'ok': ok})
                        except (SolutionException, ExecutionException) as e:
                            details.append({'input': t.get('input'), 'error': str(e), 'ok': False})
                finally:
                    if container:
                        container.cleanup()
                result.update({'status': 'success', 'points': passed, 'max_points': max_points,
                                'comment': f'{passed} из {max_points} тестов пройдено', 'details': details})

            elif check_type == 'gpt':
                from methods import get_payload, parse_gpt_answer
                from config import GPT_KEY, GPT_GATEWAY, GPT_MODEL
                raw_task_text = task_text or ''
                raw_answer_text = check_config.get('answer', '')
                raw_prompt_extra = check_config.get('prompt', '')
                task_text_limited = _limit_text(raw_task_text, 12000)
                answer_text = _limit_text(raw_answer_text, 120000)
                prompt_extra = _limit_text(raw_prompt_extra, 80000)
                max_points = check_config.get('max_points', 10)
                app.logger.info(
                    "external_check_payload_sizes callback_id=%s job_id=%s task_text=%s answer=%s prompt=%s",
                    callback_id,
                    self.request.id,
                    len(raw_task_text),
                    len(raw_answer_text),
                    len(raw_prompt_extra),
                )
                context = get_payload(task_text_limited + ('\n\nЭталонный ответ: ' + answer_text if answer_text else '') + ('\n\n' + prompt_extra if prompt_extra else ''), code, max_points, lang)
                input_messages = [{"role": m["role"], "content": m["content"]} for m in context]
                resp = requests.post(GPT_GATEWAY, json={"token": GPT_KEY, "model": GPT_MODEL, "input": input_messages}, timeout=60)
                resp.raise_for_status()
                resp_data = resp.json()
                if isinstance(resp_data, dict) and resp_data.get('error'):
                    raise RuntimeError(f"GPT gateway error: {resp_data.get('error')}")
                message = next(item for item in resp_data['result']['output'] if item['type'] == 'message')
                gpt_text = message['content'][0]['text']
                points, comment, _ = parse_gpt_answer(gpt_text)
                result.update({'status': 'success', 'points': min(points, max_points), 'max_points': max_points, 'comment': comment})

        except Exception as e:
            result['comment'] = str(e)
            app.logger.exception(
                "external_check_failed callback_id=%s job_id=%s retry=%s error=%s",
                callback_id,
                self.request.id,
                self.request.retries,
                str(e),
            )
            error_text = str(e).lower()
            if 'request timed out' in error_text or 'read timed out' in error_text or 'connect timeout' in error_text:
                # Upstream timeout is deterministic for oversized/slow requests.
                # Do not spend retries on the same payload.
                pass
            else:
                try:
                    self.retry(countdown=10 * (2 ** self.request.retries))
                    return  # retry scheduled, don't send callback
                except self.MaxRetriesExceededError:
                    pass

        try:
            callback_headers = {'Authorization': f'Bearer {_make_callback_service_token()}'}
            app.logger.info(
                "external_check_callback_start callback_id=%s job_id=%s status=%s callback_url=%s",
                callback_id,
                result.get('job_id'),
                result.get('status'),
                callback_url,
            )
            callback_resp = requests.post(callback_url, json=result, headers=callback_headers, timeout=10)
            app.logger.info(
                "external_check_callback_done callback_id=%s job_id=%s status_code=%s",
                callback_id,
                result.get('job_id'),
                callback_resp.status_code,
            )
            _push_system_check_event('external_api_check', {
                'status': result.get('status') or '',
                'callback_id': callback_id,
                'job_id': result.get('job_id'),
                'check_type': check_type,
                'lang': lang,
                'points': result.get('points'),
                'max_points': result.get('max_points'),
                'comment': _short_text(result.get('comment')),
            })
        except Exception as e:
            app.logger.exception(
                "external_check_callback_failed callback_id=%s job_id=%s error=%s",
                callback_id,
                result.get('job_id'),
                str(e),
            )
            _push_system_check_event('external_api_check', {
                'status': 'error',
                'callback_id': callback_id,
                'job_id': result.get('job_id'),
                'check_type': check_type,
                'lang': lang,
                'points': result.get('points'),
                'max_points': result.get('max_points'),
                'comment': _short_text(result.get('comment') or str(e)),
            })
