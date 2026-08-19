import importlib
import hashlib
import json
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_MODULE = (
    "migrations.versions.c4a2d8e71f90_clarify_python_review_task_prompts"
)
EXPECTED_SOURCE_IDS = (
    2441,
    2445,
    2447,
    2448,
    2449,
    2451,
    2453,
    2454,
    2455,
    2456,
    2457,
    2458,
    2459,
    2461,
    2462,
)


class PythonReviewPromptMigrationTests(unittest.TestCase):
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

    def test_payload_contains_exactly_the_fifteen_prompt_pairs(self):
        self.assertEqual(
            self.payload["format"],
            "geekpaste-grade7-grade8-review-prompts-v1",
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
            self.assertNotEqual(entry["old_text"], entry["new_text"])

    def test_new_prompts_drop_obsolete_and_empty_stdin_requirements(self):
        by_id = {entry["source_id"]: entry for entry in self.entries}

        turnstile = by_id[2441]
        self.assertEqual(
            hashlib.md5(turnstile["old_text"].encode()).hexdigest(),
            "34a58ffb5ff76a225ad7fcc79dc99c58",
        )
        self.assertIn("второй строки ввода нет", turnstile["new_text"])
        for exact_answer in (
            "Проход разрешён",
            "Для прохода нужен билет",
            "Непонятный ответ",
        ):
            self.assertIn(exact_answer, turnstile["new_text"])

        for task_id in (2445, 2451, 2458):
            prompt = by_id[task_id]["new_text"].lower()
            self.assertNotIn("пустой ввод", prompt)
            self.assertNotIn("пустая строка", prompt)
            self.assertNotIn("не ввёл ни одного", prompt)

        interests_prompt = by_id[2453]["new_text"].lower()
        self.assertNotIn("<br", interests_prompt)
        self.assertNotIn("↵", interests_prompt)
        self.assertNotIn("переход на новую строку", interests_prompt)

        self.assertIn("одного числа", by_id[2458]["new_text"].lower())
        self.assertIn("в этом же порядке", by_id[2461]["new_text"].lower())

        password_prompt = by_id[2448]["new_text"]
        password_lines = (
            "- короче 8 символов",
            "- нет цифры",
            "- нет строчной буквы",
            "- нет заглавной буквы",
            "- есть пробел",
        )
        self.assertIn("Пароль подходит", password_prompt)
        self.assertIn("Пароль не подходит:", password_prompt)
        positions = [password_prompt.index(line) for line in password_lines]
        self.assertEqual(positions, sorted(positions))

        ranking_prompt = by_id[2454]["new_text"]
        self.assertIn("`N. Имя — баллы`", ranking_prompt)
        self.assertIn("начиная с 1", ranking_prompt)

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
