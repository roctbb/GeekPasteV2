from datetime import datetime, timedelta
import json
from pathlib import Path
import time
from unittest.mock import patch

from flask import Flask, session
import jwt
import pytest
import requests
from werkzeug.exceptions import Forbidden

import manage
from models import Code, Task, db
import paste_server as server
import user_profiles as profiles
from user_profiles import load_user_names, remember_user_name


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(profiles, '_lookup_retry_at', 0)
    monkeypatch.setattr(profiles, 'fetch_user_name', lambda user_id: None)
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root / 'templates'))
    app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite://')
    db.init_app(app)
    app.add_url_rule('/', view_func=server.index)
    app.add_url_rule('/solutions', view_func=server.solutions)
    app.add_url_rule('/warnings', view_func=server.warnings)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def login_token():
    return jwt.encode(
        dict(id=7, role='student', name='Анна Иванова', iat=int(time.time())),
        'test-secret', algorithm='HS256',
    )


def test_signed_login_remembers_and_refreshes_author_name(app):
    with patch.object(manage, 'JWT_SECRET', 'test-secret'), app.test_request_context('/'):
        manage.make_jwt_auth(login_token())
        assert session['user_id'] == 7
        assert load_user_names([7, 8, None, 7]) == {7: 'Анна Иванова'}
        updated = jwt.encode(dict(id=7, role='student', name='Анна Петрова', iat=int(time.time())),
                             'test-secret', algorithm='HS256')
        manage.make_jwt_auth(updated)
        assert load_user_names([7]) == {7: 'Анна Петрова'}


@pytest.mark.parametrize('name', [None, '', '   ', {'name': 'invalid'}])
def test_legacy_tokens_and_missing_names_do_not_erase_known_names(app, name):
    remember_user_name(7, 'Анна Иванова')
    claims = dict(id=7, role='student', iat=int(time.time()))
    if name is not None:
        claims['name'] = name
    token = jwt.encode(claims, 'test-secret', algorithm='HS256')
    with patch.object(manage, 'JWT_SECRET', 'test-secret'), app.test_request_context('/'):
        manage.make_jwt_auth(token)
        assert session['user_id'] == 7
    assert load_user_names([7]) == {7: 'Анна Иванова'}


@pytest.mark.parametrize('secret,age', [('wrong-secret', 0), ('test-secret', 30)])
def test_untrusted_or_expired_token_cannot_change_author_name(app, secret, age):
    remember_user_name(7, 'Анна Иванова')
    token = jwt.encode(dict(id=7, role='student', name='Подмена', iat=int(time.time()) - age),
                       secret, algorithm='HS256')
    with patch.object(manage, 'JWT_SECRET', 'test-secret'), app.test_request_context('/'):
        with pytest.raises(Forbidden):
            manage.make_jwt_auth(token)
        assert 'user_id' not in session
    assert load_user_names([7]) == {7: 'Анна Иванова'}


def test_saved_name_is_used_for_existing_solutions_and_unknown_authors_have_fallback(app):
    task = Task(id=1, name='Задача', lang='python', points=10, check_type='tests')
    db.session.add(task)
    for code_id, user_id, age in [('OLD', 7, 2), ('NEW', 7, 1), ('OTHER', 8, 0)]:
        db.session.add(Code(id=code_id, user_id=user_id, task=task, course_id=1,
                            lang='python', code='print(1)', check_state='done', check_points=10,
                            created_at=datetime.now() - timedelta(days=age)))
    db.session.commit()
    # Profiles arrive after submissions: older rows need no backfill.
    remember_user_name(7, 'Анна <Иванова>')
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(user_id=99, role='teacher')
    listing = client.get('/solutions?filter=all')
    assert listing.status_code == 200
    assert listing.text.count('Анна &lt;Иванова&gt;') == 2
    assert 'Пользователь #8' in listing.text
    assert '<Иванова>' not in listing.text
    detail = client.get('/?id=NEW')
    assert detail.status_code == 200
    assert 'Анна &lt;Иванова&gt;' in detail.text
    assert 'Сравнение с попыткой #OLD' in detail.text


def test_empty_name_lookup_needs_no_database(app):
    with patch.object(db.session, 'execute') as execute:
        assert load_user_names([None]) == {}
        execute.assert_not_called()


def test_old_submissions_resolve_and_cache_names_without_author_login(app):
    with patch.object(profiles, 'fetch_user_name', return_value='  Анна   Иванова  ') as fetch:
        assert load_user_names([7, 7]) == {7: 'Анна Иванова'}
        fetch.assert_called_once_with(7)
        assert load_user_names([7]) == {7: 'Анна Иванова'}
        fetch.assert_called_once()
    assert load_user_names([7]) == {7: 'Анна Иванова'}


def test_service_outage_keeps_known_names_and_pauses_remote_lookups(app):
    remember_user_name(7, 'Анна Иванова')
    with patch.object(profiles, 'fetch_user_name', side_effect=requests.Timeout) as fetch:
        assert load_user_names([7, 8, 9]) == {7: 'Анна Иванова'}
        assert load_user_names([7, 8, 9]) == {7: 'Анна Иванова'}
        fetch.assert_called_once_with(8)


def test_name_lookup_happens_before_github_files_are_prepared_for_display(app):
    task = Task(id=1, name='Задача', lang='github', points=10, check_type='tests')
    raw = json.dumps({'repo_url': 'https://github.com/example/project',
                      'files': [{'name': 'main.py', 'content': 'print(1)'}]})
    db.session.add(Code(id='GITHUB', user_id=7, task=task, course_id=2, lang='github',
                        code=raw, check_state='done', check_points=10))
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(user_id=99, role='teacher')
    with patch.object(profiles, 'fetch_user_name', return_value='Анна Иванова'):
        page = client.get('/?id=GITHUB')
    assert page.status_code == 200
    assert 'Анна Иванова' in page.text
    assert 'main.py' in page.text
    db.session.rollback()
    assert db.session.get(Code, 'GITHUB').code == raw
    assert load_user_names([7]) == {7: 'Анна Иванова'}
