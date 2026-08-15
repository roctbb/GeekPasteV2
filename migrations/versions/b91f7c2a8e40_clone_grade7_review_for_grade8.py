"""clone the grade 7 Python review tasks for grade 8

Revision ID: b91f7c2a8e40
Revises: a7c0f1e2463b
Create Date: 2026-08-15

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b91f7c2a8e40"
down_revision = "a7c0f1e2463b"
branch_labels = None
depends_on = None


SOURCE_TASK_IDS = tuple(range(2440, 2464))
TARGET_TASK_IDS = tuple(range(2770, 2794))
TARGET_TEST_TASK_IDS = tuple(range(2770, 2793))
TASK_ID_OFFSET = TARGET_TASK_IDS[0] - SOURCE_TASK_IDS[0]


tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("name", sa.String()),
    sa.column("lang", sa.String()),
    sa.column("points", sa.Integer()),
    sa.column("check_type", sa.String()),
    sa.column("text", sa.Text()),
    sa.column("bypass_similarity_check", sa.Boolean()),
    sa.column("gpt_model", sa.String()),
    sa.column("gpt_rate_limit", sa.Integer()),
)


def _starred(name):
    name = name or ""
    return name if name.startswith("★ ") else f"★ {name}"


def upgrade():
    connection = op.get_bind()
    existing_targets = connection.execute(
        sa.select(tasks.c.id).where(tasks.c.id.in_(TARGET_TASK_IDS))
    ).scalars().all()
    if existing_targets:
        raise RuntimeError(
            "Grade 8 Python review task ids already exist: "
            f"{sorted(existing_targets)}"
        )

    source_rows = connection.execute(
        sa.select(tasks)
        .where(tasks.c.id.in_(SOURCE_TASK_IDS))
        .order_by(tasks.c.id)
    ).mappings().all()
    if [row["id"] for row in source_rows] != list(SOURCE_TASK_IDS):
        raise RuntimeError("The source grade 7 Python review tasks are incomplete")
    if any(row["lang"] != "python" for row in source_rows):
        raise RuntimeError("Every source Python review task must use Python")

    cloned_rows = []
    for source in source_rows:
        target_id = source["id"] + TASK_ID_OFFSET
        cloned_rows.append(
            {
                "id": target_id,
                "name": _starred(source["name"]),
                "lang": "python",
                "points": source["points"],
                "check_type": (
                    "tests" if target_id in TARGET_TEST_TASK_IDS else "gpt"
                ),
                "text": source["text"],
                "bypass_similarity_check": source["bypass_similarity_check"],
                "gpt_model": source["gpt_model"],
                "gpt_rate_limit": source["gpt_rate_limit"],
            }
        )

    op.bulk_insert(tasks, cloned_rows)
    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text(
                "SELECT setval(" 
                "'public.tasks_id_seq', "
                "GREATEST(COALESCE((SELECT max(id) FROM tasks), 1), "
                "(SELECT last_value FROM public.tasks_id_seq)), true)"
            )
        )


def downgrade():
    op.execute(tasks.delete().where(tasks.c.id.in_(TARGET_TASK_IDS)))
