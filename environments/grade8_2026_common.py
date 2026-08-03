import importlib
import json
import math
import re

from runner import ExecutionException, SolutionException


_CHAPTER_MODULES = (
    "environments.grade8_2026_chapters_1_4",
    "environments.grade8_2026_chapters_5_6",
    "environments.grade8_2026_chapters_7_8",
)
_TASKS = None


def _load_tasks():
    global _TASKS
    if _TASKS is None:
        tasks = {}
        for module_name in _CHAPTER_MODULES:
            module = importlib.import_module(module_name)
            overlap = set(tasks).intersection(module.TASKS)
            if overlap:
                raise ExecutionException(
                    f"Повторяющиеся проверяющие сценарии: {sorted(overlap)}"
                )
            tasks.update(module.TASKS)
        _TASKS = tasks
    return _TASKS


def perform_task(task_id, runner, source_code=None):
    entry = _load_tasks().get(task_id)
    if entry is None:
        raise ExecutionException(
            f"Для задачи #{task_id} не найден проверяющий сценарий."
        )
    maximum, handler = entry
    source_code = source_code or ""
    try:
        points, comment = handler(runner, source_code)
    except ExecutionException:
        raise
    except SolutionException as error:
        return 0, "Решение завершилось с ошибкой или превысило лимит времени."
    except Exception as error:
        raise ExecutionException(
            f"Внутренняя ошибка проверяющего сценария задачи #{task_id}."
        ) from error
    if not isinstance(points, int) or points < 0 or points > maximum:
        raise ExecutionException(
            f"Проверяющий сценарий #{task_id} вернул недопустимые баллы."
        )
    return points, comment


def normalize_tokens(value):
    return str(value).replace("\r", "").split()


def tokens_equal(actual, expected):
    return normalize_tokens(actual) == normalize_tokens(expected)


def casefold_tokens_equal(actual, expected):
    return [item.casefold() for item in normalize_tokens(actual)] == [
        item.casefold() for item in normalize_tokens(expected)
    ]


def exact_text_equal(actual, expected):
    return str(actual).replace("\r\n", "\n").rstrip() == str(expected).replace(
        "\r\n", "\n"
    ).rstrip()


def float_tokens_equal(actual, expected, tolerance=1e-6):
    actual_tokens = normalize_tokens(actual)
    expected_tokens = normalize_tokens(expected)
    if len(actual_tokens) != len(expected_tokens):
        return False
    try:
        pairs = zip(map(float, actual_tokens), map(float, expected_tokens))
        return all(
            math.isfinite(left)
            and math.isfinite(right)
            and abs(left - right) <= tolerance * max(1.0, abs(right))
            for left, right in pairs
        )
    except ValueError:
        return False


def unordered_lines_equal(actual, expected):
    clean = lambda value: sorted(
        line.strip()
        for line in str(value).replace("\r", "").splitlines()
        if line.strip()
    )
    return clean(actual) == clean(expected)


def json_equal(actual, expected):
    try:
        return json.loads(actual) == (
            json.loads(expected) if isinstance(expected, str) else expected
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def run_case(runner, case, default_comparator=tokens_equal):
    comparator = case.get("comparator", default_comparator)
    capture_limit = case.get("capture_limit")
    if capture_limit is None:
        output = runner(case.get("input", ""), case.get("time_limit", 1))
    else:
        if not isinstance(capture_limit, int) or not 102400 <= capture_limit <= 4 * 1024 * 1024:
            raise ExecutionException("Некорректный лимит вывода скрытого теста.")
        output = runner(
            case.get("input", ""),
            case.get("time_limit", 1),
            capture_limit,
        )
    return comparator(output, case.get("expected", ""))


def run_case_group(runner, cases, default_comparator=tokens_equal):
    try:
        return all(run_case(runner, case, default_comparator) for case in cases)
    except SolutionException:
        return False


def finish_groups(task_id, maximum, runner, groups, comparator=tokens_equal):
    if maximum <= 0 or maximum % 5 or len(groups) != maximum // 5:
        raise ExecutionException(
            f"Некорректная разбивка критериев задачи #{task_id}."
        )
    results = [run_case_group(runner, group, comparator) for group in groups]
    points = sum(5 for passed in results if passed)
    lines = [
        f"{'✓' if passed else '✗'} группа скрытых проверок {index}"
        for index, passed in enumerate(results, start=1)
    ]
    heading = f"Результат: {points}/{maximum} баллов."
    return points, "\n".join([heading, *lines])


def finish_criteria(task_id, maximum, criteria):
    if maximum <= 0 or maximum % 5 or len(criteria) != maximum // 5:
        raise ExecutionException(
            f"Некорректная разбивка критериев задачи #{task_id}."
        )
    points = sum(5 for passed, _ in criteria if passed)
    lines = [f"{'✓' if passed else '✗'} {message}" for passed, message in criteria]
    return points, "\n".join([f"Результат: {points}/{maximum} баллов.", *lines])


def source_has_all(source_code, patterns):
    return all(re.search(pattern, source_code, flags=re.I | re.S) for pattern in patterns)


def source_has_none(source_code, patterns):
    return not any(re.search(pattern, source_code, flags=re.I | re.S) for pattern in patterns)


def cpp_harness_source(source_code, harness_body):
    return (
        "#define main __geekpaste_student_main\n"
        + source_code
        + "\n#undef main\n"
        + harness_body
        + "\n"
    )


def run_cpp_harness(
    runner,
    source_code,
    harness_body,
    input_data="",
    time_limit=3,
    compile_options=None,
):
    source = cpp_harness_source(source_code, harness_body)
    if compile_options is None:
        return runner.run_source(source, input_data, time_limit)
    return runner.run_source(
        source,
        input_data,
        time_limit,
        compile_options=compile_options,
    )


def run_cpp_harness_case(runner, source_code, case, default_comparator=tokens_equal):
    try:
        output = run_cpp_harness(
            runner,
            source_code,
            case["harness"],
            case.get("input", ""),
            case.get("time_limit", 3),
            case.get("compile_options"),
        )
        return case.get("comparator", default_comparator)(output, case["expected"])
    except SolutionException:
        return False
