from html.parser import HTMLParser
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from io_test_report import parse_io_test_report, render_io_test_report, render_io_test_report_parts
from io_tests import IOTestExecutor, _report_text
from methods import build_submission_status_payload
from runner import SolutionException
from tests.test_io_tests import make_code


class HTMLView(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags, self.text, self.elements = [], [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.elements.append((tag, dict(attrs)))

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
        summary = render_io_test_report_parts(report)['check_comments_html']
        self.assertIn('Группа 1: 5 из 10 баллов.', summary)
        self.assertIn('За сданную попытку начислен 1 балл.', summary)
        self.assertNotIn('Группа 1:', html)
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
        self.assertEqual(parsed['rows'][1]['status'], 'runtime_error')
        self.assertNotIn('PRIVATE_SECRET', render_io_test_report(report))
        factory.return_value.__enter__.return_value.run.side_effect = [SolutionException('<bad error>'), 'SECRET_OUTPUT']
        _, report = IOTestExecutor(code).perform()
        parsed = parse_io_test_report(report)
        self.assertEqual(parsed['rows'][0]['input'], '2 3\n')
        self.assertEqual(parsed['rows'][0]['error'], '<bad error>')
        self.assertIn('&lt;bad error&gt;', render_io_test_report(report))

    @patch('io_tests.ExecutionContainer')
    def test_error_type_controls_verdict_not_diagnostic_text(self, factory):
        diagnostic = 'Test failed: Execution timed out after 2 seconds.'
        for error_type, label in (
            ('time_limit_exceeded', 'Превышено время'),
            ('runtime_error', 'Ошибка выполнения'),
            ('output_limit_exceeded', 'Превышен объём вывода'),
            ('compilation_error', 'Ошибка компиляции'),
            ('unknown_error', 'Ошибка проверки'),
        ):
            with self.subTest(error_type=error_type):
                factory.return_value.__enter__.return_value.run.side_effect = [
                    SolutionException(diagnostic, error_type),
                    SolutionException('PRIVATE_SECRET', error_type),
                ]
                points, report = IOTestExecutor(make_code()).perform()
                self.assertEqual(points, 0)
                self.assertNotIn('PRIVATE_SECRET', report)
                rows = parse_io_test_report(report)['rows']
                self.assertEqual([row['status'] for row in rows],
                                 [error_type if error_type != 'unknown_error' else 'error'] * 2)
                self.assertEqual([row['status_label'] for row in rows], [label] * 2)
                html = render_io_test_report(report)
                self.assertEqual(html.count(label), 2)  # One verdict per test; no repeated heading.
                if error_type == 'time_limit_exceeded':
                    self.assertNotIn('Ошибка выполнения', html)
                    self.assertIn('Лимит: 2 с', html)
                    self.assertNotIn(diagnostic, html)
                else:
                    self.assertIn(diagnostic, html)

    def test_legacy_timeout_is_recognized_only_from_runner_diagnostic(self):
        for error, expected in (
            ('Test failed: Execution timed out after 2 seconds.', 'time_limit_exceeded'),
            ('Execution timed out after 1.5 seconds.', 'time_limit_exceeded'),
            ('Превышен лимит времени: 1 с', 'time_limit_exceeded'),
            ('Runtime error: Execution timed out after 2 seconds.', 'runtime_error'),
            ('Runtime error: Превышен лимит времени: 1 с', 'runtime_error'),
            ('Something else timed out after 2 seconds.', 'error'),
            ('Compilation timed out after 30 seconds.', 'error'),
            ('<script>Execution timed out after 2 seconds.</script>', 'error'),
        ):
            with self.subTest(error=error):
                report = '\n\n'.join([
                    'Пройдено тестов: 0 из 2.',
                    'Тест 1 (публичный): ошибка выполнения или превышение лимита.',
                    _report_text('Ошибка', error),
                    'Тест 2 (приватный): ошибка выполнения или превышение лимита.',
                    _report_text('Ошибка', 'Test failed: Execution timed out after 2 seconds.'),
                ])
                rows = parse_io_test_report(report)['rows']
                self.assertEqual(rows[0]['status'], expected)
                self.assertEqual(rows[1]['status'], 'error')
                self.assertIsNone(rows[1]['error'])
                self.assertIsNone(rows[1]['error_detail'])
                html = render_io_test_report(report)
                self.assertNotIn('<script>', html)
                if expected == 'time_limit_exceeded':
                    self.assertEqual(html.count('Превышено время'), 1)
                    self.assertIn('Лимит: ', html)
                    self.assertNotIn(error, html)
                    self.assertEqual(rows[0]['error'], error)  # Preserve the saved diagnostic.

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
        self.assertIn('<table', payload['test_results_html'])
        self.assertNotIn('<table', payload['check_comments_html'])
        self.assertIn('Пройдено тестов: 0 из 1.', payload['check_comments_html'])
        self.assertNotIn('<img', payload['test_results_html'])
        code.task.test_mode = 'environment'
        self.assertNotIn('check_comments_html', build_submission_status_payload(code))
        self.assertNotIn('test_results_html', build_submission_status_payload(code))

    def test_private_success_collapses_and_has_no_empty_data_columns(self):
        report = 'Пройдено тестов: 2 из 2.\nТест 1 (приватный): пройден.\nТест 2 (приватный): пройден.'
        html = render_io_test_report(report)
        view = HTMLView(html)
        details = next(attrs for tag, attrs in view.elements if tag == 'details')
        columns = [attrs for tag, attrs in view.elements if tag == 'th' and attrs.get('scope') == 'col']
        self.assertNotIn('open', details)
        self.assertEqual(len(columns), 2)
        self.assertEqual(html.count('Данные приватных тестов скрыты.'), 1)
        self.assertNotIn('Ожидаемый вывод', html)

    def test_failure_opens_details_and_includes_filters_without_reordering_tests(self):
        report = 'Пройдено тестов: 1 из 3.\nТест 1 (публичный): пройден.\nТест 2 (приватный): неверный ответ.\nТест 3 (публичный): ошибка выполнения или превышение лимита.'
        view = HTMLView(render_io_test_report(report))
        details = next(attrs for tag, attrs in view.elements if tag == 'details')
        self.assertIn('open', details)
        self.assertEqual([attrs['data-test-status'] for tag, attrs in view.elements if tag == 'tr' and 'data-test-status' in attrs], ['passed', 'failed', 'error'])
        self.assertEqual([attrs['data-test-filter'] for tag, attrs in view.elements if tag == 'button'], ['failed', 'all'])

    def test_summary_notes_are_escaped_and_do_not_contain_test_data(self):
        report = '\n'.join(['Пройдено тестов: 1 из 1.', '<img src=x onerror=alert(1)>',
                            'Тест 1 (публичный): пройден.', _report_text('Ввод', 'PUBLIC_INPUT')])
        parts = render_io_test_report_parts(report)
        self.assertNotIn('<img', parts['check_comments_html'])
        self.assertIn('&lt;img', parts['check_comments_html'])
        self.assertNotIn('PUBLIC_INPUT', parts['check_comments_html'])
        self.assertIn('PUBLIC_INPUT', parts['test_results_html'])
