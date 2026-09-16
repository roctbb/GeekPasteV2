import importlib
from pathlib import Path
import unittest

from environments.grade7_chapter0_common import TASK_MAX_POINTS
from environments.grade7_chapter0_io import TASK_SPECS
from score_policy import normalize_test_points


EXPECTED_TEST_TASK_IDS = frozenset(range(2440, 2463))


class Grade7Chapter0ReleaseGateTests(unittest.TestCase):
    def test_checker_specs_cover_exactly_the_expected_tasks(self):
        io_ids = frozenset(TASK_SPECS)
        common_ids = frozenset(TASK_MAX_POINTS)

        self.assertFalse(io_ids & common_ids)
        self.assertEqual(io_ids | common_ids, EXPECTED_TEST_TASK_IDS)
        for task_id in EXPECTED_TEST_TASK_IDS:
            with self.subTest(task_id=task_id):
                self.assertEqual(normalize_test_points(task_id, 0), 1)

    def test_every_expected_task_has_an_importable_tester(self):
        for task_id in EXPECTED_TEST_TASK_IDS:
            with self.subTest(task_id=task_id):
                module = importlib.import_module(
                    f"environments.task_{task_id}.tester"
                )
                self.assertTrue(callable(module.perform_tests))

    def test_reflection_remains_without_a_test_checker(self):
        repository = Path(__file__).resolve().parents[1]
        reflection_tester = repository / "environments" / "task_2463" / "tester.py"
        self.assertFalse(reflection_tester.exists())


if __name__ == "__main__":
    unittest.main()
