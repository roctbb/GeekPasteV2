import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import paste_server
from spreadsheet_submission import create_spreadsheet_submission, parse_spreadsheet_submission
from test_spreadsheet_submission import workbook_bytes


class SpreadsheetRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = paste_server.app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = 7
            session['role'] = 'student'
        self.task = SimpleNamespace(id=99999, name='Кот-ученый', lang='xlsx',
                                    check_type='gpt', gpt_rate_limit=None)

    def test_upload_stores_original_workbook_and_schedules_grading(self):
        model = Mock()
        model.query.filter_by.return_value.first.return_value = self.task
        data = workbook_bytes()
        with patch('paste_server.Task', model), patch('paste_server.Code', Mock()), \
             patch('paste_server.check_gpt_rate_limit', return_value=(True, 1, 10)), \
             patch('paste_server.save_code', return_value='XLSX01') as save, \
             patch('paste_server.save_similarities.delay'), patch('paste_server.check_task.delay') as grade:
            response = self.client.post('/?task_id=99999&course_id=163', data={
                'lang': 'xlsx', 'file': (io.BytesIO(data), 'report.xlsx'),
            })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/?id=XLSX01'))
        self.assertEqual(save.call_args.args[1], 'xlsx')
        self.assertEqual(parse_spreadsheet_submission(save.call_args.args[0], 1024 * 1024)['data'], data)
        grade.assert_called_once_with('XLSX01')

    def test_corrupt_upload_is_rejected_before_saving(self):
        model = Mock()
        model.query.filter_by.return_value.first.return_value = self.task
        with patch('paste_server.Task', model), patch('paste_server.save_code') as save:
            response = self.client.post('/?task_id=99999&course_id=163', data={
                'lang': 'xlsx', 'file': (io.BytesIO(b'broken'), 'report.xlsx'),
            })
        self.assertEqual(response.status_code, 302)
        self.assertIn('task_id=99999', response.location)
        save.assert_not_called()

    def test_form_has_xlsx_upload_and_no_code_editor(self):
        model = Mock()
        model.query.filter_by.return_value.first.return_value = self.task
        with patch('paste_server.Task', model), \
             patch('paste_server.get_gpt_rate_limit_info', return_value=(0, 10, 0)):
            response = self.client.get('/?task_id=99999&course_id=163')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('accept=".xlsx"', html)
        self.assertIn('name="lang" value="xlsx"', html)
        self.assertNotIn('name="code"', html)

    def test_download_preserves_bytes_and_checks_access(self):
        data = workbook_bytes()
        code = SimpleNamespace(lang='xlsx', available_without_auth=False,
                               task=self.task, user_id=7,
                               code=create_spreadsheet_submission('report.xlsx', data, 1024 * 1024))
        with patch('paste_server.get_code', return_value=code):
            response = self.client.get('/xlsx?id=XLSX01')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, data)
            self.assertIn('report.xlsx', response.headers['Content-Disposition'])
            self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
            with self.client.session_transaction() as session:
                session['user_id'] = 8
            self.assertEqual(self.client.get('/xlsx?id=XLSX01').status_code, 403)
            with self.client.session_transaction() as session:
                session.clear()
            self.assertEqual(self.client.get('/xlsx?id=XLSX01').status_code, 302)

    def test_xlsx_language_is_enforced(self):
        self.assertIsNotNone(paste_server._task_submission_language_error(self.task, 'cpp'))
        self.assertIsNone(paste_server._task_submission_language_error(self.task, 'xlsx'))
        self.assertIsNotNone(paste_server._task_submission_language_error(SimpleNamespace(lang='cpp'), 'xlsx'))


if __name__ == '__main__':
    unittest.main()
