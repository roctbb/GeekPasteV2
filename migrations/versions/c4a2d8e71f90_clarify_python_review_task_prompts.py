"""clarify Python review task prompts

Revision ID: c4a2d8e71f90
Revises: b91f7c2a8e40
Create Date: 2026-08-19

"""

import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4a2d8e71f90"
down_revision = "b91f7c2a8e40"
branch_labels = None
depends_on = None


DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "c4a2d8e71f90_geekpaste_review_prompts.json"
)

EXPECTED_SOURCE_IDS = (
    2441,
    2445,
    2447,
    2448,
    2449,
    2451,
    2453,
    2454,
    2455,
    2456,
    2457,
    2458,
    2459,
    2461,
    2462,
)

tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("text", sa.Text()),
)


def _entries():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if payload.get("format") != "geekpaste-grade7-grade8-review-prompts-v1":
        raise RuntimeError("Unexpected GeekPaste review-prompt payload")
    entries = payload.get("tasks")
    if not isinstance(entries, list) or len(entries) != len(EXPECTED_SOURCE_IDS):
        raise RuntimeError("GeekPaste review-prompt payload must contain 15 tasks")

    source_ids = [entry.get("source_id") for entry in entries]
    target_ids = [entry.get("target_id") for entry in entries]
    if source_ids != list(EXPECTED_SOURCE_IDS):
        raise RuntimeError("Unexpected source GeekPaste review task ids")
    if target_ids != [task_id + 330 for task_id in EXPECTED_SOURCE_IDS]:
        raise RuntimeError("Unexpected target GeekPaste review task ids")

    expected_keys = {"source_id", "target_id", "old_text", "new_text"}
    for entry in entries:
        if set(entry) != expected_keys:
            raise RuntimeError("Unexpected GeekPaste review-prompt entry fields")
        if not isinstance(entry["old_text"], str):
            raise RuntimeError("Review task is missing exact old_text")
        if not isinstance(entry["new_text"], str):
            raise RuntimeError("Review task is missing exact new_text")
        if not entry["old_text"] or not entry["new_text"]:
            raise RuntimeError("Review task prompt text must not be empty")
        if entry["old_text"] == entry["new_text"]:
            raise RuntimeError("Review task has identical old and new prompts")
    return entries


def _apply_texts(from_key, to_key):
    connection = op.get_bind()
    for entry in _entries():
        for task_id in (entry["source_id"], entry["target_id"]):
            current = connection.execute(
                sa.select(tasks.c.text).where(tasks.c.id == task_id)
            ).scalar_one_or_none()
            if current is None:
                raise RuntimeError(f"Python review task {task_id} is missing")

            expected = entry[from_key]
            replacement = entry[to_key]
            if current == replacement:
                continue
            if current != expected:
                raise RuntimeError(
                    f"Python review task {task_id} has unexpected text"
                )
            connection.execute(
                tasks.update()
                .where(tasks.c.id == task_id)
                .values(text=replacement)
            )


def upgrade():
    _apply_texts("old_text", "new_text")


def downgrade():
    _apply_texts("new_text", "old_text")
