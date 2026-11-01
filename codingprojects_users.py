"""Fetch a user's display name from the CodingProjects service API."""
import time

import jwt
import requests

from config import JWT_SECRET, SUBMIT_URL


def fetch_user_name(user_id):
    if not JWT_SECRET or not SUBMIT_URL:
        return None
    now = int(time.time())
    token = jwt.encode({
        'purpose': 'user-profile', 'aud': 'codingprojects',
        'iat': now, 'exp': now + 60,
        'user_id': user_id,
    }, JWT_SECRET, algorithm='HS256')
    response = requests.get(
        SUBMIT_URL.rstrip('/') + f'/users/{user_id}',
        headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}'},
        timeout=(2, 3), allow_redirects=False,
    )
    if response.status_code == 404:
        data = response.json()
        if isinstance(data, dict) and data.get('state') == 'not_found':
            return None
    if response.status_code != 200:
        raise ValueError(f'CodingProjects user API returned {response.status_code}')
    data = response.json()
    user = data.get('user') if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get('state') != 'ok' or not isinstance(user, dict) \
            or type(user.get('id')) is not int or user['id'] != user_id \
            or not isinstance(user.get('name'), str) or not user['name'].strip():
        raise ValueError('Invalid CodingProjects user response')
    return user['name']
