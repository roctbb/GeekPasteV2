import requests
from celery import Celery
import checker
from config import *
import jwt
from methods import *
from manage import app
from datetime import datetime

celery = Celery('app', broker=CELERY_BROKER)
celery.conf.task_default_queue = 'paste_queue'


def generate_jwt(user_id, task_id):
    payload = {
        'user_id': user_id,
        'task_id': task_id
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
    return token


@celery.task()
def save_similarities(id):
    with app.app_context():
        code = get_code(id)

        if not code or not code.user_id or code.similarity_checked:
            return

        all_codes = Code.query.filter(Code.user_id.isnot(None), Code.user_id != code.user_id).all()

        for alternative in all_codes:
            n = checker.similarity(code.code, alternative.code)

            if n > SIMILARITY_LEVEL:
                save_similarity(code, alternative, n)
                code.has_similarity_warning = True

                if n > 95:
                    code.has_critical_similarity_warning = True

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


