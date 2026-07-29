"""enable test checkers for the grade 7 introduction tasks

Revision ID: a7c0f1e2463b
Revises: 5b3d67532215
Create Date: 2026-07-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7c0f1e2463b"
down_revision = "5b3d67532215"
branch_labels = None
depends_on = None


tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("check_type", sa.String()),
)

GRADE7_INTRO_TEST_TASK_IDS = tuple(range(2440, 2463))


def upgrade():
    op.execute(
        tasks.update()
        .where(tasks.c.id.in_(GRADE7_INTRO_TEST_TASK_IDS))
        .values(check_type="tests")
    )


def downgrade():
    op.execute(
        tasks.update()
        .where(tasks.c.id.in_(GRADE7_INTRO_TEST_TASK_IDS))
        .where(tasks.c.check_type == "tests")
        .values(check_type="gpt")
    )
