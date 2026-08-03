import importlib
import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ROOT / "environments"
MANIFEST_PATH = ENVIRONMENTS / "grade8_2026_manifest.json"
MODULES = (
    "environments.grade8_2026_chapters_1_4",
    "environments.grade8_2026_chapters_5_6",
    "environments.grade8_2026_chapters_7_8",
)


class Grade8ReleaseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.tasks = cls.manifest["tasks"]
        cls.test_tasks = [task for task in cls.tasks if task["tester_required"]]

    def test_manifest_is_the_frozen_2026_mapping(self):
        self.assertEqual(
            hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
            "46d89f78897e7a5c71fd87a8806cc5d18062160472d473b575e93a6926d1b4fb",
        )
        self.assertEqual(self.manifest["format"], "grade8-2026-environments-v1")
        self.assertEqual(
            self.manifest["package_digest"],
            "8fbdbb2ea3fc0004fe8182400fa50d0e64ef4450b321fd9b5be6bf46c576a984",
        )
        self.assertEqual(self.manifest["task_id_start"], 2567)
        self.assertEqual(self.manifest["task_id_end"], 2769)
        self.assertEqual(len(self.tasks), 203)
        self.assertEqual([task["id"] for task in self.tasks], list(range(2567, 2770)))
        self.assertEqual(sum(task["points"] for task in self.tasks), 1965)
        self.assertEqual(len({task["source"] for task in self.tasks}), 203)
        self.assertFalse(any("\ufffd" in task["name"] for task in self.tasks))

    def test_checker_and_language_policy_counts(self):
        self.assertEqual(
            {kind: sum(task["check_type"] == kind for task in self.tasks) for kind in ("tests", "gpt")},
            {"tests": 105, "gpt": 98},
        )
        self.assertEqual(
            {lang: sum(task["lang"] == lang for task in self.tasks) for lang in ("cpp", "python", "zip", "image")},
            {"cpp": 153, "python": 14, "zip": 16, "image": 20},
        )
        self.assertTrue(
            all(task["check_type"] == "gpt" for task in self.tasks if task["lang"] in {"zip", "image"})
        )
        self.assertTrue(
            all(task["lang"] in {"cpp", "python"} for task in self.test_tasks)
        )
        by_id = {task["id"]: task for task in self.tasks}
        self.assertEqual(
            (by_id[2570]["lang"], by_id[2570]["check_type"]),
            ("python", "tests"),
        )
        self.assertEqual(
            (by_id[2621]["lang"], by_id[2621]["check_type"]),
            ("python", "tests"),
        )
        self.assertEqual(
            (by_id[2622]["lang"], by_id[2622]["check_type"]),
            ("cpp", "gpt"),
        )
        self.assertEqual(
            (by_id[2753]["lang"], by_id[2753]["check_type"]),
            ("cpp", "tests"),
        )

    def test_release_sources_are_valid_utf8_without_mojibake_markers(self):
        suspicious = ("Р°", "Р±", "Р²", "Рµ", "Рё", "Рѕ", "С‚", "СЃ", "вњ")
        paths = [MANIFEST_PATH, *(ENVIRONMENTS.glob("grade8_2026*.py"))]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", text, path)
            for marker in suspicious:
                self.assertNotIn(marker, text, f"{path}: {marker}")

    def test_wrappers_exactly_cover_deterministic_tasks(self):
        expected_ids = {task["id"] for task in self.test_tasks}
        actual_ids = {
            int(match.group(1))
            for directory in ENVIRONMENTS.glob("task_*")
            if (match := re.fullmatch(r"task_(\d+)", directory.name))
            and 2567 <= int(match.group(1)) <= 2769
            and (directory / "tester.py").is_file()
        }
        self.assertEqual(actual_ids, expected_ids)
        for task_id in sorted(expected_ids):
            source = (ENVIRONMENTS / f"task_{task_id}" / "tester.py").read_text(
                encoding="utf-8"
            )
            self.assertIn("from environments.grade8_2026_common import perform_task", source)
            self.assertRegex(source, rf"return perform_task\({task_id}, runner, source_code\)")

    def test_handlers_exactly_cover_wrappers_and_points(self):
        handlers = {}
        for module_name in MODULES:
            module = importlib.import_module(module_name)
            self.assertFalse(set(handlers).intersection(module.TASKS))
            handlers.update(module.TASKS)
        expected = {task["id"]: task["points"] for task in self.test_tasks}
        actual = {task_id: value[0] for task_id, value in handlers.items()}
        self.assertEqual(actual, expected)
        self.assertTrue(all(callable(value[1]) for value in handlers.values()))


if __name__ == "__main__":
    unittest.main()
