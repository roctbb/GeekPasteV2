from unittest.mock import Mock, patch

import pytest
import requests

from ai_client import AIRequestError, generate_text
from ai_settings import AISettingsError


SETTINGS = {
    'provider': 'gateway', 'model': 'default-model', 'max_output_tokens': 4096,
    'timeout': 45, 'gateway_url': 'https://gateway.example/v1/responses',
    'gateway_key': 'gateway-secret', 'gateway_proxy': '',
    'openai_url': 'https://api.openai.com/v1/responses',
    'openai_key': 'openai-secret', 'openai_proxy': 'socks5h://fixture-user:fixture-password@proxy.example:1080',
}
MESSAGES = [{'role': 'user', 'content': [
    {'type': 'input_text', 'text': 'Check solution'},
    {'type': 'input_image', 'image_url': 'data:image/png;base64,aGVsbG8='},
]}]


def response_data(text='10\nCorrect'):
    return {'status': 'completed', 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'message', 'status': 'completed', 'content': [
            {'type': 'output_text', 'text': text},
        ]},
    ]}


@pytest.mark.parametrize('provider', ['gateway', 'openai'])
def test_protocol_and_selected_credentials(provider):
    data = response_data()
    reply = Mock(status_code=200)
    reply.json.return_value = {'result': data} if provider == 'gateway' else data
    settings = SETTINGS | {'provider': provider}
    with patch('ai_client.load_ai_settings', return_value=settings), \
            patch('ai_client.requests.post', return_value=reply) as post:
        assert generate_text(MESSAGES, model='task-model') == '10\nCorrect'
    post.assert_called_once()
    assert post.call_args.args == (settings[f'{provider}_url'],)
    kwargs = post.call_args.kwargs
    assert kwargs['timeout'] == 45
    assert kwargs['allow_redirects'] is False
    assert kwargs['proxies'] == {'http': settings[f'{provider}_proxy'], 'https': settings[f'{provider}_proxy']}
    assert kwargs['json']['input'] == MESSAGES
    assert kwargs['json']['model'] == 'task-model'
    if provider == 'openai':
        assert kwargs['headers']['Authorization'] == 'Bearer openai-secret'
        assert kwargs['json']['max_output_tokens'] == 4096
        assert kwargs['json']['store'] is False
        assert 'token' not in kwargs['json'] and 'params' not in kwargs['json']
    else:
        assert 'Authorization' not in kwargs['headers']
        assert kwargs['json']['token'] == 'gateway-secret'
        assert kwargs['json']['params'] == {'max_output_tokens': 4096}


def test_collects_text_after_reasoning_and_uses_default_model():
    data = response_data('10')
    data['output'][1]['content'].append({'type': 'output_text', 'text': 'Correct'})
    data['output'].append({'type': 'message', 'content': [{'type': 'output_text', 'text': 'Details'}]})
    with patch('ai_client.load_ai_settings', return_value=SETTINGS | {'provider': 'openai'}), \
            patch('ai_client.requests.post', return_value=Mock(status_code=200, json=lambda: data)) as post:
        assert generate_text(MESSAGES) == '10\nCorrect\nDetails'
        assert post.call_args.kwargs['json']['model'] == 'default-model'


@pytest.mark.parametrize('data', [
    {'error': {'message': 'secret upstream body'}},
    response_data() | {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}},
    response_data() | {'status': 'failed'},
    {'output': [{'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'secret upstream body'}]}]},
    {'output': [{'type': 'reasoning'}]},
    {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': ''}]}]},
    {'output': [{'type': 'message', 'status': 'in_progress', 'content': [{'type': 'output_text', 'text': '10'}]}]},
    {'output': [{'type': 'message', 'content': 'secret upstream body'}]},
    [],
])
def test_invalid_partial_and_refused_responses_are_not_grades(data):
    with patch('ai_client.load_ai_settings', return_value=SETTINGS | {'provider': 'openai'}), \
            patch('ai_client.requests.post', return_value=Mock(status_code=200, json=lambda: data)) as post:
        with pytest.raises(AIRequestError) as error:
            generate_text(MESSAGES)
        assert 'secret' not in str(error.value)
        post.assert_called_once()  # No fallback to the other provider.


@pytest.mark.parametrize('status', [301, 307, 401, 429, 500])
def test_http_errors_do_not_leak_body_or_follow_redirects(status):
    reply = Mock(status_code=status, text='secret upstream body')
    with patch('ai_client.load_ai_settings', return_value=SETTINGS), \
            patch('ai_client.requests.post', return_value=reply) as post:
        with pytest.raises(AIRequestError, match=f'HTTP {status}') as error:
            generate_text(MESSAGES)
        assert 'secret' not in str(error.value)
        reply.json.assert_not_called()
        post.assert_called_once()


@pytest.mark.parametrize('error, expected', [
    (requests.ReadTimeout('secret URL'), requests.Timeout),
    (requests.exceptions.ProxyError('secret URL'), requests.ConnectionError),
    (ValueError('secret URL'), AIRequestError),
])
def test_network_errors_preserve_retry_category_without_secrets(error, expected):
    with patch('ai_client.load_ai_settings', return_value=SETTINGS), \
            patch('ai_client.requests.post', side_effect=error):
        with pytest.raises(expected) as caught:
            generate_text(MESSAGES)
        assert 'secret' not in str(caught.value)
        assert caught.value.__suppress_context__


def test_missing_key_does_not_send_any_request():
    with patch('ai_client.load_ai_settings', return_value=SETTINGS | {'gateway_key': ''}), \
            patch('ai_client.requests.post') as post:
        with pytest.raises(AISettingsError):
            generate_text(MESSAGES)
        post.assert_not_called()


@pytest.mark.parametrize('provider', ['gateway', 'openai'])
def test_real_request_preparation_ignores_netrc_and_ambient_proxy(provider, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://unwanted-proxy.example:3128')
    monkeypatch.setenv('ALL_PROXY', 'http://unwanted-proxy.example:3128')
    settings = SETTINGS | {'provider': provider, f'{provider}_proxy': ''}
    data = response_data()
    response = requests.Response()
    response.status_code = 200
    response.json = lambda: {'result': data} if provider == 'gateway' else data
    with patch('ai_client.load_ai_settings', return_value=settings), \
            patch('requests.sessions.get_netrc_auth', return_value=('unwanted', 'password')) as netrc, \
            patch('requests.sessions.Session.send', return_value=response) as send:
        assert generate_text(MESSAGES) == '10\nCorrect'
        prepared = send.call_args.args[0]
        expected = 'Bearer openai-secret' if provider == 'openai' else None
        assert prepared.headers.get('Authorization') == expected
        assert requests.utils.select_proxy(prepared.url, send.call_args.kwargs['proxies']) == ''
        netrc.assert_not_called()
