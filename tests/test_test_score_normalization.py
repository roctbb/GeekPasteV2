import unittest
from types import SimpleNamespace
from unittest.mock import patch

from methods import check_task_with_tests
from score_policy import normalize_gpt_points, normalize_test_points


class _ZeroScoreExecutor:
    def __init__(self, code):
        self.code = code

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def perform(self):
        return 0, 'Ни один тест не пройден.'


class TestScoreNormalizationTests(unittest.TestCase):
    def test_rubric_releases_receive_attempt_point(self):
        self.assertEqual(normalize_test_points(2440, 0), 1)
        self.assertEqual(normalize_test_points(2462, 0), 1)
        self.assertEqual(normalize_test_points(2567, 0), 1)
        self.assertEqual(normalize_test_points(2769, 0), 1)

    def test_legacy_tasks_keep_the_existing_minimum(self):
        self.assertEqual(normalize_test_points(2439, 0), 1)
        self.assertEqual(normalize_test_points(2463, 0), 1)
        self.assertEqual(normalize_test_points(9999, 0), 1)

    def test_missing_points_keep_legacy_minimum(self):
        self.assertEqual(normalize_test_points(2440, None), 1)

    def test_positive_points_are_unchanged(self):
        self.assertEqual(normalize_test_points(2440, 5), 5)
        self.assertEqual(normalize_test_points(2002, 10), 10)

    def test_all_gpt_tasks_and_images_receive_attempt_point(self):
        self.assertEqual(normalize_gpt_points(2567, 'cpp', 0, 10), 1)
        self.assertEqual(normalize_gpt_points(2769, 'zip', 0, 20), 1)
        self.assertEqual(normalize_gpt_points(2002, 'image', 0, 10), 1)
        self.assertEqual(normalize_gpt_points(2457, 'python', 0, 15), 1)
        self.assertEqual(normalize_gpt_points(2787, 'python', 0, 15), 1)
        self.assertEqual(normalize_gpt_points(2462, 'python', 0, 20), 1)
        self.assertEqual(normalize_gpt_points(2792, 'python', 0, 20), 1)
        self.assertEqual(normalize_gpt_points(2002, 'cpp', 0, 10), 1)

    @patch('methods.TestExecutor', _ZeroScoreExecutor)
    def test_deterministic_check_awards_attempt_point(self):
        task = SimpleNamespace(id=2567, points=10)
        code = SimpleNamespace(
            check_points=None,
            check_comments=None,
            check_state=None,
        )

        check_task_with_tests(task, code)

        self.assertEqual(code.check_points, 1)
        self.assertEqual(code.check_state, 'partially done')
        self.assertIn('Ни один тест не пройден.', code.check_comments)
        self.assertIn('1 балл за сданную попытку', code.check_comments)


if __name__ == "__main__":
    unittest.main()
