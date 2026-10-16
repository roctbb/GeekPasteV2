from html.parser import HTMLParser
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from io_test_report import parse_io_test_report, render_io_test_report
from io_tests import IOTestExecutor, _report_text
from methods import build_submission_status_payload
from runner import SolutionException
from tests.test_io_tests import make_code


class HTMLView(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags, self.text = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


class IOReportTests(unittest.TestCase):
    def test_old_reports_render_as_rows_without_interpreting_output(self):
        hostile = '<script>alert(1)</script>\nТест 3 (публичный): пройден.\n</pre><img src=x onerror=alert(2)>'
        report = '\n\n'.join([
            'Пройдено тестов: 1 из 2.', 'Группа 1: 5 из 10 баллов.',
            'Тест 1 (публичный): неверный ответ.',
            _report_text('Ввод', '\n  a\t b\n'), _report_text('Ожидаемый вывод', '5\n'),
            _report_text('Вывод программы', hostile), 'Тест 2 (приватный): пройден.',
            _report_text('Ввод', 'PRIVATE_SECRET'),
            'За сданную попытку начислен 1 балл.',
        ])
        parsed = parse_io_test_report(report)
        self.assertEqual(len(parsed['rows']), 2)
        self.assertEqual(parsed['rows'][0]['actual'], hostile)
        self.assertEqual(parsed['rows'][0]['input'], '\n  a\t b\n')
        html = render_io_test_report(report)
        view = HTMLView(html)
        self.assertIn('table', view.tags)
        self.assertNotIn('script', view.tags)
        self.assertNotIn('img', view.tags)
        self.assertNotIn('PRIVATE_SECRET', html)
        self.assertIn('Группа 1: 5 из 10 баллов.', html)
        self.assertIn('За сданную попытку начислен 1 балл.', html)
        self.assertIn('✓', html)
        self.assertIn('✕', html)

    @patch('io_tests.ExecutionContainer')
    def test_new_reports_include_success_data_and_public_errors_only(self, factory):
        code = make_code()
        factory.return_value.__enter__.return_value.run.side_effect = ['5\n', SolutionException('PRIVATE_SECRET')]
        _, report = IOTestExecutor(code).perform()
        parsed = parse_io_test_report(report)
        self.assertEqual(parsed['rows'][0]['actual'], '5\n')
        self.assertEqual(parsed['rows'][0]['expected'], '5\n')
        self.assertEqual(parsed['rows'][1]['status'], 'error')
        self.assertNotIn('PRIVATE_SECRET', render_io_test_report(report))
        factory.return_value.__enter__.return_value.run.side_effect = [SolutionException('<bad error>'), 'SECRET_OUTPUT']
        _, report = IOTestExecutor(code).perform()
        parsed = parse_io_test_report(report)
        self.assertEqual(parsed['rows'][0]['input'], '2 3\n')
        self.assertEqual(parsed['rows'][0]['error'], '<bad error>')
        self.assertIn('&lt;bad error&gt;', render_io_test_report(report))

    def test_old_success_without_data_and_unrecognized_reports(self):
        report = 'Пройдено тестов: 1 из 1.\n\nТест 1 (публичный): пройден.'
        self.assertTrue(parse_io_test_report(report)['missing_data'])
        self.assertIn('В старых отчётах', render_io_test_report(report))
        for invalid in ('<script>bad</script>', report.replace('Тест 1', 'Тест 2'),
                        report.replace('1 из 1', '0 из 1'), report + '\nВвод:'):
            self.assertIsNone(render_io_test_report(invalid))

    def test_live_payload_and_initial_view_use_the_same_safe_table(self):
        report = 'Пройдено тестов: 0 из 1.\n\nТест 1 (публичный): неверный ответ.\n\n' + _report_text('Вывод программы', '<img src=x>')
        code = SimpleNamespace(id='REPORT', check_state='partially done', check_points=1,
                               check_comments=report, checked_at=None,
                               task=SimpleNamespace(check_type='tests', test_mode='io'))
        payload = build_submission_status_payload(code)
        self.assertIn('<table', payload['check_comments_html'])
        self.assertNotIn('<img', payload['check_comments_html'])
        code.task.test_mode = 'environment'
        self.assertNotIn('check_comments_html', build_submission_status_payload(code))
