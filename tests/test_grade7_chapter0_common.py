import importlib
import os
import subprocess
import sys
import unittest

from environments.grade7_chapter0_common import TASK_MAX_POINTS, perform_task
from runner import (
    ExecutionContainer,
    ExecutionException,
    SolutionException,
    TestRunner,
    build_isolated_probe_controller,
)


class LocalRunner:
    """Runs trusted test fixtures without Docker; production still uses TestRunner."""

    def __init__(self, source):
        self.source = source

    def __call__(self, input_data, time_limit=2):
        return self.run_source(self.source, input_data, time_limit)

    def run_source(
        self,
        source_code,
        input_data="",
        time_limit=2,
        probe_source=None,
    ):
        isolated = probe_source is not None
        if isolated:
            source_code = build_isolated_probe_controller(
                source_code,
                probe_source,
                input_data,
            )
            input_data = ""
        result = subprocess.run(
            [sys.executable, "-B", "-c", source_code],
            input=input_data,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=time_limit,
        )
        if result.returncode:
            message = result.stderr.strip() or f"exit code {result.returncode}"
            if isolated:
                raise ExecutionException(message)
            raise SolutionException(message)
        return result.stdout


REFERENCE_SOLUTIONS = {
    2451: """
words = ["кот", "пёс", "кот", "лиса", "пёс", "сова"]
unique = []
for word in words:
    if word not in unique:
        unique.append(word)
print(unique)
""",
    2452: """
text = input("Введите текст: ").lower()
for symbol in ",.!?:;":
    text = text.replace(symbol, " ")
counts = {}
for word in text.split():
    counts[word] = counts.get(word, 0) + 1
for word, count in counts.items():
    print(f"{word}: {count}")
""",
    2453: """
alice = {item.strip().lower() for item in input("Интересы Алисы: ").split(",") if item.strip()}
boris = {item.strip().lower() for item in input("Интересы Бориса: ").split(",") if item.strip()}
print("Общие:", ", ".join(sorted(alice & boris)))
print("Все:", ", ".join(sorted(alice | boris)))
print("Только у Алисы:", ", ".join(sorted(alice - boris)))
print("Только у Бориса:", ", ".join(sorted(boris - alice)))
""",
    2454: """
results = ["Алиса:15", "Борис:9", "Алиса:7", "Виктор:12", "Борис:8"]
totals = {}
for row in results:
    name, points = row.split(":")
    totals[name] = totals.get(name, 0) + int(points)
for place, (name, points) in enumerate(
    sorted(totals.items(), key=lambda item: item[1], reverse=True), 1
):
    print(f"{place}. {name} — {points}")
""",
    2455: """
player = {"золото": 3, "ключ": 1}
chest = {"золото": 15, "зелье": 2, "карта": 1}
for item, amount in chest.items():
    player[item] = player.get(item, 0) + amount
chest.clear()
print("__GEEKPASTE_RESULT_fake__", player)
""",
    2456: """
words = input("Введите текст: ").lower().split()
counts = {}
for word in words:
    counts[word] = counts.get(word, 0) + 1
rare = sorted(word for word, count in counts.items() if count == 1)
print(", ".join(rare))
""",
    2457: """
# Синтаксические: пропущено двоеточие и = использовался вместо сравнения.
# Ошибки имени: count_evens вместо count_even, value вместо values.
# Логическая ошибка: return стоял внутри цикла.
def count_even(numbers):
    count = 0
    for number in numbers:
        if number % 2 == 0:
            count += 1
    return count

print(count_even([1, 2, 4, 7, 10]))
print(count_even([]))
print(count_even([1, 3, 5]))
print(count_even([2, 4, 6]))
""",
    2458: """
def read_numbers():
    return list(map(int, input("Введите числа: ").split()))

def calculate_statistics(numbers):
    if not numbers:
        return None
    total = sum(numbers)
    return total, total / len(numbers), min(numbers), max(numbers)

def show_statistics(statistics):
    total, average, minimum, maximum = statistics
    print("Сумма:", total)
    print("Среднее:", average)
    print("Минимум:", minimum)
    print("Максимум:", maximum)

numbers = read_numbers()
statistics = calculate_statistics(numbers)
if statistics is None:
    print("Числа не введены")
else:
    show_statistics(statistics)
""",
    2459: """
def normalize_name(name):
    return " ".join(part.capitalize() for part in name.split())

print(normalize_name("  иВАН иВАНОВ "))
print(normalize_name("аЛИСА"))
print(normalize_name(""))
print(normalize_name("анна   мария"))
print(normalize_name("  ПЁТР петров "))
print(normalize_name("сЕРГЕЙ иВАНОВИЧ пЕТРОВ"))
""",
    2460: """
def average(numbers):
    if not numbers:
        return None
    return sum(numbers) / len(numbers)

print(average([2, 4, 6]))
print(average([1.5, 2.5]))
print(average([]))
print(average([10]))
print(average([-1, 1]))
""",
    2461: """
def check_password(password):
    errors = []
    if len(password) < 8:
        errors.append("короче 8 символов")
    if not any(symbol.isdigit() for symbol in password):
        errors.append("нет цифры")
    if not any(symbol.islower() for symbol in password):
        errors.append("нет строчной буквы")
    if not any(symbol.isupper() for symbol in password):
        errors.append("нет заглавной буквы")
    if " " in password:
        errors.append("есть пробел")
    return not errors, errors

for value in ["Python12", "python12", "Password", "PASSWORD1", "Pyth on12", "Pw1", "pw 1"]:
    print(check_password(value))
""",
    2462: """
def run_tests(function, tests):
    passed = 0
    for number, (argument, expected) in enumerate(tests, 1):
        actual = function(argument)
        if actual == expected:
            passed += 1
            print(f"Тест {number}: пройден")
        else:
            print(
                f"Тест {number}: ошибка — "
                f"ожидалось {expected}, получено {actual}"
            )
    print(f"Пройдено {passed} из {len(tests)} тестов")

def is_even(number):
    return number % 2 == 0

tests = [(2, True), (7, False), (9, True), (-4, True), (-3, False)]
run_tests(is_even, tests)
run_tests(lambda number: number > 0, [(1, True), (-1, True)])
""",
}


FORGED_MARKER_AVERAGE = r"""
import atexit
import inspect
import json


def forge_old_result(function):
    def wrapped(*args, **kwargs):
        marker = None
        frame = inspect.currentframe()
        while frame is not None:
            for constant in frame.f_code.co_consts:
                if (
                    isinstance(constant, str)
                    and constant.startswith("__GEEKPASTE_RESULT_")
                ):
                    marker = constant
            frame = frame.f_back
        if marker:
            payload = {
                "exists": True,
                "results": [
                    {"ok": True, "value": 4.0, "args_after": [[2, 4, 6]]},
                    {"ok": True, "value": 2.0, "args_after": [[1.5, 2.5]]},
                    {"ok": True, "value": None, "args_after": [[]]},
                    {"ok": True, "value": 10.0, "args_after": [[10]]},
                    {"ok": True, "value": 0.0, "args_after": [[-1, 1]]},
                ],
            }
            atexit.register(
                print,
                marker + json.dumps(payload, ensure_ascii=False),
            )
        return 999
    return wrapped


@forge_old_result
def average(numbers):
    return 999


for case in ([2, 4, 6], [1.5, 2.5], [], [10], [-1, 1]):
    print(average(case))
"""


class Grade7Chapter0CheckerTests(unittest.TestCase):
    def test_reference_solutions_receive_exact_maximum(self):
        for task_id, source in REFERENCE_SOLUTIONS.items():
            with self.subTest(task_id=task_id):
                points, comments = perform_task(
                    task_id,
                    LocalRunner(source),
                    source,
                )
                self.assertEqual(
                    points,
                    TASK_MAX_POINTS[task_id],
                    comments,
                )

    def test_completely_broken_function_receives_zero_points(self):
        source = "def count_even(numbers):\n    return 0\n"
        points, comments = perform_task(2457, LocalRunner(source), source)

        self.assertEqual(points, 0)
        self.assertIn("✗", comments)

    def test_syntax_error_receives_zero_points(self):
        source = "def broken(:\n"
        points, comments = perform_task(2457, LocalRunner(source), source)

        self.assertEqual(points, 0)
        self.assertIn("не разбирается", comments)

    def test_password_error_order_is_not_significant(self):
        source = REFERENCE_SOLUTIONS[2461].replace(
            "return not errors, errors",
            "return not errors, list(reversed(errors))",
        )
        points, comments = perform_task(2461, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2461], comments)

    def test_function_harness_preserves_literal_global_constants(self):
        source = REFERENCE_SOLUTIONS[2461].replace(
            "def check_password(password):",
            "MIN_LENGTH = 8\n\ndef check_password(password):",
        ).replace(
            "len(password) < 8",
            "len(password) < MIN_LENGTH",
        )
        points, comments = perform_task(2461, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2461], comments)

    def test_function_harness_preserves_computed_global_constants(self):
        source = REFERENCE_SOLUTIONS[2461].replace(
            "def check_password(password):",
            "MIN_LENGTH = 4 * 2\n\ndef check_password(password):",
        ).replace(
            "len(password) < 8",
            "len(password) < MIN_LENGTH",
        )
        points, comments = perform_task(2461, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2461], comments)

    def test_average_accepts_five_checks_run_from_a_literal_case_list(self):
        function_source = REFERENCE_SOLUTIONS[2460].split(
            "print(average", 1
        )[0]
        source = function_source + """
cases = [[2, 4, 6], [1.5, 2.5], [], [10], [-1, 1]]
for case in cases:
    print(average(case))
"""
        points, comments = perform_task(2460, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2460], comments)

    def test_normalize_name_accepts_six_checks_run_in_a_loop(self):
        source = """
def normalize_name(name):
    return " ".join(part.capitalize() for part in name.split())

cases = [
    "   иВАН   иВАНОВ  ",
    "аЛИСА",
    "",
    "анна   мария",
    "  ПЁТР петров ",
    "сЕРГЕЙ   иВАНОВИЧ   пЕТРОВ",
]
for case in cases:
    print(normalize_name(case))
"""
        points, comments = perform_task(2459, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2459], comments)

    def test_called_test_helpers_count_as_own_checks(self):
        normalize_source = """
def normalize_name(name):
    return " ".join(part.capitalize() for part in name.split())

def test_normalize_name():
    assert normalize_name("  иВАН иВАНОВ ") == "Иван Иванов"
    assert normalize_name("аЛИСА") == "Алиса"
    assert normalize_name("") == ""
    assert normalize_name("анна   мария") == "Анна Мария"
    assert normalize_name("  ПЁТР петров ") == "Пётр Петров"
    assert normalize_name("сЕРГЕЙ иВАНОВИЧ пЕТРОВ") == "Сергей Иванович Петров"

test_normalize_name()
"""
        average_source = """
def average(numbers):
    return sum(numbers) / len(numbers) if numbers else None

def test_average():
    cases = [[2, 4, 6], [1.5, 2.5], [], [10], [-1, 1]]
    for case in cases:
        average(case)

test_average()
"""
        password_function = REFERENCE_SOLUTIONS[2461].split(
            "for value in",
            1,
        )[0]
        password_source = password_function + """
def test_passwords():
    cases = [
        "Python12", "python12", "Password", "PASSWORD1",
        "Pyth on12", "Pw1", "pw 1",
    ]
    for value in cases:
        check_password(value)

test_passwords()
"""
        fixtures = (
            (2459, normalize_source),
            (2460, average_source),
            (2461, password_source),
        )
        for task_id, source in fixtures:
            with self.subTest(task_id=task_id):
                points, comments = perform_task(
                    task_id,
                    LocalRunner(source),
                    source,
                )
                self.assertEqual(
                    points,
                    TASK_MAX_POINTS[task_id],
                    comments,
                )

    def test_uncalled_test_helper_does_not_count(self):
        source = """
def normalize_name(name):
    return " ".join(part.capitalize() for part in name.split())

def test_normalize_name():
    for value in ["a", "b", "c", "d", "e", "f"]:
        normalize_name(value)

if False:
    test_normalize_name()
"""
        points, _ = perform_task(2459, LocalRunner(source), source)

        self.assertEqual(points, 5)

    def test_old_marker_forgery_cannot_replace_trusted_result(self):
        points, _ = perform_task(
            2460,
            LocalRunner(FORGED_MARKER_AVERAGE),
            FORGED_MARKER_AVERAGE,
        )

        self.assertLess(points, TASK_MAX_POINTS[2460])

    def test_precomputed_unrelated_lists_do_not_solve_deduplication(self):
        source = """
words = ["ничего"]
first = ["кот", "пёс", "лиса", "сова"]
second = ["чай", "кофе", "вода"]
third = []
"""
        points, _ = perform_task(2451, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2451])

    def test_duplicate_union_is_rejected_before_set_comparison(self):
        source = """
alice = [item.strip().lower() for item in input().split(",")]
boris = [item.strip().lower() for item in input().split(",")]
alice_set = set(alice)
boris_set = set(boris)
print("Общие:", ", ".join(sorted(alice_set & boris_set)))
print("Все:", ", ".join(alice + boris))
print("Только у Алисы:", ", ".join(sorted(alice_set - boris_set)))
print("Только у Бориса:", ", ".join(sorted(boris_set - alice_set)))
"""
        points, _ = perform_task(2453, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2453])

    def test_rare_words_requires_a_frequency_dictionary(self):
        source = """
words = input().lower().split()
rare = sorted({word for word in words if words.count(word) == 1})
print(", ".join(rare))
"""
        points, _ = perform_task(2456, LocalRunner(source), source)

        self.assertEqual(points, 5)

    def test_clear_no_rare_words_message_is_accepted(self):
        source = """
words = input().lower().split()
counts = {}
for word in words:
    counts[word] = counts.get(word, 0) + 1
rare = sorted(word for word, count in counts.items() if count == 1)
if rare:
    print(", ".join(rare))
else:
    print("Редких слов не найдено")
"""
        points, comments = perform_task(2456, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2456], comments)

    def test_period_is_part_of_frequency_punctuation(self):
        source = """
text = input().lower()
for symbol in ",!?:;":
    text = text.replace(symbol, " ")
counts = {}
for word in text.split():
    counts[word] = counts.get(word, 0) + 1
for word, count in counts.items():
    print(f"{word}: {count}")
"""
        points, _ = perform_task(2452, LocalRunner(source), source)

        self.assertEqual(points, 5)

    def test_three_rounds_are_accumulated(self):
        source = """
results = []
totals = {}
rounds = {}
for row in results:
    name, raw_points = row.split(":")
    rounds[name] = rounds.get(name, 0) + 1
    if rounds[name] <= 2:
        totals[name] = totals.get(name, 0) + int(raw_points)
for name, points in sorted(
    totals.items(),
    key=lambda item: item[1],
    reverse=True,
):
    print(f"{name} — {points}")
"""
        points, _ = perform_task(2454, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2454])

    def test_result_table_does_not_require_numbering(self):
        source = """
results = []
totals = {}
for row in results:
    name, raw_points = row.split(":")
    totals[name] = totals.get(name, 0) + int(raw_points)
for name, points in sorted(
    totals.items(),
    key=lambda item: item[1],
    reverse=True,
):
    print(f"{name} — {points}")
"""
        points, comments = perform_task(2454, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2454], comments)

    def test_two_inventory_overlaps_are_accumulated(self):
        source = """
player = {}
chest = {}
overlap_done = False
for item, amount in chest.items():
    if item in player:
        if not overlap_done:
            player[item] += amount
            overlap_done = True
    else:
        player[item] = amount
chest.clear()
"""
        points, _ = perform_task(2455, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2455])

    def test_dummy_functions_and_hardcoded_statistics_are_rejected(self):
        source = """
def unused_one(value):
    return value

def unused_two(value):
    return value

def unused_three():
    return None

if input().strip():
    print("Сумма: 6")
    print("Среднее: 2")
    print("Минимум: 1")
    print("Максимум: 3")
"""
        points, _ = perform_task(2458, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2458])

    def test_hardcoded_test_report_is_rejected(self):
        source = """
def run_tests(function, tests):
    for argument, expected in tests:
        function(argument)
    print("Тест 1: пройден")
    print("Тест 2: пройден")
    print("Тест 3: ошибка")
    print("Тест 4: пройден")
    print("Тест 5: пройден")
    print("Пройдено 4 из 5 тестов")

def first(number):
    return number % 2 == 0

def second(number):
    return number > 0

run_tests(first, [(2, True), (9, True)])
run_tests(second, [(-1, True)])
"""
        points, _ = perform_task(2462, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2462])

    def test_execution_exception_is_not_scored_as_student_failure(self):
        class FailingRunner:
            def __call__(self, input_data, time_limit=2):
                raise ExecutionException("docker unavailable")

        with self.assertRaisesRegex(ExecutionException, "docker unavailable"):
            perform_task(2452, FailingRunner(), "print(input())")

    def test_solution_exception_receives_zero(self):
        class FailingRunner:
            def __call__(self, input_data, time_limit=2):
                raise SolutionException("student timeout")

        points, _ = perform_task(2452, FailingRunner(), "print(input())")

        self.assertEqual(points, 0)

    def test_oversized_probe_payload_receives_zero(self):
        source = """
def average(numbers):
    return ["x" * 1000] * 1000

for case in ([2], [3], [4], [5], [6]):
    average(case)
"""
        points, _ = perform_task(2460, LocalRunner(source), source)

        self.assertEqual(points, 0)

    def test_oversized_student_stdout_receives_zero(self):
        source = """
words = []
print("x" * 200000)
"""
        points, _ = perform_task(2451, LocalRunner(source), source)

        self.assertEqual(points, 0)

    @unittest.skipUnless(
        os.getenv("RUN_DOCKER_SMOKE") == "1",
        "set RUN_DOCKER_SMOKE=1 for the real Docker cp smoke test",
    )
    def test_forged_marker_is_rejected_in_real_docker_cp_mode(self):
        previous_mode = os.environ.get("DOCKER_TRANSFER_MODE")
        os.environ["DOCKER_TRANSFER_MODE"] = "cp"
        try:
            with ExecutionContainer(
                "python",
                None,
                FORGED_MARKER_AVERAGE,
            ) as container:
                points, _ = perform_task(
                    2460,
                    TestRunner(container),
                    FORGED_MARKER_AVERAGE,
                )
        finally:
            if previous_mode is None:
                os.environ.pop("DOCKER_TRANSFER_MODE", None)
            else:
                os.environ["DOCKER_TRANSFER_MODE"] = previous_mode

        self.assertLess(points, TASK_MAX_POINTS[2460])

    def test_all_thin_wrappers_export_perform_tests(self):
        for task_id in range(2451, 2463):
            with self.subTest(task_id=task_id):
                module = importlib.import_module(
                    f"environments.task_{task_id}.tester"
                )
                self.assertTrue(callable(module.perform_tests))


if __name__ == "__main__":
    unittest.main()
