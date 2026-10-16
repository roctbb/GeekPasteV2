import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from io_test_import import import_environment_tests, preset_metadata
from io_test_report import parse_io_test_report
from io_tests import outputs_equal
from methods import check_task_with_tests
from tests.test_magic_square_split import reference


REFERENCE_CPP = r'''
#include <iostream>
#include <vector>
int main() {
    int n;
    std::cin >> n;
    std::vector<std::vector<long long>> a(n, std::vector<long long>(n));
    for (auto &row : a) for (auto &x : row) std::cin >> x;
    long long target = 0;
    for (auto x : a[0]) target += x;
    auto mismatch = [&](const char *kind, int number, long long sum) {
        if (sum == target) return false;
        std::cout << "no " << kind << " " << number
                  << "; SuM=" << sum << "; ExPeCtEd=" << target << "\r\n";
        return true;
    };
    for (int i = 0; i < n; ++i) {
        long long sum = 0;
        for (auto x : a[i]) sum += x;
        if (mismatch("ROW", i + 1, sum)) return 0;
    }
    for (int j = 0; j < n; ++j) {
        long long sum = 0;
        for (int i = 0; i < n; ++i) sum += a[i][j];
        if (mismatch("COL", j + 1, sum)) return 0;
    }
    long long first = 0, second = 0;
    for (int i = 0; i < n; ++i) {
        first += a[i][i];
        second += a[i][n - i - 1];
    }
    if (mismatch("DIAG", 1, first) || mismatch("DIAG", 2, second)) return 0;
    std::cout << "Y\rES \r\n";
}
'''


def make_submission():
    task = SimpleNamespace(id=2915, name='Первое расхождение', points=5,
                           test_mode='io', check_type='tests',
                           test_config=import_environment_tests(2915, 'cpp', 5))
    return SimpleNamespace(id='MAGIC-IO-TEST', lang='cpp', code=REFERENCE_CPP,
                           task=task, task_id=2915, user_id=None, course_id=None,
                           check_points=None, check_state=None, check_comments=None)


class MagicSquareIOTests(unittest.TestCase):
    def test_frozen_suite_keeps_all_cases_limits_and_public_visibility(self):
        config = make_submission().task.test_config
        self.assertEqual(preset_metadata(2915)['sha256'],
                         '917a0b8431b9fbc184bf618be7a51cce2c1f1e11835c70f87e757fa0fb012f05')
        self.assertEqual(len(config['tests']), 16)
        self.assertEqual(config['scoring'], 'all_or_nothing')
        self.assertEqual((config['memory_limit'], config['process_limit'], config['disable_swap']),
                         (512, 128, False))
        modes = [case['comparison'] for case in config['tests']]
        self.assertEqual(modes.count('tokens_ignore_cr'), 4)
        self.assertEqual(modes.count('magic_mismatch'), 12)
        for case in config['tests']:
            self.assertTrue(case['is_public'])
            self.assertEqual((case['time_limit'], case['output_limit']), (1, 102400))
            self.assertEqual(reference(case['input'], True), case['output'].strip())

    def test_diagnostic_format_preserves_accepted_and_rejected_boundaries(self):
        expected = 'NO: row 2 (sum 13, expected 17)\n'
        accepted = [expected, expected.upper(), expected.lower(),
                    'NO row 2 sum=13; expected=17',
                    ' NO:ROW\t2 (SUM:13 EXPECTED:17) ',
                    'N\rO: ro\rw 2 (sum 1\r3, expected 17)\r\n',
                    'NO row 2, sum 13 expected 17',
                    'NO row 2sum13expected17']
        rejected = ['NO', 'YES', '', expected + 'debug', 'debug ' + expected,
                    expected.replace('row', 'col'), expected.replace('row 2', 'row 1'),
                    expected.replace('sum 13', 'sum 14'), expected.replace('expected 17', 'expected 18'),
                    expected.replace('row 2', 'row 02'), expected.replace('sum 13', 'sum +13'),
                    expected.replace('sum 13', 'sum 013'), expected.replace('13', '13.0'),
                    expected.replace('row 2', 'row ٢'), expected.replace('sum 13', 'sum -13')]
        for actual in accepted + rejected:
            with self.subTest(actual=actual):
                self.assertEqual(outputs_equal(actual, expected, 'magic_mismatch'), actual in accepted)
        for actual in ('YES', ' Y\rES\r\n', 'YES \n\t'):
            self.assertTrue(outputs_equal(actual, 'YES\n', 'tokens_ignore_cr'))
        for actual in ('yes', 'Yes', 'YES debug', 'Y ES'):
            self.assertFalse(outputs_equal(actual, 'YES\n', 'tokens_ignore_cr'))

    @patch('io_tests.ExecutionContainer')
    def test_every_failed_case_keeps_attempt_point_without_partial_credit(self, factory):
        for failed in [None, *range(16)]:
            code = make_submission()
            answers = [case['output'] for case in code.task.test_config['tests']]
            if failed is not None:
                answers[failed] = 'WRONG'
            factory.return_value.__enter__.return_value.run.side_effect = answers
            check_task_with_tests(code.task, code)
            self.assertEqual(code.check_points, 5 if failed is None else 1)
            self.assertEqual(code.check_state, 'done' if failed is None else 'partially done')
            report = parse_io_test_report(code.check_comments)
            self.assertEqual(report['passed'], 16 if failed is None else 15)
            self.assertTrue(all(row['public'] for row in report['rows']))


@unittest.skipUnless(os.getenv('RUN_GRADE8_DOCKER_INTEGRATION') == '1', 'requires Docker runtime')
class MagicSquareIODockerTests(unittest.TestCase):
    @patch('methods.send_telegram_message')
    def test_real_cpp_with_compatible_format_passes_all_public_tests(self, notify):
        code = make_submission()
        check_task_with_tests(code.task, code)
        self.assertEqual((code.check_points, code.check_state), (5, 'done'), code.check_comments)
        report = parse_io_test_report(code.check_comments)
        self.assertEqual((report['passed'], report['total']), (16, 16))
        self.assertTrue(all(row['public'] and row['input'] is not None for row in report['rows']))
        notify.assert_not_called()
