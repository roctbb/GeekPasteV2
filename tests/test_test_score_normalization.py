import unittest

from score_policy import normalize_test_points


class TestScoreNormalizationTests(unittest.TestCase):
    def test_grade7_intro_tasks_preserve_explicit_zero(self):
        self.assertEqual(normalize_test_points(2440, 0), 0)
        self.assertEqual(normalize_test_points(2462, 0), 0)

    def test_neighboring_tasks_keep_legacy_minimum(self):
        self.assertEqual(normalize_test_points(2439, 0), 1)
        self.assertEqual(normalize_test_points(2463, 0), 1)

    def test_missing_points_keep_legacy_minimum(self):
        self.assertEqual(normalize_test_points(2440, None), 1)

    def test_positive_points_are_unchanged(self):
        self.assertEqual(normalize_test_points(2440, 5), 5)
        self.assertEqual(normalize_test_points(2002, 10), 10)


if __name__ == "__main__":
    unittest.main()
