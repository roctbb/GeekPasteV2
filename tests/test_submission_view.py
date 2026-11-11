from copy import deepcopy
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re
from unittest.mock import patch

from flask import Flask
import pytest
from sqlalchemy import event

from io_tests import _report_text
from models import Code, Task, db
import paste_server as server


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.urls = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.append(unescape(dict(attrs)['href']))


@pytest.fixture
def submission_app(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite://')
    db.init_app(app)
    for path, view in [('/', server.index), ('/submission/status', server.submission_status_api),
                       ('/submission/hidden-tests', server.submission_hidden_tests),
                       ('/tasks/<int:task_id>/test-data/<token>', server.tasks_test_data)]:
        app.add_url_rule(path, view_func=view)
    monkeypatch.setattr(server, 'load_user_names', lambda ids: {7: 'Анна'})
    with app.app_context():
        db.create_all()
        task = Task(id=2917, name='Заяц-счетовод', lang='cpp', points=5,
                    check_type='tests', test_mode='io', test_config={'tests': [
                        {'input': 'PUBLIC_INPUT', 'output': '5', 'is_public': True},
                        {'input': 'PRIVATE_INPUT <script>alert(1)</script>',
                         'output': 'PRIVATE_OUTPUT <img src=x>', 'is_public': False},
                        {'input': 'LARGE_START' + 'я' * 100000 + 'LARGE_END',
                         'output': 'EXPECTED_START' + 'x' * 100000 + 'EXPECTED_END', 'is_public': False},
                    ]})
        report = '\n\n'.join([
            'Пройдено тестов: 1 из 3.', 'Тест 1 (публичный): пройден.',
            _report_text('Ввод', 'PUBLIC_INPUT'), _report_text('Ожидаемый вывод', '5'),
            _report_text('Вывод программы', '5'),
            'Тест 2 (приватный): неверный ответ.', 'Тест 3 (приватный): неверный ответ.',
        ])
        db.session.add(Code(id='VIEW', user_id=7, task=task, course_id=163, lang='cpp',
                            code='int main() {}', check_state='partially done',
                            check_points=1, check_comments=report, available_without_auth=True))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def login(client, role, user_id=99):
    with client.session_transaction() as state:
        state.clear()
        if user_id is not None:
            state['user_id'] = user_id
        if role:
            state['role'] = role


@pytest.mark.parametrize('role,user_id', [(None, None), ('student', 7), ('student', 99),
                                        ('teacher', 99), ('admin', 99)])
def test_submission_title_and_private_data_absence_on_initial_page(submission_app, role, user_id):
    client = submission_app.test_client()
    login(client, role, user_id)
    response = client.get('/?id=VIEW')
    assert response.status_code == 200
    assert '<title>Заяц-счетовод — GeekPaste</title>' in response.text
    assert 'id="submission-title">Заяц-счетовод</h1>' in response.text
    assert 'Сдача #VIEW' in response.text
    assert ('data-hidden-tests-url=' in response.text) == (role in ('teacher', 'admin'))
    assert 'PRIVATE_INPUT' not in response.text
    assert 'PRIVATE_OUTPUT' not in response.text
    assert 'LARGE_START' not in response.text
    assert 'EXPECTED_START' not in response.text
    if role not in ('teacher', 'admin'):
        assert '/submission/hidden-tests' not in response.text


def test_teacher_initial_page_keeps_stress_inputs_deferred(submission_app):
    client = submission_app.test_client()
    login(client, 'teacher')
    db.session.expire_all()
    queries = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)
    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        assert client.get('/?id=VIEW').status_code == 200
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)
    assert not any('test_config' in sql for sql in queries)


def test_title_is_escaped_and_unnamed_or_standalone_pastes_have_fallback(submission_app):
    client = submission_app.test_client()
    login(client, 'student', 7)
    code = db.session.get(Code, 'VIEW')
    code.task.name = 'Заяц <script>alert(1)</script>'
    db.session.commit()
    response = client.get('/?id=VIEW')
    assert 'Заяц &lt;script&gt;alert(1)&lt;/script&gt;' in response.text
    assert '<script>alert(1)</script>' not in response.text
    code.task.name = None
    db.session.commit()
    assert 'id="submission-title">Сдача #VIEW</h1>' in client.get('/?id=VIEW').text
    code.task = None
    db.session.commit()
    response = client.get('/?id=VIEW')
    assert 'id="submission-title">Сдача #VIEW</h1>' in response.text
    assert 'data-hidden-tests-url=' not in response.text


@pytest.mark.parametrize('role,user_id', [(None, None), ('student', 7), ('student', 99), ('teacher', None)])
def test_private_endpoint_denies_students_and_anonymous_even_for_public_code(submission_app, role, user_id):
    client = submission_app.test_client()
    login(client, role, user_id)
    with patch.object(server, 'get_code') as lookup:
        response = client.get('/submission/hidden-tests?id=VIEW')
    assert response.status_code == 403
    lookup.assert_not_called()
    assert 'PRIVATE_INPUT' not in response.text


@pytest.mark.parametrize('role', ['teacher', 'admin'])
def test_teacher_private_test_previews_are_escaped_bounded_and_read_only(submission_app, role):
    client = submission_app.test_client()
    login(client, role)
    with patch.object(server.check_task, 'delay') as grade:
        response = client.get('/submission/hidden-tests?id=VIEW')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'private, no-store'
    html = response.json['test_results_html']
    assert 'PRIVATE_INPUT &lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert 'PRIVATE_OUTPUT &lt;img src=x&gt;' in html
    assert '<script>' not in html and '<img' not in html
    assert 'PUBLIC_INPUT' in html  # One table preserves the public rows too.
    assert 'LARGE_START' in html and 'LARGE_END' not in html
    assert 'EXPECTED_START' in html and 'EXPECTED_END' not in html
    assert 'Скачать полностью' in html
    assert 'Не сохранён' in html
    assert len(response.data) < 30000
    assert re.search(r'>2<span', html) and re.search(r'>3<span', html)
    grade.assert_not_called()
    code = db.session.get(Code, 'VIEW')
    assert (code.check_state, code.check_points) == ('partially done', 1)
    public = client.get('/submission/status?id=VIEW')
    assert public.status_code == 200
    assert 'PRIVATE_INPUT' not in public.text and 'LARGE_START' not in public.text


def test_full_download_uses_original_case_index_and_existing_role_guard(submission_app):
    client = submission_app.test_client()
    login(client, 'teacher')
    urls = Links(client.get('/submission/hidden-tests?id=VIEW').json['test_results_html']).urls
    assert len(urls) == 2
    expected = db.session.get(Task, 2917).test_config['tests'][2]['input']
    response = client.get(urls[0])
    assert response.status_code == 200
    assert response.data.decode() == expected
    assert response.headers['Cache-Control'] == 'private, no-store'
    login(client, 'student', 7)
    assert client.get(urls[0]).status_code == 403
    login(client, 'teacher')
    task = db.session.get(Task, 2917)
    config = deepcopy(task.test_config)
    config['tests'][2]['input'] = 'CHANGED'
    task.test_config = config
    db.session.commit()
    assert client.get(urls[0]).status_code == 409


def test_missing_unsupported_and_changed_private_tests(submission_app):
    client = submission_app.test_client()
    login(client, 'teacher')
    assert client.get('/submission/hidden-tests?id=missing').status_code == 404
    task = db.session.get(Task, 2917)
    task.test_config = {'tests': [{'input': 'PUBLIC', 'output': '5', 'is_public': True}]}
    db.session.commit()
    response = client.get('/submission/hidden-tests?id=VIEW')
    assert response.status_code == 409  # The saved report no longer matches private fixtures.
    task.test_mode = 'environment'
    db.session.commit()
    assert client.get('/submission/hidden-tests?id=VIEW').status_code == 404
