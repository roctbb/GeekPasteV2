import string
import random
import datetime
from sqlalchemy import *
from models import *
from config import *
import requests
from runner import TestExecutor, SolutionException, ExecutionException


def create_id():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def get_code(id):
    return Code.query.filter_by(id=id).first()


def save_code(code, lang, client_ip, id=None, user_id=None, task_id=None, course_id=None):
    if not id:
        while True:
            id = create_id()
            if not get_code(id):
                break

    code = Code(id=id, code=code, lang=lang, ip=client_ip, views=0, user_id=user_id, task_id=task_id,
                checked=False, checked_at=None, check_state=None, check_comments=None, check_points=0,
                course_id=course_id)
    db.session.add(code)
    db.session.commit()

    return id


def get_all_codes(lang=None):
    if not lang:
        return Code.query.all()
    return Code.query.filter_by(lang=lang).all()


def add_view(code):
    code.views += 1
    db.session.commit()


def save_similarity(new_code, similar_code, percent):
    similarity_entry = similarities_table.insert().values(
        code_id=new_code.id,
        code_id2=similar_code.id,
        percent=percent
    )

    db.session.execute(similarity_entry)
    db.session.commit()


def check_task_with_tests(task, code):
    executor = None
    try:
        executor = TestExecutor(code)
        points, comments = executor.perform()

        if points > task.points:
            raise ExecutionException("Too much points")

        if not points:
            points = 1

        code.check_points = points
        code.check_comments = comments

        if code.check_points == task.points:
            code.check_state = 'done'
        else:
            code.check_state = 'partially done'

    except ExecutionException as e:
        code.check_points = 1
        code.check_state = 'execution error'
        code.check_comments = str(e)
    except SolutionException as e:
        code.check_points = 1
        code.check_state = 'solution error'
        code.check_comments = str(e)

    if executor:
        print("deleting executor")
        del executor


def get_payload(task_text, solution_text, max_points):
    payload = [
        {
            "role": "system",
            "content": f"Твоя задача оценить решение задачи по программированию. Оценивай только работоспособность, а не качество кода. Максимальный балл - {max_points}. Если код не запускается или не компилируется, или завершается с ошибкой, ставь 0. Количество баллов кратно 5. На первой строке ответа напиши количество баллов числом. Далее - свой комментарий."
        },
        {
            "role": "user",
            "content": f"Условие задачи:\n{task_text}"
        },
        {
            "role": "user",
            "content": f"Решение ученика:\n{solution_text}"
        }
    ]
    return payload


def parse_gpt_answer(answer):
    try:
        points = int(answer.split('\n')[0])
        comments = '\n'.join(answer.split('\n')[1:])
    except Exception as e:
        points = 1
        comments = str(e)

    return points, comments


def check_task_with_gpt(task, code):
    payload = {
        "token": GPT_KEY,
        "model": GPT_MODEL,
        "context": get_payload(task.text, code.code, task.points)
    }

    try:
        answer = requests.post(GPT_GATEWAY, json=payload)
    except Exception as e:
        code.check_points = 1
        code.check_state = 'execution error'
        code.check_comments = str(e)
        return

    try:
        result = answer.json()
        gpt_answer = result['result']['choices'][0]['message']['content']
    except Exception as e:
        code.check_points = 1
        code.check_state = 'execution error'
        code.check_comments = str(e)
        return

    points, comments = parse_gpt_answer(gpt_answer)
    code.check_points = max(min(points, task.points), 1)
    code.check_comments = comments

    if code.check_points == task.points:
        code.check_state = 'done'
    else:
        code.check_state = 'partially done'
