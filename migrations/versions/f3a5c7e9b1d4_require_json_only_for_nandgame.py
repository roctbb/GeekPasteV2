"""require JSON-only submissions for nandgame tasks

Revision ID: f3a5c7e9b1d4
Revises: e2f4a6c8b0d3
Create Date: 2026-09-04

"""

import hashlib

from alembic import op
import sqlalchemy as sa


revision = "f3a5c7e9b1d4"
down_revision = "e2f4a6c8b0d3"
branch_labels = None
depends_on = None


TASK_IDS = (2570, 2582, 2586, 2589, 2590, 2592)
OLD_SHA256 = {
    2570: "424c92e634f6f5011c375080ebf93b295cea2d1912bb00f3014eeaea20fbfe58",
    2582: "886edba4c560db47036081d08471ce1466f6da485c9daa6d2495c5eee5dd5ea6",
    2586: "01972952ae1b597aef04a7b1ff6999470e7aa635ea3d13203f03c1fb039b211c",
    2589: "a5d4d926ec81a4ef4286210f3d975daf9947c68e35ac5b80775ce9a207534a8b",
    2590: "126a87633a89fd20bef70cc77da1b54bf85a2db15079d01f28cbcf737fd95170",
    2592: "2dc704bcb5b2c8e918c354e1d1c3df24b4ccb344edce45e7993b190cc0f3d5b5",
}

OLD_GENERIC_GPT_APPENDIX = (
    "## Правило проверки в GeekPaste\n\n"
    "ИИ оценивает присланный текст или код по всем ограничениям, примерам и критериям выше и выставляет "
    "целое число от 0 до 15. Полный балл ставится только за полностью рабочее решение; существенно неполное, некомпилируемое или не относящееся к задаче решение получает 0. "
    "Если в условии требуется конкретная алгоритмическая сложность или запрещённый приём, нарушение этого требования не считается правильным решением."
)

def _new_gpt_appendix(points):
    return (
        "## Правило проверки в GeekPaste\n\n"
        "Принимайте только один корректный JSON-объект, полученный кнопкой `Export` в nandgame. "
        "Markdown-обрамление, комментарии, объяснения и любой другой текст до или после JSON не допускаются. "
        "Оцените прогресс по указанным в условии уровням и выставьте целое число "
        f"от 0 до {points}."
    )

OLD_TEST_APPENDIX = (
    "## Формат сдачи для автоматической проверки\n\n"
    "Сначала вставьте без изменений полный JSON из кнопки `Export`."
)
NEW_TEST_APPENDIX = (
    "## Формат сдачи для автоматической проверки\n\n"
    "Вставьте без изменений полный JSON из кнопки `Export`. Проверка принимает только один JSON-объект: "
    "без Markdown-обрамления, комментариев, объяснений и любого другого текста до или после JSON."
)

REPLACEMENTS = {
    2570: (
        (
            "Пришлите этот JSON вместе с объяснениями.",
            "Пришлите только этот JSON без Markdown-обрамления, комментариев и любого другого текста.",
        ),
        (OLD_TEST_APPENDIX, NEW_TEST_APPENDIX),
    ),
    2582: (
        (
            "* **5 баллов** — пройдены `Subtraction`, `Equal to Zero` и `Less than Zero`, и к ним приложено объяснение в две-три фразы: как соединены переносы, почему старший разряд считается последним и по какому признаку схема понимает, что результат отрицательный.",
            "* **5 баллов** — пройдены `Subtraction`, `Equal to Zero` и `Less than Zero`.",
        ),
        (
            "**Как сдать:** JSON-экспортом прогресса со страницы настроек игры вместе с объяснениями.",
            "**Как сдать:** пришлите только JSON-экспорт прогресса со страницы настроек игры — без Markdown-обрамления, комментариев и любого другого текста.",
        ),
        ("**Проверка:** nandgame + ИИ по объяснению", "**Проверка:** по JSON-экспорту nandgame"),
        (OLD_GENERIC_GPT_APPENDIX, _new_gpt_appendix(15)),
    ),
    2586: (
        (
            "* **5 баллов** — пройдены `Counter` и `RAM`, и к ним приложено объяснение в две-три фразы: что делает адрес, что делает сигнал записи и почему при чтении остальные ячейки не мешают.",
            "* **5 баллов** — пройдены `Counter` и `RAM`.",
        ),
        (
            "**Как сдать:** JSON-экспортом прогресса вместе с объяснениями.",
            "**Как сдать:** пришлите только JSON-экспорт прогресса — без Markdown-обрамления, комментариев и любого другого текста.",
        ),
        ("**Проверка:** nandgame + ИИ по объяснению", "**Проверка:** по JSON-экспорту nandgame"),
        (OLD_GENERIC_GPT_APPENDIX, _new_gpt_appendix(15)),
    ),
    2589: (
        (
            "* **5 баллов** — пройден `Computer`, и к нему приложено объяснение в три-четыре фразы: откуда процессор берёт очередную команду, что происходит со счётчиком команд и как выполняется переход.",
            "* **5 баллов** — пройден `Computer`.",
        ),
        (
            "**Как сдать:** JSON-экспортом прогресса вместе с объяснениями.",
            "**Как сдать:** пришлите только JSON-экспорт прогресса — без Markdown-обрамления, комментариев и любого другого текста.",
        ),
        ("**Проверка:** nandgame + ИИ по объяснению", "**Проверка:** по JSON-экспорту nandgame"),
        (OLD_GENERIC_GPT_APPENDIX, _new_gpt_appendix(15)),
    ),
    2590: (
        (
            "* **5 баллов** — написана программа поиска большего числа, и к ней приложена таблица трассировки для двух наборов входных данных: когда первое число больше и когда больше второе.",
            "* **5 баллов** — написана программа поиска большего числа.",
        ),
        (
            "**Как сдать:** JSON-экспортом прогресса; текст программы и обе таблицы трассировки приложите отдельно.",
            "**Как сдать:** пришлите только JSON-экспорт прогресса — без Markdown-обрамления, комментариев и любого другого текста.",
        ),
        ("**Проверка:** nandgame + ИИ по объяснению", "**Проверка:** по JSON-экспорту nandgame"),
        (OLD_GENERIC_GPT_APPENDIX, _new_gpt_appendix(15)),
    ),
    2592: (
        (
            "**Как сдать:** JSON-экспортом прогресса вместе с текстом программы и таблицей трассировки первых трёх оборотов цикла (значения счётчика, накопителя и адреса следующей команды).",
            "**Как сдать:** пришлите только JSON-экспорт прогресса — без Markdown-обрамления, комментариев и любого другого текста.",
        ),
        (
            "* **5 баллов** — в программе есть цикл с переходом назад и проверкой условия выхода, а таблица трассировки заполнена верно и объясняет, как программа узнаёт, что пора остановиться.",
            "* **5 баллов** — в программе есть цикл с переходом назад и проверкой условия выхода.",
        ),
        ("**Проверка:** nandgame + ИИ по трассировке", "**Проверка:** по JSON-экспорту nandgame"),
        (OLD_GENERIC_GPT_APPENDIX.replace("0 до 15", "0 до 10"), _new_gpt_appendix(10)),
    ),
}

tasks = sa.table(
    "tasks",
    sa.column("id", sa.Integer()),
    sa.column("text", sa.Text()),
)


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _replace_once(text, old, new):
    newline = "\r\n" if "\r\n" in text else "\n"
    old = old.replace("\n", newline)
    new = new.replace("\n", newline)
    if text.count(old) != 1:
        raise RuntimeError("Expected prompt fragment exactly once")
    return text.replace(old, new, 1)


def _transform(text, task_id, forward=True):
    pairs = REPLACEMENTS[task_id]
    if not forward:
        pairs = tuple((new, old) for old, new in reversed(pairs))
    for old, new in pairs:
        text = _replace_once(text, old, new)
    return text


def _upgrade_text(text, task_id):
    if _sha256(text) == OLD_SHA256[task_id]:
        return _transform(text, task_id, True)
    old = _transform(text, task_id, False)
    if _sha256(old) != OLD_SHA256[task_id] or _transform(old, task_id, True) != text:
        raise RuntimeError(f"Nandgame task {task_id} has unexpected text")
    return text


def _downgrade_text(text, task_id):
    if _sha256(text) == OLD_SHA256[task_id]:
        return text
    old = _transform(text, task_id, False)
    if _sha256(old) != OLD_SHA256[task_id]:
        raise RuntimeError(f"Nandgame task {task_id} has unexpected text")
    return old


def _apply(transform):
    connection = op.get_bind()
    for task_id in TASK_IDS:
        current = connection.execute(
            sa.select(tasks.c.text).where(tasks.c.id == task_id)
        ).scalar_one_or_none()
        if current is None:
            raise RuntimeError(f"Nandgame task {task_id} is missing")
        replacement = transform(current, task_id)
        if replacement != current:
            connection.execute(
                tasks.update().where(tasks.c.id == task_id).values(text=replacement)
            )


def upgrade():
    _apply(_upgrade_text)


def downgrade():
    _apply(_downgrade_text)
