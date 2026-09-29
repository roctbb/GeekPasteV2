import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from score_policy import normalize_test_points, finalize_submission_score
from methods import check_task_with_tests
from runner import SolutionException, ExecutionException
import paste_celery

class OlympiadPolicyTests(unittest.TestCase):
    def test_only_full_solution_gets_points(self):
        for task_id in range(2871,2915):
            for points in (None,0,1,2,3,4,5,6):
                self.assertEqual(normalize_test_points(task_id,points),5 if (points or 0)>=5 else 0)
        for task_id in (2870,2915,2567):
            self.assertEqual(normalize_test_points(task_id,0),1)

    def test_checker_wrong_answer_runtime_and_system_failures_stay_zero(self):
        task=SimpleNamespace(id=2914,points=5)
        for result in [(0,'Неверно.'),(5,'Полное решение.'),SolutionException('timeout'),ExecutionException('system')]:
            code=SimpleNamespace(id='QA',task_id=task.id,code='print(0)',check_points=None,check_state=None,check_comments='',user_id=None,course_id=None,task=task)
            executor=Mock()
            if isinstance(result,Exception): executor.perform.side_effect=result
            else: executor.perform.return_value=result
            context=Mock(); context.__enter__=Mock(return_value=executor); context.__exit__=Mock(return_value=None)
            with patch('methods.TestExecutor',return_value=context),patch('methods.send_telegram_message'):
                check_task_with_tests(task,code)
            expected=5 if isinstance(result,tuple) and result[0]==5 else 0
            self.assertEqual(code.check_points,expected)
            self.assertNotIn('Начислен 1 балл',code.check_comments)
            finalize_submission_score(code)
            self.assertEqual(code.check_points,expected)

    def test_callback_preserves_zero_and_five(self):
        for points in (0,5):
            code=SimpleNamespace(id='QA',task_id=2914,course_id=165,user_id=1,code='print(0)',check_points=points,check_comments='QA',check_state='done' if points else 'partially done',task=SimpleNamespace(points=5,check_type='tests'))
            with patch('paste_celery.db',SimpleNamespace(session=Mock())),patch('paste_celery.SUBMIT_URL','https://example.test/callback'),patch('paste_celery.requests.post') as post,patch('paste_celery.generate_jwt',return_value='test'),patch('paste_celery.build_academic_integrity_payload',return_value={'ai':{},'similarity':{}}),patch('paste_celery._emit_submission_status'),patch('paste_celery._push_system_check_event'):
                paste_celery._publish_checked_submission(code)
            self.assertEqual(post.call_args.kwargs['json']['points'],points)

if __name__=='__main__': unittest.main()
