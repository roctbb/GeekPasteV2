import requests
from celery import Celery
import checker
from config import *
from methods import *
from manage import app
from datetime import datetime

celery = Celery('app', broker=CELERY_BROKER)
celery.conf.task_default_queue = 'paste_queue'




@celery.task()
def save_similarities(id):
    with app.app_context():
        code = get_code(id)

        if not code or not code.user_id or code.similarity_checked:
            return

        if code.task and code.task.bypass_similarity_check:
            return

        all_codes = Code.query.filter(Code.user_id.isnot(None), Code.user_id != code.user_id).all()

        current_code = code.code
        if code.lang == 'ipynb':
            current_code = extract_code_from_ipynb(code.code)

        # Collect all similarities above threshold for summary notification
        found_similarities = []

        for alternative in all_codes:
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
