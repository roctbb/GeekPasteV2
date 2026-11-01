from unittest.mock import Mock, patch

import jwt
import pytest

import codingprojects_users as api


def test_single_user_lookup_is_signed_and_response_id_is_checked():
    response = Mock(status_code=200)
    response.json.return_value = {'state': 'ok', 'user': {'id': 42, 'name': 'Анна Иванова'}}
    with patch.object(api, 'JWT_SECRET', 'test-secret'), \
            patch.object(api, 'SUBMIT_URL', 'https://cp.test/api/geekpaste'), \
            patch.object(api.requests, 'get', return_value=response) as get:
        assert api.fetch_user_name(42) == 'Анна Иванова'
    args, kwargs = get.call_args
    assert args == ('https://cp.test/api/geekpaste/users/42',)
    token = kwargs['headers']['Authorization'].removeprefix('Bearer ')
    claims = jwt.decode(token, 'test-secret', algorithms=['HS256'], audience='codingprojects')
    assert claims['purpose'] == 'user-profile'
    assert claims['user_id'] == 42
    assert claims['exp'] - claims['iat'] == 60
    assert kwargs['timeout'] == (2, 3)
    assert kwargs['allow_redirects'] is False


@pytest.mark.parametrize('status,data', [
    (500, {}), (401, {}), (404, {}), (200, []),
    (200, {'state': 'ok', 'user': {'id': 99, 'name': 'Другой автор'}}),
    (200, {'state': 'ok', 'user': {'id': 42, 'name': None}}),
    (200, {'state': 'ok', 'user': {'id': 42, 'name': '   '}}),
])
def test_failed_or_mismatched_responses_cannot_supply_a_name(status, data):
    response = Mock(status_code=status)
    response.json.return_value = data
    with patch.object(api, 'JWT_SECRET', 'test-secret'), \
            patch.object(api.requests, 'get', return_value=response), pytest.raises(ValueError):
        api.fetch_user_name(42)


def test_unknown_user_has_no_name():
    response = Mock(status_code=404)
    response.json.return_value = {'state': 'not_found'}
    with patch.object(api, 'JWT_SECRET', 'test-secret'), \
            patch.object(api.requests, 'get', return_value=response):
        assert api.fetch_user_name(42) is None
