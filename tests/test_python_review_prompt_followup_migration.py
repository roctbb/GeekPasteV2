import hashlib
import importlib
import json
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_MODULE = (
    "migrations.versions.e5a9c1d4f7b2_fix_review_prompt_scoring"
)
EXPECTED_SOURCE_IDS = (2456, 2459)
PRODUCTION_OLD_MD5 = {
    2456: "faf38aab2ab44ce1963e27711beb9d3c",
    2459: "cbaafe194786e4f0dbd8f23d09bb1e0e",
}


class PythonReviewPromptFollowupMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = importlib.import_module(MIGRATION_MODULE)
        self.payload = json.loads(
            self.migration.DATA_PATH.read_text(encoding="utf-8")
        )
        self.entries = self.payload["tasks"]

    def _database(self, overrides=None, omitted=()):
        overrides = overrides or {}
        omitted = set(omitted)
        engine = sa.create_engine("sqlite://")
        metadata = sa.MetaData()
        task_table = sa.Table(
            "tasks",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("text", sa.Text, nullable=False),
        )
        metadata.create_all(engine)

        rows = []
        for entry in self.entries:
            for task_id in (entry["source_id"], entry["target_id"]):
                if task_id in omitted:
                    continue
                rows.append({
                    "id": task_id,
                    "text": overrides.get(task_id, entry["old_text"]),
                })
        return engine, task_table, rows

    def _texts(self, connection, task_table, entry):
        return connection.execute(
            sa.select(task_table.c.text)
            .where(task_table.c.id.in_((
                entry["source_id"],
                entry["target_id"],
            )))
            .order_by(task_table.c.id)
        ).scalars().all()

    def test_payload_contains_exactly_the_two_prompt_pairs(self):
        self.assertEqual(
            self.payload["format"],
            "geekpaste-python-review-prompt-scoring-fixes-v1",
        )
        self.assertEqual(
            tuple(entry["source_id"] for entry in self.entries),
            EXPECTED_SOURCE_IDS,
        )
        self.assertEqual(
            tuple(entry["target_id"] for entry in self.entries),
            tuple(task_id + 330 for task_id in EXPECTED_SOURCE_IDS),
        )
        for entry in self.entries:
            self.assertEqual(
                set(entry),
                {"source_id", "target_id", "old_text", "new_text"},
            )
            self.assertEqual(
                hashlib.md5(entry["old_text"].encode()).hexdigest(),
                PRODUCTION_OLD_MD5[entry["source_id"]],
            )
            self.assertNotEqual(entry["old_text"], entry["new_text"])

    def test_new_rare_words_prompt_scores_only_program_behavior(self):
        rare_words = self.entries[0]["new_text"]
        self.assertIn("это только рекомендация", rare_words)
        self.assertIn("оценивается поведение программы", rare_words)
        self.assertNotIn("нужно решить с использованием словаря", rare_words)
        scoring = rare_words.split("**Оценивание:**", 1)[1]
        self.assertNotIn("словар", scoring.lower())

    def test_new_normalize_prompt_shows_single_spaces_and_accepts_equivalent_whitespace(self):
        normalize = self.entries[1]["new_text"]
        self.assertIn('normalize_name(" иВАН иВАНОВ ")', normalize)
        self.assertNotIn('normalize_name("   иВАН   иВАНОВ  ")', normalize)
        self.assertIn("точное количество пробельных символов", normalize.lower())
        self.assertIn(
            "в начале, между словами и в конце может быть один или несколько",
            normalize,
        )

    def test_upgrade_and_downgrade_are_idempotent_and_keep_pairs_in_sync(self):
        engine, task_table, rows = self._database()
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                self.migration.upgrade()
                self.migration.upgrade()

            for entry in self.entries:
                self.assertEqual(
                    self._texts(connection, task_table, entry),
                    [entry["new_text"], entry["new_text"]],
                )

            with mock.patch.object(self.migration, "op", operations):
                self.migration.downgrade()
                self.migration.downgrade()

            for entry in self.entries:
                self.assertEqual(
                    self._texts(connection, task_table, entry),
                    [entry["old_text"], entry["old_text"]],
                )

    def test_upgrade_converges_a_partially_updated_pair(self):
        first = self.entries[0]
        engine, task_table, rows = self._database({
            first["source_id"]: first["new_text"],
        })
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                self.migration.upgrade()
            self.assertEqual(
                self._texts(connection, task_table, first),
                [first["new_text"], first["new_text"]],
            )

    def test_upgrade_rejects_text_that_matches_neither_exact_version(self):
        first = self.entries[0]
        engine, task_table, rows = self._database({
            first["source_id"]: "unexpected production prompt",
        })
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                with self.assertRaisesRegex(
                    RuntimeError,
                    f"task {first['source_id']} has unexpected text",
                ):
                    self.migration.upgrade()

    def test_upgrade_rejects_a_missing_task_from_either_course(self):
        missing_id = self.entries[0]["target_id"]
        engine, task_table, rows = self._database(omitted=(missing_id,))
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                with self.assertRaisesRegex(
                    RuntimeError,
                    f"task {missing_id} is missing",
                ):
                    self.migration.upgrade()


if __name__ == "__main__":
    unittest.main()
