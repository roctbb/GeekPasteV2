import importlib
import unittest


migration = importlib.import_module(
    'migrations.versions.f3a5c7e9b1d4_require_json_only_for_nandgame'
)


class NandgameJsonOnlyMigrationTests(unittest.TestCase):
    def test_transform_is_reversible_for_every_task(self):
        for task_id in migration.TASK_IDS:
            with self.subTest(task_id=task_id):
                old = '\n\n'.join(old for old, _new in migration.REPLACEMENTS[task_id])
                new = migration._transform(old, task_id, True)
                self.assertEqual(migration._transform(new, task_id, False), old)

    def test_new_prompts_require_json_only_and_no_explanations(self):
        for task_id in migration.TASK_IDS:
            with self.subTest(task_id=task_id):
                old = '\n\n'.join(old for old, _new in migration.REPLACEMENTS[task_id])
                new = migration._transform(old, task_id, True)
                self.assertIn('JSON', new)
                self.assertIn('Markdown-обрамления', new)
                self.assertNotIn('вместе с объяснениями', new)
                self.assertNotIn('ИИ по объяснению', new)


if __name__ == '__main__':
    unittest.main()
