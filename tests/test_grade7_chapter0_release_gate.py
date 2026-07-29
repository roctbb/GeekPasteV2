import importlib
from pathlib import Path
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from environments.grade7_chapter0_common import TASK_MAX_POINTS
from environments.grade7_chapter0_io import TASK_SPECS
from score_policy import ZERO_SCORE_TEST_TASK_IDS


EXPECTED_TEST_TASK_IDS = frozenset(range(2440, 2463))
MIGRATION_MODULE = (
    "migrations.versions.a7c0f1e2463b_enable_grade7_intro_tests"
)


class Grade7Chapter0ReleaseGateTests(unittest.TestCase):
    def test_checker_specs_cover_exactly_the_migrated_tasks(self):
        io_ids = frozenset(TASK_SPECS)
        common_ids = frozenset(TASK_MAX_POINTS)
        migration = importlib.import_module(MIGRATION_MODULE)

        self.assertFalse(io_ids & common_ids)
        self.assertEqual(io_ids | common_ids, EXPECTED_TEST_TASK_IDS)
        self.assertEqual(
            frozenset(migration.GRADE7_INTRO_TEST_TASK_IDS),
            EXPECTED_TEST_TASK_IDS,
        )
        self.assertEqual(ZERO_SCORE_TEST_TASK_IDS, EXPECTED_TEST_TASK_IDS)

    def test_every_migrated_task_has_an_importable_tester(self):
        for task_id in EXPECTED_TEST_TASK_IDS:
            with self.subTest(task_id=task_id):
                module = importlib.import_module(
                    f"environments.task_{task_id}.tester"
                )
                self.assertTrue(callable(module.perform_tests))

    def test_migration_changes_only_the_programming_tasks(self):
        migration = importlib.import_module(MIGRATION_MODULE)
        engine = sa.create_engine("sqlite://")
        metadata = sa.MetaData()
        tasks = sa.Table(
            "tasks",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("check_type", sa.String),
        )
        metadata.create_all(engine)

        with engine.begin() as connection:
            connection.execute(
                tasks.insert(),
                [
                    {"id": task_id, "check_type": "gpt"}
                    for task_id in range(2439, 2464)
                ],
            )
            operations = Operations(MigrationContext.configure(connection))

            with mock.patch.object(migration, "op", operations):
                migration.upgrade()

            upgraded = dict(
                connection.execute(
                    sa.select(tasks.c.id, tasks.c.check_type)
                ).all()
            )
            self.assertEqual(upgraded[2439], "gpt")
            self.assertEqual(upgraded[2463], "gpt")
            self.assertTrue(
                all(
                    upgraded[task_id] == "tests"
                    for task_id in EXPECTED_TEST_TASK_IDS
                )
            )

            connection.execute(
                tasks.update()
                .where(tasks.c.id == 2441)
                .values(check_type="manual")
            )
            with mock.patch.object(migration, "op", operations):
                migration.downgrade()

            downgraded = dict(
                connection.execute(
                    sa.select(tasks.c.id, tasks.c.check_type)
                ).all()
            )
            self.assertEqual(downgraded[2441], "manual")
            self.assertTrue(
                all(
                    downgraded[task_id] == "gpt"
                    for task_id in EXPECTED_TEST_TASK_IDS - {2441}
                )
            )

    def test_reflection_remains_without_a_test_checker(self):
        repository = Path(__file__).resolve().parents[1]
        reflection_tester = repository / "environments" / "task_2463" / "tester.py"
        self.assertFalse(reflection_tester.exists())


if __name__ == "__main__":
    unittest.main()
