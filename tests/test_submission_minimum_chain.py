import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from score_policy import ATTEMPT_COMMENT, finalize_submission_score
import paste_celery


def code(points=0, state='partially done', source='print(0)'):
    return SimpleNamespace(id='TEST', code=source, check_points=points,
        check_comments='Критерии не выполнены.', check_state=state,
        course_id=162, user_id=10, task_id=2467,
        task=SimpleNamespace(points=75, check_type='gpt'))


class SubmissionMinimumTests(unittest.TestCase):
    def test_finalizer_is_idempotent_and_keeps_positive_scores(self):
        for points, expected in [(0, 1), (1, 1), (5, 5), (75, 75)]:
            with self.subTest(points=points):
                value = code(points)
                finalize_submission_score(value)
                finalize_submission_score(value)
                self.assertEqual(value.check_points, expected)
                self.assertEqual(value.check_comments.count(ATTEMPT_COMMENT), int(points == 0))

    def test_missing_pending_and_ungraded_work_does_not_get_credit(self):
        for value in [code(source=''), code(source='   '), code(state=None),
                      code(state='not checked'), code(state='checking'), code(points=None)]:
            before = value.check_points
            finalize_submission_score(value)
            self.assertEqual(value.check_points, before)

    def test_callback_defensively_replaces_zero_and_persists_same_score(self):
        for points, expected in [(0, 1), (1, 1), (5, 5)]:
            value = code(points)
            with patch('paste_celery.db', SimpleNamespace(session=Mock())), \
                 patch('paste_celery.SUBMIT_URL', 'https://example.test/callback'), \
                 patch('paste_celery.requests.post') as post, \
                 patch('paste_celery.generate_jwt', return_value='test-token'), \
                 patch('paste_celery.build_academic_integrity_payload', return_value={'ai': {}, 'similarity': {}}), \
                 patch('paste_celery._emit_submission_status') as emit, \
                 patch('paste_celery._push_system_check_event'):
                paste_celery._publish_checked_submission(value)
            self.assertEqual(value.check_points, expected)
            self.assertEqual(post.call_args.kwargs['json']['points'], expected)
            self.assertEqual(emit.call_args.args[0].check_points, expected)

    def test_failed_github_fetch_also_publishes_attempt(self):
        value = code(0, 'fetching', '{"repo_url":"https://github.com/user/missing"}')
        with patch('paste_celery.get_code', return_value=value), \
             patch('paste_celery.extract_data_from_github_repository', side_effect=RuntimeError('unavailable')), \
             patch('paste_celery.db', SimpleNamespace(session=Mock())), \
             patch('paste_celery._publish_checked_submission') as publish:
            paste_celery.fetch_github_and_check.run('TEST', 'https://github.com/user/missing', 2467)
        self.assertEqual(value.check_state, 'execution error')
        publish.assert_called_once_with(value)
        finalize_submission_score(value)
        self.assertEqual(value.check_points, 1)

    def test_external_tests_and_gpt_callbacks_preserve_zero(self):
        response = Mock(status_code=200)
        response.json.return_value = {'result': {'output': [
            {'type': 'message', 'content': [{'text': '0\nНеверно.'}]}]}}
        for check_type in ['tests', 'gpt']:
            with self.subTest(check_type=check_type), \
                 patch('runner.BrainfuckExecutor') as executor, \
                 patch('paste_celery.requests.post', return_value=response) as post, \
                 patch('paste_celery._make_callback_service_token', return_value='test'), \
                 patch('paste_celery._push_system_check_event'):
                executor.return_value.run.return_value = 'wrong'
                paste_celery.external_check_task.run(
                    code='++', lang='brainfuck', task_text='Example', check_type=check_type,
                    check_config={'tests': [{'expected': 'right'}], 'max_points': 10},
                    callback_url='https://example.test/callback', callback_id='test')
            callback = post.call_args.kwargs['json']
            self.assertEqual(callback['points'], 0)
            self.assertEqual(callback['status'], 'success')
            self.assertEqual(callback['comment'],
                             'Неверно.' if check_type == 'gpt' else '0 из 1 тестов пройдено')
            self.assertNotIn(ATTEMPT_COMMENT, callback['comment'])


if __name__ == '__main__':
    unittest.main()
