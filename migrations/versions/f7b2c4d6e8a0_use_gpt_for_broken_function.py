"""use GPT for the broken-function review task

Revision ID: f7b2c4d6e8a0
Revises: e5a9c1d4f7b2
Create Date: 2026-08-25

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7b2c4d6e8a0"
down_revision = "e5a9c1d4f7b2"
branch_labels = None
depends_on = None


TASK_IDS = (2457, 2787)

tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("check_type", sa.String()),
)


def _set_check_type(expected, replacement):
    connection = op.get_bind()
    for task_id in TASK_IDS:
        current = connection.execute(
            sa.select(tasks.c.check_type).where(tasks.c.id == task_id)
        ).scalar_one_or_none()
        if current is None:
            raise RuntimeError(f"Broken-function task {task_id} is missing")
        if current == replacement:
            continue
        if current != expected:
            raise RuntimeError(
                f"Broken-function task {task_id} has unexpected check_type {current!r}"
            )
        connection.execute(
            tasks.update()
            .where(tasks.c.id == task_id)
            .values(check_type=replacement)
        )


def upgrade():
    _set_check_type("tests", "gpt")


def downgrade():
    _set_check_type("gpt", "tests")
