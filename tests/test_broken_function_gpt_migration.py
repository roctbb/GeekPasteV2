import importlib
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from score_policy import ZERO_SCORE_GPT_TASK_IDS, normalize_gpt_points


MIGRATION_MODULE = (
    "migrations.versions.f7b2c4d6e8a0_use_gpt_for_broken_function"
)
TASK_IDS = (2457, 2787)


class BrokenFunctionGptMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = importlib.import_module(MIGRATION_MODULE)
        self.engine = sa.create_engine("sqlite://")
        self.metadata = sa.MetaData()
        self.tasks = sa.Table(
            "tasks",
            self.metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("check_type", sa.String),
        )
        self.metadata.create_all(self.engine)

    def _operations(self, connection):
        return Operations(MigrationContext.configure(connection))

    def test_upgrade_and_downgrade_change_only_both_course_copies(self):
        with self.engine.begin() as connection:
            connection.execute(
                self.tasks.insert(),
                [
                    {"id": 2456, "check_type": "tests"},
                    {"id": 2457, "check_type": "tests"},
                    {"id": 2787, "check_type": "tests"},
                    {"id": 2788, "check_type": "tests"},
                ],
            )
            with mock.patch.object(
                self.migration, "op", self._operations(connection)
            ):
                self.migration.upgrade()
                self.migration.upgrade()

            upgraded = dict(
                connection.execute(
                    sa.select(self.tasks.c.id, self.tasks.c.check_type)
                ).all()
            )
            self.assertEqual(upgraded[2457], "gpt")
            self.assertEqual(upgraded[2787], "gpt")
            self.assertEqual(upgraded[2456], "tests")
            self.assertEqual(upgraded[2788], "tests")

            with mock.patch.object(
                self.migration, "op", self._operations(connection)
            ):
                self.migration.downgrade()
                self.migration.downgrade()

            downgraded = dict(
                connection.execute(
                    sa.select(self.tasks.c.id, self.tasks.c.check_type)
                ).all()
            )
            self.assertTrue(
                all(downgraded[task_id] == "tests" for task_id in TASK_IDS)
            )

    def test_unexpected_state_is_rejected(self):
        with self.engine.begin() as connection:
            connection.execute(
                self.tasks.insert(),
                [
                    {"id": 2457, "check_type": "manual"},
                    {"id": 2787, "check_type": "tests"},
                ],
            )
            with mock.patch.object(
                self.migration, "op", self._operations(connection)
            ):
                with self.assertRaisesRegex(RuntimeError, "unexpected check_type"):
                    self.migration.upgrade()

    def test_gpt_rubric_receives_attempt_point(self):
        self.assertFalse(set(TASK_IDS) & ZERO_SCORE_GPT_TASK_IDS)
        self.assertEqual(normalize_gpt_points(2457, "python", 0, 15), 1)
        self.assertEqual(normalize_gpt_points(2787, "python", 0, 15), 1)


if __name__ == "__main__":
    unittest.main()
