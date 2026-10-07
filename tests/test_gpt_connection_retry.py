from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from celery.exceptions import Retry
import requests

import paste_celery


def submission():
    task = SimpleNamespace(id=2479, text='TASK', points=10, lang='python',
                           gpt_model=None, check_type='gpt',
                           bypass_similarity_check=False, name='Task')
    return SimpleNamespace(id='TEST', task=task, task_id=2479, course_id=None,
                           user_id=None, lang='python', code='print(1)',
                           check_state='checking', check_points=0,
                           check_comments=None, gpt_llm_probability=None,
                           has_ai_warning=False)


def gateway_response():
    response = Mock(status_code=200)
    response.json.return_value = {'result': {'output': [{
        'type': 'message', 'content': [{'text': '10\nВерно.'}],
    }]}}
    return response


class GptConnectionRetryTests(unittest.TestCase):
    def test_native_retries_without_publishing_or_changing_score_then_succeeds(self):
        for error in (requests.ReadTimeout('timeout'), requests.ConnectionError('reset')):
            code = submission()
            with self.subTest(error=type(error).__name__), ExitStack() as stack:
                stack.enter_context(patch('paste_celery.get_code', return_value=code))
                post = stack.enter_context(patch('methods.requests.post', side_effect=[
                    error, error, error, gateway_response()]))
                publish = stack.enter_context(patch('paste_celery._publish_checked_submission'))
                notify = stack.enter_context(patch('methods.send_telegram_message'))
                stack.enter_context(patch('methods.analyze_code_for_ai_usage',
                                          return_value={'suspicious': False}))
                stack.enter_context(patch('methods.db.session'))
                retry = stack.enter_context(patch.object(paste_celery.check_task, 'retry',
                                                         side_effect=Retry()))
                for attempt in range(3):
                    paste_celery.check_task.push_request(retries=attempt)
                    try:
                        with self.assertRaises(Retry):
                            paste_celery.check_task.run(code.id)
                    finally:
                        paste_celery.check_task.pop_request()
                    retry.assert_called_with(exc=error, countdown=5)
                    publish.assert_not_called()
                    notify.assert_not_called()
                    self.assertEqual((code.check_state, code.check_points, code.check_comments),
                                     ('checking', 0, None))
                paste_celery.check_task.push_request(retries=3)
                try:
                    paste_celery.check_task.run(code.id)
                finally:
                    paste_celery.check_task.pop_request()
                self.assertEqual(post.call_count, 4)
                self.assertEqual((code.check_state, code.check_points), ('done', 10))
                publish.assert_called_once_with(code)
                notify.assert_not_called()

    def test_native_exhaustion_and_non_network_errors_publish_final_error(self):
        for retries, error in ((3, requests.ReadTimeout('timeout')), (0, ValueError('bad payload'))):
            code = submission()
            with self.subTest(retries=retries), ExitStack() as stack:
                stack.enter_context(patch('paste_celery.get_code', return_value=code))
                stack.enter_context(patch('methods.requests.post', side_effect=error))
                publish = stack.enter_context(patch('paste_celery._publish_checked_submission'))
                notify = stack.enter_context(patch('methods.send_telegram_message'))
                retry = stack.enter_context(patch.object(paste_celery.check_task, 'retry'))
                paste_celery.check_task.push_request(retries=retries)
                try:
                    paste_celery.check_task.run(code.id)
                finally:
                    paste_celery.check_task.pop_request()
                retry.assert_not_called()
                publish.assert_called_once_with(code)
                notify.assert_called_once()
                self.assertEqual((code.check_state, code.check_points), ('execution error', 1))

    def test_external_connection_failure_retries_before_callback(self):
        for error in (requests.ReadTimeout('timeout'), requests.ConnectionError('reset')):
            with self.subTest(error=type(error).__name__), \
                 patch('paste_celery.requests.post', side_effect=error) as post, \
                 patch.object(paste_celery.external_check_task, 'retry', side_effect=Retry()) as retry:
                with self.assertRaises(Retry):
                    self.run_external()
                retry.assert_called_once_with(countdown=5)
                self.assertEqual(post.call_count, 1)

    def test_external_exhaustion_sends_error_callback(self):
        with patch('paste_celery.requests.post', side_effect=[
                requests.ReadTimeout('timeout'), Mock(status_code=200)]) as post, \
             patch.object(paste_celery.external_check_task, 'retry',
                          side_effect=paste_celery.external_check_task.MaxRetriesExceededError()), \
             patch('paste_celery._make_callback_service_token', return_value='test'), \
             patch('paste_celery._push_system_check_event'):
            self.run_external()
        self.assertEqual(post.call_count, 2)
        result = post.call_args.kwargs['json']
        self.assertEqual((result['status'], result['points']), ('error', 0))

    def run_external(self):
        paste_celery.external_check_task.run(
            code='print(1)', lang='python', task_text='TASK', check_type='gpt',
            check_config={'max_points': 10},
            callback_url='https://example.test/callback', callback_id='test')
