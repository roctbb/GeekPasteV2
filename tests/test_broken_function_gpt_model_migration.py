import importlib
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_MODULE = (
    "migrations.versions.a8c0d2e4f6b1_pin_broken_function_gpt_model"
)
TASK_IDS = (2457, 2787)


class BrokenFunctionGptModelMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = importlib.import_module(MIGRATION_MODULE)
        self.engine = sa.create_engine("sqlite://")
        self.metadata = sa.MetaData()
        self.tasks = sa.Table(
            "tasks",
            self.metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("check_type", sa.String),
            sa.Column("gpt_model", sa.String),
        )
        self.metadata.create_all(self.engine)

    def _operations(self, connection):
        return Operations(MigrationContext.configure(connection))

    def test_upgrade_and_downgrade_pin_only_both_course_copies(self):
        with self.engine.begin() as connection:
            connection.execute(
                self.tasks.insert(),
                [
                    {"id": 2456, "check_type": "tests", "gpt_model": None},
                    {"id": 2457, "check_type": "gpt", "gpt_model": None},
                    {"id": 2787, "check_type": "gpt", "gpt_model": None},
                    {"id": 2788, "check_type": "tests", "gpt_model": None},
                ],
            )
            with mock.patch.object(
                self.migration, "op", self._operations(connection)
            ):
                self.migration.upgrade()
                self.migration.upgrade()

            upgraded = dict(
                connection.execute(
                    sa.select(self.tasks.c.id, self.tasks.c.gpt_model)
                ).all()
            )
            self.assertEqual(upgraded[2457], self.migration.GPT_MODEL)
            self.assertEqual(upgraded[2787], self.migration.GPT_MODEL)
            self.assertIsNone(upgraded[2456])
            self.assertIsNone(upgraded[2788])

            with mock.patch.object(
                self.migration, "op", self._operations(connection)
            ):
                self.migration.downgrade()
                self.migration.downgrade()

            downgraded = dict(
                connection.execute(
                    sa.select(self.tasks.c.id, self.tasks.c.gpt_model)
                ).all()
            )
            self.assertTrue(
                all(downgraded[task_id] is None for task_id in TASK_IDS)
            )

    def test_non_gpt_task_is_rejected(self):
        with self.engine.begin() as connection:
            connection.execute(
                self.tasks.insert(),
                [
                    {"id": 2457, "check_type": "tests", "gpt_model": None},
                    {"id": 2787, "check_type": "gpt", "gpt_model": None},
                ],
            )
            with mock.patch.object(
                self.migration, "op", self._operations(connection)
            ):
                with self.assertRaisesRegex(RuntimeError, "not configured for GPT"):
                    self.migration.upgrade()


if __name__ == "__main__":
    unittest.main()
