from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
import pytest
from sqlalchemy import select, text

import ai_settings
from ai_client import generate_text
from ai_settings import AISettingsError, load_ai_settings, save_ai_settings, reset_ai_settings
from models import AISettings, db
from test_ai_client import SETTINGS, MESSAGES, response_data


@pytest.fixture
def settings_app(tmp_path, monkeypatch):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    app.config.update(SECRET_KEY='test-only-secret-longer-than-32-characters',
                      SQLALCHEMY_DATABASE_URI=f'sqlite:///{tmp_path / "settings.sqlite"}', TESTING=True)
    db.init_app(app)
    monkeypatch.setattr(ai_settings, 'environment_settings', lambda: SETTINGS.copy())
    monkeypatch.setattr(ai_settings.config, 'AI_SETTINGS_ENCRYPTION_KEY', '')
    with app.app_context():
        AISettings.__table__.create(db.engine)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def form(**changes):
    return {key: str(value) for key, value in SETTINGS.items() if key in ai_settings.PUBLIC_FIELDS} | changes


def test_encryption_persistence_and_immediate_switch(settings_app):
    with settings_app.app_context():
        assert load_ai_settings() == SETTINGS
        save_ai_settings(form(provider='openai', openai_key='new-secret', model='new-model'), 7)
        with db.engine.connect() as connection:
            row = connection.execute(select(AISettings.__table__)).one()
            assert row.updated_by == 7
            assert 'new-secret' not in row.encrypted_config
            assert 'openai' not in row.encrypted_config
        assert load_ai_settings()['openai_key'] == 'new-secret'
    # A new context/worker reads saved settings without a process restart.
    with settings_app.app_context(), patch('ai_client.requests.post', return_value=Mock(
            status_code=200, json=response_data)) as post:
        generate_text(MESSAGES)
        assert post.call_args.args == (SETTINGS['openai_url'],)
        assert post.call_args.kwargs['headers']['Authorization'] == 'Bearer new-secret'
        assert post.call_args.kwargs['json']['model'] == 'new-model'
        save_ai_settings(form(provider='gateway'), 7)
        post.return_value.json = lambda: {'result': response_data()}
        generate_text(MESSAGES)
        assert post.call_args.args == (SETTINGS['gateway_url'],)
        assert post.call_args.kwargs['json']['token'] == 'gateway-secret'
        assert 'Authorization' not in post.call_args.kwargs['headers']


def test_keep_clear_inherit_and_reset(settings_app):
    with settings_app.app_context():
        save_ai_settings(form(openai_key='custom', openai_proxy='http://u:p@proxy.example:8080'), 1)
        save_ai_settings(form(openai_key=''), 1)
        assert load_ai_settings()['openai_key'] == 'custom'
        save_ai_settings(form(openai_key_action='clear', openai_proxy_action='clear'), 1)
        assert load_ai_settings()['openai_key'] == ''
        assert load_ai_settings()['openai_proxy'] == ''
        save_ai_settings(form(openai_key_action='inherit', openai_proxy_action='inherit'), 1)
        assert load_ai_settings()['openai_key'] == SETTINGS['openai_key']
        assert load_ai_settings()['openai_proxy'] == SETTINGS['openai_proxy']
        reset_ai_settings()
        assert load_ai_settings() == SETTINGS
        assert not ai_settings.settings_view()['overridden']


@pytest.mark.parametrize('change', [
    {'provider': 'unknown'}, {'model': ''}, {'timeout': '0'}, {'max_output_tokens': 'NaN'},
    {'openai_url': 'https://user:secret@api.example/v1/responses'},
    {'openai_url': 'https://api.example/v1/responses?key=secret'},
    {'gateway_url': 'ftp://example/v1/responses'}, {'gateway_url': 'https://example:99999/api'},
    {'openai_proxy': 'socks4://proxy.example'}, {'gateway_proxy': 'https://proxy.example/path'},
    {'openai_key': 'key\nwith-newline'}, {'gateway_key_action': 'clear'},
    {'openai_key_action': 'invalid'},
])
def test_invalid_settings_are_atomic_and_do_not_echo_values(settings_app, change):
    with settings_app.app_context():
        save_ai_settings(form(), 1)
        before = load_ai_settings()
        with pytest.raises(AISettingsError) as error:
            save_ai_settings(form(**change), 1)
        assert 'secret' not in str(error.value)
        assert load_ai_settings() == before


def test_wrong_key_fails_closed_instead_of_falling_back(settings_app):
    with settings_app.app_context():
        save_ai_settings(form(provider='openai'), 1)
        settings_app.config['SECRET_KEY'] = 'another-secret-longer-than-32-characters'
        with pytest.raises(AISettingsError):
            load_ai_settings()
        reset_ai_settings()
        assert load_ai_settings() == SETTINGS


def test_weak_key_cannot_persist_secrets(settings_app):
    with settings_app.app_context():
        settings_app.config['SECRET_KEY'] = 'weak'
        with pytest.raises(AISettingsError, match='AI_SETTINGS_ENCRYPTION_KEY'):
            save_ai_settings(form(), 1)


def test_missing_table_uses_environment_but_database_failure_does_not(settings_app):
    with settings_app.app_context():
        AISettings.__table__.drop(db.engine)
        assert load_ai_settings() == SETTINGS
        with pytest.raises(AISettingsError, match='миграции'):
            save_ai_settings(form(), 1)
        with db.engine.begin() as connection:
            connection.execute(text('CREATE TABLE ai_settings (id INTEGER PRIMARY KEY)'))
        with patch('ai_client.requests.post') as post:
            with pytest.raises(AISettingsError, match='базы данных'):
                generate_text(MESSAGES)
            post.assert_not_called()


@pytest.fixture
def settings_client(settings_app):
    from paste_server import system_ai_settings
    settings_app.add_url_rule('/system/ai', view_func=system_ai_settings, methods=['GET', 'POST'])
    settings_app.add_url_rule('/system/status', endpoint='system_status', view_func=lambda: '')
    return settings_app.test_client()


def login(client, role='admin'):
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['role'] = role


def test_settings_access_and_csrf(settings_client):
    assert settings_client.get('/system/ai').status_code == 302
    for role in ('student', 'teacher'):
        login(settings_client, role)
        assert settings_client.get('/system/ai').status_code == 403
        assert settings_client.post('/system/ai', data=form()).status_code == 403
    login(settings_client)
    assert settings_client.get('/system/ai').status_code == 200
    assert settings_client.post('/system/ai', data=form()).status_code == 403
    assert settings_client.post('/system/ai', data=form(csrf_token='неверный')).status_code == 403
    assert settings_client.post('/system/ai', data={'action': 'reset'}).status_code == 403
    with settings_client.session_transaction() as session:
        token = session['ai_settings_csrf']
    assert settings_client.post('/system/ai', data=form(csrf_token=token)).status_code == 302


def test_secrets_never_rendered_or_stored_in_session(settings_client, settings_app):
    login(settings_client)
    page = settings_client.get('/system/ai')
    assert 'no-store' in page.headers['Cache-Control']
    for secret in ('gateway-secret', 'openai-secret', 'fixture-user:fixture-password'):
        assert secret not in page.text
    with settings_client.session_transaction() as session:
        token = session['ai_settings_csrf']
    page = settings_client.post('/system/ai', data=form(
        provider='openai', openai_key='replacement-secret', csrf_token=token), follow_redirects=True)
    assert page.status_code == 200
    assert 'replacement-secret' not in page.text
    with settings_client.session_transaction() as session:
        assert 'replacement-secret' not in repr(dict(session))
    page = settings_client.post('/system/ai', data=form(
        openai_key='invalid secret', csrf_token=token))
    assert page.status_code == 400
    assert 'invalid secret' not in page.text
    with settings_app.app_context():
        assert load_ai_settings()['openai_key'] == 'replacement-secret'
    assert settings_client.post('/system/ai', data={'action': 'reset', 'csrf_token': token}).status_code == 302


def test_native_and_external_grading_use_the_saved_openai_connection(settings_app):
    import methods
    import paste_celery
    from test_gpt_connection_retry import submission

    with settings_app.app_context():
        save_ai_settings(form(provider='openai', model='system-model'), 1)
        code = submission()
        code.task.gpt_model = 'task-model'
        reply = Mock(status_code=200, json=response_data)
        with patch('ai_client.requests.post', return_value=reply) as post, \
                patch('methods.send_telegram_message') as notify, \
                patch('methods.analyze_code_for_ai_usage', return_value={'suspicious': False}):
            methods.check_task_with_gpt(code.task, code)
            assert code.check_state == 'done'
            assert post.call_args.args == (SETTINGS['openai_url'],)
            assert post.call_args.kwargs['json']['model'] == 'task-model'
            notify.assert_not_called()
    with patch('paste_celery.app', settings_app), \
            patch('ai_client.requests.post', side_effect=[reply, Mock(status_code=200)]) as post, \
            patch('paste_celery._make_callback_service_token', return_value='test-callback'), \
            patch('paste_celery._push_system_check_event'):
        paste_celery.external_check_task.run(
            code='print(1)', lang='python', task_text='TASK', check_type='gpt',
            check_config={'max_points': 10}, callback_url='https://example.test/callback', callback_id='test')
        assert post.call_args_list[0].args == (SETTINGS['openai_url'],)
        assert post.call_args_list[0].kwargs['json']['model'] == 'system-model'
        assert post.call_args_list[1].kwargs['json']['status'] == 'success'


def test_credential_in_legacy_endpoint_is_not_rendered(settings_client, monkeypatch):
    monkeypatch.setattr(ai_settings, 'environment_settings', lambda: SETTINGS | {
        'gateway_url': 'https://legacy-user:legacy-password@example.test/v1/responses'})
    login(settings_client)
    page = settings_client.get('/system/ai')
    assert page.status_code == 200
    assert 'legacy-password' not in page.text
