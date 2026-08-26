import hashlib
import importlib
import json
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from score_policy import ZERO_SCORE_GPT_TASK_IDS, normalize_gpt_points


MIGRATION_MODULE = (
    "migrations.versions.e2f4a6c8b0d3_use_gpt_for_test_system"
)
TASK_IDS = (2462, 2792)
PRODUCTION_OLD_SHA256 = (
    "2c162ebf014447aed57a25e3431d22b815843496a6b4b4006e500444204d3529"
)


class TestSystemGptMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = importlib.import_module(MIGRATION_MODULE)
        self.payload = json.loads(
            self.migration.DATA_PATH.read_text(encoding="utf-8")
        )
        self.entry = self.payload["tasks"][0]
        self.engine = sa.create_engine("sqlite://")
        metadata = sa.MetaData()
        self.tasks = sa.Table(
            "tasks",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("check_type", sa.String),
            sa.Column("gpt_model", sa.String),
            sa.Column("text", sa.Text),
        )
        metadata.create_all(self.engine)

    def _operations(self, connection):
        return Operations(MigrationContext.configure(connection))

    def _rows(self, overrides=None, omitted=()):
        overrides = overrides or {}
        omitted = set(omitted)
        default = {
            "check_type": "tests",
            "gpt_model": None,
            "text": self.entry["old_text"],
        }
        return [
            {"id": task_id, **default, **overrides.get(task_id, {})}
            for task_id in TASK_IDS
            if task_id not in omitted
        ]

    def _states(self, connection):
        return connection.execute(
            sa.select(
                self.tasks.c.id,
                self.tasks.c.check_type,
                self.tasks.c.gpt_model,
                self.tasks.c.text,
            ).order_by(self.tasks.c.id)
        ).all()

    def test_payload_matches_production_and_marks_starter_code(self):
        self.assertEqual(
            self.payload["format"],
            "geekpaste-test-system-gpt-v1",
        )
        self.assertEqual(
            hashlib.sha256(self.entry["old_text"].encode()).hexdigest(),
            PRODUCTION_OLD_SHA256,
        )
        self.assertIn("фрагмент стартовым кодом", self.entry["new_text"])
        self.assertIn("Повторять их в своём решении не обязательно", self.entry["new_text"])

    def test_upgrade_and_downgrade_are_idempotent(self):
        with self.engine.begin() as connection:
            connection.execute(self.tasks.insert(), self._rows())
            with mock.patch.object(
                self.migration,
                "op",
                self._operations(connection),
            ):
                self.migration.upgrade()
                self.migration.upgrade()

            for row in self._states(connection):
                self.assertEqual(row.check_type, "gpt")
                self.assertEqual(row.gpt_model, self.migration.GPT_MODEL)
                self.assertEqual(row.text, self.entry["new_text"])

            with mock.patch.object(
                self.migration,
                "op",
                self._operations(connection),
            ):
                self.migration.downgrade()
                self.migration.downgrade()

            for row in self._states(connection):
                self.assertEqual(row.check_type, "tests")
                self.assertIsNone(row.gpt_model)
                self.assertEqual(row.text, self.entry["old_text"])

    def test_upgrade_converges_partial_state(self):
        with self.engine.begin() as connection:
            connection.execute(
                self.tasks.insert(),
                self._rows({
                    2462: {
                        "check_type": "gpt",
                        "gpt_model": self.migration.GPT_MODEL,
                    },
                }),
            )
            with mock.patch.object(
                self.migration,
                "op",
                self._operations(connection),
            ):
                self.migration.upgrade()
            self.assertTrue(
                all(row.check_type == "gpt" for row in self._states(connection))
            )

    def test_upgrade_rejects_unexpected_or_missing_task(self):
        with self.engine.begin() as connection:
            connection.execute(
                self.tasks.insert(),
                self._rows({2462: {"check_type": "manual"}}),
            )
            with mock.patch.object(
                self.migration,
                "op",
                self._operations(connection),
            ):
                with self.assertRaisesRegex(RuntimeError, "unexpected check_type"):
                    self.migration.upgrade()

        engine = sa.create_engine("sqlite://")
        self.tasks.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(self.tasks.insert(), self._rows(omitted=(2792,)))
            with mock.patch.object(
                self.migration,
                "op",
                self._operations(connection),
            ):
                with self.assertRaisesRegex(RuntimeError, "task 2792 is missing"):
                    self.migration.upgrade()

    def test_gpt_rubric_preserves_real_zeroes(self):
        self.assertTrue(set(TASK_IDS).issubset(ZERO_SCORE_GPT_TASK_IDS))
        self.assertEqual(normalize_gpt_points(2462, "python", 0, 20), 0)
        self.assertEqual(normalize_gpt_points(2792, "python", 0, 20), 0)


if __name__ == "__main__":
    unittest.main()
