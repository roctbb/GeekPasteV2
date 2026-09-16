import importlib
from pathlib import Path
import unittest

from score_policy import GRADE8_2026_TASK_IDS, normalize_test_points


TARGET_TASK_IDS = tuple(range(2770, 2794))
TARGET_TEST_TASK_IDS = tuple(range(2770, 2793))


class Grade8PythonReviewReleaseGateTests(unittest.TestCase):
    def test_every_test_task_reuses_the_matching_grade7_checker(self):
        for source_id, target_id in zip(
            range(2440, 2463),
            TARGET_TEST_TASK_IDS,
        ):
            with self.subTest(source_id=source_id, target_id=target_id):
                source = importlib.import_module(
                    f"environments.task_{source_id}.tester"
                )
                target = importlib.import_module(
                    f"environments.task_{target_id}.tester"
                )
                self.assertIs(target.perform_tests, source.perform_tests)

    def test_reflection_stays_on_gpt_without_a_tester(self):
        repository = Path(__file__).resolve().parents[1]
        self.assertFalse(
            (repository / "environments" / "task_2793" / "tester.py").exists()
        )

    def test_scoring_policy_includes_the_new_grade8_tasks(self):
        for task_id in TARGET_TEST_TASK_IDS:
            with self.subTest(task_id=task_id):
                self.assertEqual(normalize_test_points(task_id, 0), 1)
        self.assertTrue(set(TARGET_TASK_IDS).issubset(GRADE8_2026_TASK_IDS))


if __name__ == "__main__":
    unittest.main()
