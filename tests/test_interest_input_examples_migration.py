import hashlib
import importlib
import json
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_MODULE = (
    "migrations.versions.d1e3f5a7b9c2_add_interest_input_examples"
)
PRODUCTION_OLD_SHA256 = (
    "c29e22c992a128f3be8dda6122ed3abb8e4fd4862e19b28b2254671fc30bfb32"
)


class InterestInputExamplesMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = importlib.import_module(MIGRATION_MODULE)
        self.payload = json.loads(
            self.migration.DATA_PATH.read_text(encoding="utf-8")
        )
        self.entry = self.payload["tasks"][0]

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
        rows = [
            {
                "id": task_id,
                "text": overrides.get(task_id, self.entry["old_text"]),
            }
            for task_id in (2453, 2783)
            if task_id not in omitted
        ]
        return engine, task_table, rows

    def _texts(self, connection, task_table):
        return connection.execute(
            sa.select(task_table.c.text)
            .where(task_table.c.id.in_((2453, 2783)))
            .order_by(task_table.c.id)
        ).scalars().all()

    def test_payload_matches_production_and_documents_spacing_variants(self):
        self.assertEqual(
            self.payload["format"],
            "geekpaste-interest-input-examples-v1",
        )
        self.assertEqual(self.entry["source_id"], 2453)
        self.assertEqual(self.entry["target_id"], 2783)
        self.assertEqual(
            hashlib.sha256(self.entry["old_text"].encode()).hexdigest(),
            PRODUCTION_OLD_SHA256,
        )
        prompt = self.entry["new_text"]
        self.assertIn("Чтение,МУЗЫКА", prompt)
        self.assertIn("чтение ,  спорт", prompt)
        self.assertIn("Пример 2 — пробелы рядом с запятыми", prompt)

    def test_upgrade_and_downgrade_are_idempotent_and_keep_pair_in_sync(self):
        engine, task_table, rows = self._database()
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                self.migration.upgrade()
                self.migration.upgrade()
            self.assertEqual(
                self._texts(connection, task_table),
                [self.entry["new_text"], self.entry["new_text"]],
            )

            with mock.patch.object(self.migration, "op", operations):
                self.migration.downgrade()
                self.migration.downgrade()
            self.assertEqual(
                self._texts(connection, task_table),
                [self.entry["old_text"], self.entry["old_text"]],
            )

    def test_upgrade_converges_partially_updated_pair(self):
        engine, task_table, rows = self._database({
            2453: self.entry["new_text"],
        })
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                self.migration.upgrade()
            self.assertEqual(
                self._texts(connection, task_table),
                [self.entry["new_text"], self.entry["new_text"]],
            )

    def test_upgrade_rejects_unexpected_or_missing_task(self):
        engine, task_table, rows = self._database({2453: "unexpected"})
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Interest task 2453 has unexpected text",
                ):
                    self.migration.upgrade()

        engine, task_table, rows = self._database(omitted=(2783,))
        with engine.begin() as connection:
            connection.execute(task_table.insert(), rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(self.migration, "op", operations):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Interest task 2783 is missing",
                ):
                    self.migration.upgrade()


if __name__ == "__main__":
    unittest.main()
