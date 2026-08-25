"""add interest input examples

Revision ID: d1e3f5a7b9c2
Revises: a8c0d2e4f6b1
Create Date: 2026-08-25

"""

import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1e3f5a7b9c2"
down_revision = "a8c0d2e4f6b1"
branch_labels = None
depends_on = None


DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "d1e3f5a7b9c2_interest_input_examples.json"
)

tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("text", sa.Text()),
)


def _entry():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if payload.get("format") != "geekpaste-interest-input-examples-v1":
        raise RuntimeError("Unexpected GeekPaste interest-example payload")
    entries = payload.get("tasks")
    if not isinstance(entries, list) or len(entries) != 1:
        raise RuntimeError("Interest-example payload must contain one task pair")

    entry = entries[0]
    if set(entry) != {"source_id", "target_id", "old_text", "new_text"}:
        raise RuntimeError("Unexpected interest-example entry fields")
    if entry["source_id"] != 2453 or entry["target_id"] != 2783:
        raise RuntimeError("Unexpected interest-example task ids")
    if not isinstance(entry["old_text"], str) or not entry["old_text"]:
        raise RuntimeError("Interest task is missing exact old_text")
    if not isinstance(entry["new_text"], str) or not entry["new_text"]:
        raise RuntimeError("Interest task is missing new_text")
    if entry["old_text"] == entry["new_text"]:
        raise RuntimeError("Interest task has identical old and new prompts")
    return entry


def _apply_texts(from_key, to_key):
    connection = op.get_bind()
    entry = _entry()
    for task_id in (entry["source_id"], entry["target_id"]):
        current = connection.execute(
            sa.select(tasks.c.text).where(tasks.c.id == task_id)
        ).scalar_one_or_none()
        if current is None:
            raise RuntimeError(f"Interest task {task_id} is missing")

        expected = entry[from_key]
        replacement = entry[to_key]
        if current == replacement:
            continue
        if current != expected:
            raise RuntimeError(f"Interest task {task_id} has unexpected text")
        connection.execute(
            tasks.update().where(tasks.c.id == task_id).values(text=replacement)
        )


def upgrade():
    _apply_texts("old_text", "new_text")


def downgrade():
    _apply_texts("new_text", "old_text")
