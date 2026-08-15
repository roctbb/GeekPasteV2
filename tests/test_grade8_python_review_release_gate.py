import importlib
from pathlib import Path
import unittest
from unittest import mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from score_policy import GRADE8_2026_TASK_IDS, ZERO_SCORE_TEST_TASK_IDS


MIGRATION_MODULE = (
    "migrations.versions.b91f7c2a8e40_clone_grade7_review_for_grade8"
)
SOURCE_TASK_IDS = tuple(range(2440, 2464))
TARGET_TASK_IDS = tuple(range(2770, 2794))
TARGET_TEST_TASK_IDS = tuple(range(2770, 2793))


def _task_table(metadata):
    return sa.Table(
        "tasks",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String),
        sa.Column("lang", sa.String),
        sa.Column("points", sa.Integer),
        sa.Column("check_type", sa.String),
        sa.Column("text", sa.Text),
        sa.Column("bypass_similarity_check", sa.Boolean),
        sa.Column("gpt_model", sa.String),
        sa.Column("gpt_rate_limit", sa.Integer),
    )


class Grade8PythonReviewReleaseGateTests(unittest.TestCase):
    def test_migration_clones_content_and_makes_every_task_optional(self):
        migration = importlib.import_module(MIGRATION_MODULE)
        engine = sa.create_engine("sqlite://")
        metadata = sa.MetaData()
        tasks = _task_table(metadata)
        metadata.create_all(engine)

        source_rows = []
        for task_id in SOURCE_TASK_IDS:
            source_rows.append(
                {
                    "id": task_id,
                    "name": (
                        f"★ Source {task_id}"
                        if task_id in {2444, 2449, 2450, 2456, 2462}
                        else f"Source {task_id}"
                    ),
                    "lang": "python",
                    "points": 5 + task_id % 4 * 5,
                    "check_type": "gpt" if task_id == 2463 else "tests",
                    "text": f"Task text {task_id}",
                    "bypass_similarity_check": False,
                    "gpt_model": None,
                    "gpt_rate_limit": None,
                }
            )

        with engine.begin() as connection:
            connection.execute(tasks.insert(), source_rows)
            operations = Operations(MigrationContext.configure(connection))
            with mock.patch.object(migration, "op", operations):
                migration.upgrade()

            cloned = connection.execute(
                sa.select(tasks)
                .where(tasks.c.id.in_(TARGET_TASK_IDS))
                .order_by(tasks.c.id)
            ).mappings().all()
            self.assertEqual([row["id"] for row in cloned], list(TARGET_TASK_IDS))

            for source, target in zip(source_rows, cloned):
                self.assertTrue(target["name"].startswith("★ "))
                self.assertEqual(target["name"].removeprefix("★ "), source["name"].removeprefix("★ "))
                self.assertEqual(target["lang"], "python")
                self.assertEqual(target["points"], source["points"])
                self.assertEqual(target["text"], source["text"])
                self.assertEqual(
                    target["check_type"],
                    "gpt" if target["id"] == 2793 else "tests",
                )

            with mock.patch.object(migration, "op", operations):
                migration.downgrade()
            remaining = connection.execute(
                sa.select(tasks.c.id).order_by(tasks.c.id)
            ).scalars().all()
            self.assertEqual(remaining, list(SOURCE_TASK_IDS))

    def test_every_test_task_reuses_the_matching_grade7_checker(self):
        for source_id, target_id in zip(
            range(2440, 2463),
            TARGET_TEST_TASK_IDS,
        ):
            with self.subTest(source_id=source_id, target_id=target_id):
                source = importlib.import_module(
                    f"environments.task_{source_id}.tester"
                )
                target = importlib.import_module(
                    f"environments.task_{target_id}.tester"
                )
                self.assertIs(target.perform_tests, source.perform_tests)

    def test_reflection_stays_on_gpt_without_a_tester(self):
        repository = Path(__file__).resolve().parents[1]
        self.assertFalse(
            (repository / "environments" / "task_2793" / "tester.py").exists()
        )

    def test_scoring_policy_includes_the_new_grade8_tasks(self):
        self.assertTrue(
            set(TARGET_TEST_TASK_IDS).issubset(ZERO_SCORE_TEST_TASK_IDS)
        )
        self.assertTrue(set(TARGET_TASK_IDS).issubset(GRADE8_2026_TASK_IDS))


if __name__ == "__main__":
    unittest.main()
