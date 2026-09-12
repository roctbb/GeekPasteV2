import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from methods import check_task_with_gpt


def task(task_id=2467):
    return SimpleNamespace(id=task_id, text='Квест: 15 критериев по 5 баллов.',
                           points=75, lang='github', gpt_model='test')


def submission(files=None):
    return SimpleNamespace(
        code=json.dumps({'repo_url': 'https://github.com/student/quest',
                         'resolved_repo': 'student/quest', 'ref': 'main',
                         'files': files if files is not None else [
                             {'name': 'main.py', 'content': 'choice = input("Куда идти?")\n'}]}),
        lang='github', task_id=2467, user_id=None, course_id=162,
        check_points=None, check_state=None, check_comments=None,
        has_ai_warning=False,
    )


def gateway(text):
    return SimpleNamespace(json=lambda: {'result': {'output': [
        {'type': 'message', 'content': [{'text': text}]}]}})


class QuestGithubTests(unittest.TestCase):
    def check(self, text, code=None, task_id=2467):
        code = code or submission()
        with patch('methods.requests.post', return_value=gateway(text)) as post, \
                patch('methods.db', SimpleNamespace(session=Mock())), \
                patch('methods.analyze_code_for_ai_usage', return_value={'suspicious': False}):
            check_task_with_gpt(task(task_id), code)
        return code, post.call_args.kwargs['json']

    def test_valid_but_broken_quest_gets_five(self):
        code, request = self.check('0\nQUEST_SUBMISSION: YES\nВ квесте есть ошибки запуска.')
        self.assertEqual(code.check_points, 5)
        self.assertEqual(code.check_state, 'partially done')
        prompt = request['input'][0]['content']
        self.assertIn('70 баллов', prompt)
        self.assertIn('НЕ включай их', prompt)
        self.assertIn('посторонний проект', prompt)
        self.assertNotIn('ставь 0', prompt)
        self.assertNotIn('QUEST_SUBMISSION:', code.check_comments)

    def test_full_score_adds_publication_only_once(self):
        code, _ = self.check('70\nQUEST_SUBMISSION: YES\nВыполнены остальные критерии.')
        self.assertEqual(code.check_points, 75)
        self.assertEqual(code.check_state, 'done')

    def test_unrelated_project_gets_attempt_but_not_publication_credit(self):
        code, _ = self.check('70\nQUEST_SUBMISSION: NO\nЭто сторонняя библиотека, а не квест.')
        self.assertEqual(code.check_points, 1)
        self.assertIn('0/5', code.check_comments)

    def test_missing_eligibility_never_grants_publication_credit(self):
        for reply in ['70\nВсе хорошо.', '70\nQUEST_SUBMISSION: YES\nQUEST_SUBMISSION: NO']:
            with self.subTest(reply=reply):
                code, _ = self.check(reply)
                self.assertEqual(code.check_points, 1)
                self.assertEqual(code.check_state, 'execution error')

    def test_score_is_bounded_and_in_steps_of_five(self):
        for points, expected in [(4, 5), (12, 15), (100, 75)]:
            with self.subTest(points=points):
                code, _ = self.check(f'{points}\nQUEST_SUBMISSION: YES\nКомментарий.')
                self.assertEqual(code.check_points, expected)

    @patch('methods.requests.post')
    def test_empty_readme_only_and_failed_fetch_are_not_quests(self, post):
        for files in [[], [{'name': 'README.md', 'content': 'Это квест!'}],
                      [{'name': 'main.py', 'content': '  '}]]:
            code = submission(files)
            check_task_with_gpt(task(), code)
            self.assertEqual(code.check_points, 1)
        code = submission()
        code.code = json.dumps({'repo_url': 'https://github.com/student/quest', 'files': []})
        check_task_with_gpt(task(), code)
        self.assertEqual(code.check_points, 1)
        post.assert_not_called()

    def test_unrelated_task_keeps_existing_policy(self):
        code, request = self.check('10\nОбычная проверка.', task_id=2002)
        self.assertEqual(code.check_points, 10)
        self.assertNotIn('QUEST_SUBMISSION:', request['input'][0]['content'])

    def test_legacy_zip_is_not_credited_as_github_publication(self):
        code = submission()
        code.lang = 'zip'
        code.code = json.dumps([{'name': 'main.py', 'content': 'print(1)'}])
        code, request = self.check('0\nНет публикации.', code=code)
        self.assertNotEqual(code.check_points, 5)
        self.assertNotIn('QUEST_SUBMISSION:', request['input'][0]['content'])


if __name__ == '__main__':
    unittest.main()
