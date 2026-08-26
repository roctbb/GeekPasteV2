"""use GPT for the test-system review task

Revision ID: e2f4a6c8b0d3
Revises: d1e3f5a7b9c2
Create Date: 2026-08-26

"""

import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e2f4a6c8b0d3"
down_revision = "d1e3f5a7b9c2"
branch_labels = None
depends_on = None


TASK_IDS = (2462, 2792)
GPT_MODEL = "gpt-5.3-codex"
DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "e2f4a6c8b0d3_test_system_gpt.json"
)

tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("check_type", sa.String()),
    sa.column("gpt_model", sa.String()),
    sa.column("text", sa.Text()),
)


def _entry():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if payload.get("format") != "geekpaste-test-system-gpt-v1":
        raise RuntimeError("Unexpected test-system GPT payload")
    entries = payload.get("tasks")
    if not isinstance(entries, list) or len(entries) != 1:
        raise RuntimeError("Test-system GPT payload must contain one task pair")

    entry = entries[0]
    if set(entry) != {"source_id", "target_id", "old_text", "new_text"}:
        raise RuntimeError("Unexpected test-system GPT entry fields")
    if (entry["source_id"], entry["target_id"]) != TASK_IDS:
        raise RuntimeError("Unexpected test-system task ids")
    if not isinstance(entry["old_text"], str) or not entry["old_text"]:
        raise RuntimeError("Test-system task is missing exact old_text")
    if not isinstance(entry["new_text"], str) or not entry["new_text"]:
        raise RuntimeError("Test-system task is missing new_text")
    if entry["old_text"] == entry["new_text"]:
        raise RuntimeError("Test-system task has identical old and new prompts")
    return entry


def _apply(expected, replacement):
    connection = op.get_bind()
    entry = _entry()
    for task_id in TASK_IDS:
        current = connection.execute(
            sa.select(
                tasks.c.check_type,
                tasks.c.gpt_model,
                tasks.c.text,
            ).where(tasks.c.id == task_id)
        ).one_or_none()
        if current is None:
            raise RuntimeError(f"Test-system task {task_id} is missing")

        expected_type, expected_model, expected_text = expected
        new_type, new_model, new_text = replacement
        if current.check_type not in (expected_type, new_type):
            raise RuntimeError(
                f"Test-system task {task_id} has unexpected check_type "
                f"{current.check_type!r}"
            )
        if current.gpt_model not in (expected_model, new_model):
            raise RuntimeError(
                f"Test-system task {task_id} has unexpected gpt_model "
                f"{current.gpt_model!r}"
            )
        if current.text not in (expected_text, new_text):
            raise RuntimeError(
                f"Test-system task {task_id} has unexpected text"
            )

        if (
            current.check_type,
            current.gpt_model,
            current.text,
        ) != replacement:
            connection.execute(
                tasks.update().where(tasks.c.id == task_id).values(
                    check_type=new_type,
                    gpt_model=new_model,
                    text=new_text,
                )
            )


def upgrade():
    entry = _entry()
    _apply(
        ("tests", None, entry["old_text"]),
        ("gpt", GPT_MODEL, entry["new_text"]),
    )


def downgrade():
    entry = _entry()
    _apply(
        ("gpt", GPT_MODEL, entry["new_text"]),
        ("tests", None, entry["old_text"]),
    )
