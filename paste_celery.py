from celery import Celery
import checker
from config import *
from methods import *
from manage import app

celery = Celery('app', broker=CELERY_BROKER)
celery.conf.task_default_queue = 'paste_queue'


@celery.task()
def save_similarities(id):
    with app.app_context():
        code = get_code(id)

        if not code:
            return

        all_codes = get_all_codes()

        for code2 in all_codes:
            if code2.id == code.id:
                continue

            n = checker.similarity(code.code, code2.code)

            if n > SIMILARITY_LEVEL:
                save_similarity(code, code2, n)

        code.checked = True
        db.session.commit()
