import re

import pytest

from paste_server import app


@pytest.fixture
def client():
    return app.test_client()


def login(client, role='student'):
    with client.session_transaction() as session:
        session['user_id'] = 42
        session['role'] = role
        session['ai_settings_csrf'] = 'old-settings-token'


@pytest.mark.parametrize('role', ['student', 'teacher', 'admin'])
def test_nav_logout_clears_session_and_does_not_automatically_log_back_in(client, role):
    login(client, role)
    page = client.get('/')
    assert page.status_code == 200
    form = re.search(r'<form\b[^>]*action="/logout"[^>]*>(.*?)</form>', page.text, re.S)
    assert form is not None
    token = re.search(r'name="csrf_token" value="([^"]+)"', form.group(1)).group(1)
    response = client.post('/logout', data={'csrf_token': token}, follow_redirects=True)
    assert len(response.history) == 1
    assert response.history[0].status_code == 303
    assert response.request.path == '/logged-out'
    assert response.status_code == 200
    assert 'Вы вышли из GeekPaste' in response.text
    assert 'action="/logout"' not in response.text
    assert 'no-store' in response.headers['Cache-Control']
    with client.session_transaction() as session:
        assert dict(session) == {}
    assert client.get('/my/submissions').status_code == 302


@pytest.mark.parametrize('token', [None, '', 'wrong-token', 'неверный-токен'])
def test_logout_requires_csrf_and_keeps_session_on_failure(client, token):
    login(client)
    client.get('/')
    response = client.post('/logout', data={} if token is None else {'csrf_token': token})
    assert response.status_code == 403
    with client.session_transaction() as session:
        assert session['user_id'] == 42


def test_get_cannot_log_out_and_missing_session_token_cannot_be_bypassed(client):
    login(client)
    assert client.get('/logout').status_code == 405
    assert client.post('/logout', data={'csrf_token': ''}).status_code == 403
    with client.session_transaction() as session:
        assert session['user_id'] == 42


def test_logged_out_page_is_public_and_login_requires_an_explicit_click(client):
    page = client.get('/logged-out')
    assert page.status_code == 200
    assert 'href="/" class="btn btn-primary">Войти</a>' in page.text
    assert client.post('/logout', follow_redirects=True).status_code == 200
    # The normal login flow remains available from the button.
    assert client.get('/').status_code == 302
    login(client)
    response = client.get('/logged-out')
    assert response.status_code == 302
    assert response.headers['Location'] == '/'
