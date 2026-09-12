import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask
from models import Code, db, similarities_table
import paste_celery
import paste_server
from scripts.repair_github_similarity import repair_pair, sync_flags


def payload(source):
    return json.dumps({'repo_url': 'https://github.com/test/quest', 'files': [{'name': 'main.py', 'content': source}]})


class GitHubQueueTests(unittest.TestCase):
    def test_submission_does_not_queue_similarity_on_placeholder(self):
        client = paste_server.app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 1
            session['role'] = 'student'
        with patch.object(paste_server, 'save_code', return_value='TEST'), \
             patch.object(paste_server.save_similarities, 'delay') as similarity, \
             patch.object(paste_server.fetch_github_and_check, 'delay') as fetch:
            response = client.post('/', data={'github_repo_url': 'https://github.com/test/quest'})
        self.assertEqual(response.status_code, 302)
        fetch.assert_called_once_with('TEST', 'https://github.com/test/quest', None)
        similarity.assert_not_called()

    def test_fetch_commits_files_before_queueing_similarity(self):
        value = SimpleNamespace(id='TEST', code='pending', similarity_checked=True)
        events = []
        with patch.object(paste_celery, 'get_code', return_value=value), \
             patch.object(paste_celery, 'extract_data_from_github_repository', return_value=payload('print(42)')), \
             patch.object(paste_celery, 'db', SimpleNamespace(session=Mock(commit=lambda: events.append('commit')))), \
             patch.object(paste_celery.save_similarities, 'delay', side_effect=lambda _: events.append('similarity')), \
             patch.object(paste_celery.check_task, 'delay', side_effect=lambda _: events.append('grade')):
            paste_celery.fetch_github_and_check.run('TEST', 'https://github.com/test/quest', 12)
        self.assertEqual(events, ['commit', 'similarity', 'grade'])
        self.assertFalse(value.similarity_checked)
        self.assertIn('print(42)', value.code)

    def test_worker_uses_source_not_old_checker_for_github(self):
        current = SimpleNamespace(id='ONE', user_id=1, task=None, task_id=None, course_id=None,
                                  lang='github', code=payload('print(42)'), similarity_checked=False, has_similarity_warning=False)
        alternative = SimpleNamespace(code=payload('print(42) # same source'))
        query = Mock()
        query.yield_per.return_value = [alternative]
        with patch.object(paste_celery, 'get_code', return_value=current), \
             patch.object(paste_celery, 'db', SimpleNamespace(session=Mock())), \
             patch.object(paste_celery, 'similarity_candidates_query', return_value=query), \
             patch.object(paste_celery, 'save_similarity') as save, \
             patch.object(paste_celery.checker, 'similarity') as old_checker, \
             patch.object(paste_celery, 'send_similarity_summary_notification'), \
             patch.object(paste_celery, '_push_system_check_event'), \
             patch.object(paste_celery, '_notify_integrity_update'):
            paste_celery.save_similarities.run('ONE')
        old_checker.assert_not_called()
        save.assert_called_once_with(current, alternative, 100, send_notification=False)
        self.assertTrue(current.similarity_checked)


class GitHubRepairTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.a = Code(id='ONE', lang='github', code=payload('def play():\n    name=input("Имя?")\n    print(name)\nplay()'), user_id=1,
                      check_points=35, check_comments='Keep feedback', check_state='partially done', has_similarity_warning=True,
                      has_critical_similarity_warning=True, similarity_checked=True)
        self.b = Code(id='TWO', lang='github', code=payload('from math import sqrt\nvalues=[sqrt(x) for x in range(100)]'), user_id=2,
                      check_points=75, check_state='done', similarity_checked=True)
        db.session.add_all([self.a, self.b])
        db.session.commit()
        db.session.execute(similarities_table.insert().values(code_id='ONE', code_id2='TWO', percent=100))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_dry_run_and_repair_keep_scores_and_back_up_old_flags(self):
        with redirect_stdout(io.StringIO()):
            plan = repair_pair('ONE', 'TWO')
        self.assertLess(plan['new_percent'], 75)
        self.assertEqual(len(db.session.execute(similarities_table.select()).all()), 1)
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            backup = str(Path(temp) / 'backup.json')
            repair_pair('ONE', 'TWO', True, backup)
            self.assertEqual(json.loads(Path(backup).read_text())['pair'][0]['percent'], 100)
        self.assertEqual(len(db.session.execute(similarities_table.select()).all()), 0)
        self.assertFalse(self.a.has_similarity_warning)
        self.assertFalse(self.a.has_critical_similarity_warning)
        self.assertEqual((self.a.check_points, self.b.check_points), (35, 75))
        self.assertEqual(self.a.check_comments, 'Keep feedback')

    def test_real_match_is_retained(self):
        self.b.code = self.a.code
        db.session.commit()
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            repair_pair('ONE', 'TWO', True, str(Path(temp) / 'backup.json'))
        self.assertEqual(db.session.execute(similarities_table.select()).one().percent, 100)
        self.assertTrue(self.a.has_similarity_warning)

    def test_sync_only_uses_integrity_endpoint_without_score(self):
        response = Mock()
        response.json.return_value = {'state': 'ok'}
        with patch('scripts.repair_github_similarity.requests.post', return_value=response) as post, \
             patch('scripts.repair_github_similarity.generate_jwt', return_value='test'), \
             redirect_stdout(io.StringIO()):
            sync_flags(['ONE'])
        self.assertTrue(post.call_args.args[0].endswith('/integrity'))
        self.assertNotIn('points', post.call_args.kwargs['json'])


if __name__ == '__main__':
    unittest.main()
