import requests
import time
import jwt
from celery import Celery
import checker
from config import *
from methods import *
from manage import app
from datetime import datetime

celery = Celery('app', broker=CELERY_BROKER)
celery.conf.task_default_queue = 'paste_queue'
celery.conf.worker_max_tasks_per_child = 100 # Restart worker after 1000 tasks
celery.conf.worker_prefetch_multiplier = 1  # Reduce prefetching


def _make_callback_service_token():
    payload = {'service': 'geekpaste', 'iat': int(time.time())}
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')




@celery.task()
def save_similarities(id):
    with app.app_context():
        code = get_code(id)

        if not code or not code.user_id or code.similarity_checked:
            return

        if code.task and code.task.bypass_similarity_check:
            return

        # Use yield_per to avoid loading all records into memory at once
        query = Code.query.filter(Code.user_id.isnot(None), Code.user_id != code.user_id)

        current_code = code.code
        if code.lang == 'ipynb':
            current_code = extract_code_from_ipynb(code.code)

        # Collect all similarities above threshold for summary notification
        found_similarities = []

        # Process in batches to avoid memory overflow
        for alternative in query.yield_per(100):
            alternative_code = alternative.code
            if alternative.lang == 'ipynb':
                alternative_code = extract_code_from_ipynb(alternative.code)

            n = checker.similarity(current_code, alternative_code)

            if n >= SIMILARITY_LEVEL:
                # Save similarity without sending individual notification
                save_similarity(code, alternative, n, send_notification=False)
                found_similarities.append((alternative, n))

        # Send single summary notification for all similarities
        if found_similarities:
            send_similarity_summary_notification(code, found_similarities)

        code.similarity_checked = True
        db.session.commit()

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
        result = {
            'callback_id': callback_id,
            'job_id': self.request.id,
            'status': 'error',
            'points': 0,
            'max_points': 1,
            'comment': '',
            'details': []
        }
        print(check_config, check_type)
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
                    if lang != 'brainfuck':
                        del container
                result.update({'status': 'success', 'points': passed, 'max_points': max_points,
                                'comment': f'{passed} из {max_points} тестов пройдено', 'details': details})

            elif check_type == 'gpt':
                from methods import get_payload, parse_gpt_answer
                from config import GPT_KEY, GPT_GATEWAY, GPT_MODEL
                answer_text = check_config.get('answer', '')
                max_points = check_config.get('max_points', 10)
                prompt_extra = check_config.get('prompt', '')
                context = get_payload(task_text + ('\n\nЭталонный ответ: ' + answer_text if answer_text else '') + ('\n\n' + prompt_extra if prompt_extra else ''), code, max_points, lang)
                input_messages = [{"role": m["role"], "content": m["content"]} for m in context]
                resp = requests.post(GPT_GATEWAY, json={"token": GPT_KEY, "model": GPT_MODEL, "input": input_messages}, timeout=60)
                resp.raise_for_status()
                resp_data = resp.json()
                message = next(item for item in resp_data['result']['output'] if item['type'] == 'message')
                gpt_text = message['content'][0]['text']
                points, comment, _ = parse_gpt_answer(gpt_text)
                result.update({'status': 'success', 'points': min(points, max_points), 'max_points': max_points, 'comment': comment})

        except Exception as e:
            result['comment'] = str(e)
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
        except Exception as e:
            app.logger.exception(
                "external_check_callback_failed callback_id=%s job_id=%s error=%s",
                callback_id,
                result.get('job_id'),
                str(e),
            )
