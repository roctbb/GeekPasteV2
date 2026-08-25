"""pin a supported GPT model for the broken-function review task

Revision ID: a8c0d2e4f6b1
Revises: f7b2c4d6e8a0
Create Date: 2026-08-25

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a8c0d2e4f6b1"
down_revision = "f7b2c4d6e8a0"
branch_labels = None
depends_on = None


TASK_IDS = (2457, 2787)
GPT_MODEL = "gpt-5.3-codex"

tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("check_type", sa.String()),
    sa.column("gpt_model", sa.String()),
)


def _set_model(expected, replacement):
    connection = op.get_bind()
    for task_id in TASK_IDS:
        current = connection.execute(
            sa.select(tasks.c.check_type, tasks.c.gpt_model).where(
                tasks.c.id == task_id
            )
        ).one_or_none()
        if current is None:
            raise RuntimeError(f"Broken-function task {task_id} is missing")
        if current.check_type != "gpt":
            raise RuntimeError(
                f"Broken-function task {task_id} is not configured for GPT"
            )
        if current.gpt_model == replacement:
            continue
        if current.gpt_model != expected:
            raise RuntimeError(
                f"Broken-function task {task_id} has unexpected gpt_model "
                f"{current.gpt_model!r}"
            )
        connection.execute(
            tasks.update()
            .where(tasks.c.id == task_id)
            .values(gpt_model=replacement)
        )


def upgrade():
    _set_model(None, GPT_MODEL)


def downgrade():
    _set_model(GPT_MODEL, None)
