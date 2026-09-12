import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
import requests
import paste_server as server
import recheck_request as api


class TeacherRecheckTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.code = SimpleNamespace(id='TEST', user_id=42, task_id=12, course_id=7, task=True)
        self.lookup = patch.object(server, 'get_code', return_value=self.code)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def login(self, user=42, role='student'):
        with self.client.session_transaction() as session:
            session['user_id'] = user
            session['role'] = role
            session['recheck_csrf'] = 'test-csrf'

    def test_only_author_can_read_or_request_even_if_teacher_or_public(self):
        with patch.object(server, 'codingprojects_recheck') as remote:
            self.assertEqual(self.client.get('/submission/recheck?id=TEST').status_code, 401)
            for role in ['student', 'teacher', 'admin']:
                self.login(99, role)
                self.assertEqual(self.client.get('/submission/recheck?id=TEST').status_code, 403)
                self.assertEqual(self.client.post('/submission/recheck?id=TEST').status_code, 403)
            remote.assert_not_called()

    def test_csrf_and_comment_validation(self):
        self.login()
        with patch.object(server, 'codingprojects_recheck') as remote:
            self.assertEqual(self.client.post('/submission/recheck?id=TEST', json={'comment': 'Valid comment'}).status_code, 403)
            for comment in ['', 'short', ' ' * 20, 'x' * 1001, None, ['invalid']]:
                response = self.client.post('/submission/recheck?id=TEST', json={'comment': comment}, headers={'X-CSRF-Token': 'test-csrf'})
                self.assertEqual(response.status_code, 422)
            remote.assert_not_called()

    def test_status_and_request_are_forwarded_without_regrading(self):
        self.login()
        with patch.object(server, 'codingprojects_recheck', return_value=({'state': 'ok', 'requested': True}, 200)) as remote, patch.object(server.check_task, 'delay') as grader:
            self.assertEqual(self.client.get('/submission/recheck?id=TEST').status_code, 200)
            remote.assert_called_with(self.code, None)
            response = self.client.post('/submission/recheck?id=TEST', json={'comment': '  Не согласен со вторым критерием  '}, headers={'X-CSRF-Token': 'test-csrf'})
            self.assertEqual(response.status_code, 200)
            remote.assert_called_with(self.code, 'Не согласен со вторым критерием')
            grader.assert_not_called()

    def test_outage_does_not_report_success(self):
        self.login()
        with patch.object(server, 'codingprojects_recheck', side_effect=requests.Timeout):
            response = self.client.get('/submission/recheck?id=TEST')
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json['state'], 'error')

    def test_signed_scope_timeout_and_status_endpoint(self):
        response = Mock(status_code=200)
        response.json.return_value = {'state': 'ok', 'requested': False, 'available': True}
        with patch.object(api, 'JWT_SECRET', 'test-secret'), patch.object(api, 'SUBMIT_URL', 'https://cp.test/api/geekpaste'), patch.object(api, 'APP_URL', 'https://paste.test'), patch.object(api.requests, 'post', return_value=response) as post:
            for comment, path in [(None, '/recheck/status'), ('Проверьте критерий', '/recheck')]:
                api.codingprojects_recheck(self.code, comment)
                args, kwargs = post.call_args
                self.assertEqual(args[0], 'https://cp.test/api/geekpaste' + path)
                claims = jwt.decode(kwargs['json']['token'], 'test-secret', algorithms=['HS256'], audience='codingprojects')
                self.assertEqual(claims['purpose'], 'solution-recheck')
                self.assertEqual((claims['user_id'], claims['task_id'], claims['course_id']), (42, 12, 7))
                self.assertEqual(claims['solution'], 'https://paste.test/?id=TEST')
                self.assertEqual(claims['exp'] - claims['iat'], 60)
                self.assertEqual(kwargs['timeout'], (3, 10))


if __name__ == '__main__':
    unittest.main()
