"""Teacher review requests; this never queues another automatic grading run."""
import time

import jwt
import requests

from config import APP_URL, JWT_SECRET, SUBMIT_URL


def codingprojects_recheck(code, comment=None):
    now = int(time.time())
    token = jwt.encode({
        'purpose': 'solution-recheck', 'aud': 'codingprojects',
        'iat': now, 'exp': now + 60,
        'user_id': code.user_id, 'task_id': code.task_id,
        'course_id': code.course_id, 'solution': APP_URL + f'/?id={code.id}',
    }, JWT_SECRET, algorithm='HS256')
    payload = {'token': token}
    if comment is not None:
        payload['comment'] = comment
    endpoint = '/recheck/status' if comment is None else '/recheck'
    response = requests.post(SUBMIT_URL.rstrip('/') + endpoint, json=payload,
                             headers={'Accept': 'application/json'}, timeout=(3, 10))
    if response.status_code == 404:
        return {'state': 'not_found', 'available': False, 'requested': False,
                'message': 'Результат ещё не появился в CodingProjects. Попробуйте чуть позже.'}, 404
    if response.status_code in (200, 409):
        data = response.json()
        if data.get('state') == 'ok' and isinstance(data.get('requested'), bool):
            return data, response.status_code
    raise ValueError('CodingProjects recheck API unavailable')
