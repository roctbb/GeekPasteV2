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
words = [item.strip() for item in input().split(",") if item.strip()]
unique = []
for word in words:
    if word not in unique:
        unique.append(word)
print(", ".join(unique))
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
totals = {}
for _ in range(int(input())):
    row = input()
    name, points = row.split(":")
    totals[name] = totals.get(name, 0) + int(points)
for place, (name, points) in enumerate(
    sorted(totals.items(), key=lambda item: (-item[1], item[0])), 1
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
if rare:
    print(", ".join(rare))
else:
    print("Редких слов нет")
""",
    2457: """
# Синтаксическая ошибка: в def count_even(numbers) пропущено двоеточие.
# Синтаксическая ошибка: в условии использовано = вместо ==.
# Ошибка имени: count_evens вместо count_even.
# Ошибка имени: value вместо values.
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

print(normalize_name("   иВАН   иВАНОВ  "))
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

    def test_stdin_tasks_never_receive_a_sole_empty_line(self):
        class RecordingRunner(LocalRunner):
            def __init__(self, source):
                super().__init__(source)
                self.inputs = []

            def __call__(self, input_data, time_limit=2):
                self.inputs.append(input_data)
                return super().__call__(input_data, time_limit)

        for task_id in (2451, 2452, 2453, 2454, 2456, 2458):
            with self.subTest(task_id=task_id):
                source = REFERENCE_SOLUTIONS[task_id]
                runner = RecordingRunner(source)
                perform_task(task_id, runner, source)
                self.assertTrue(runner.inputs)
                self.assertTrue(
                    all(value.rstrip("\r\n") for value in runner.inputs),
                    f"Task {task_id} contains a sole-empty stdin scenario",
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

    def test_password_error_order_is_exact(self):
        source = REFERENCE_SOLUTIONS[2461].replace(
            "return not errors, errors",
            "return not errors, list(reversed(errors))",
        )
        points, _ = perform_task(2461, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2461])

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

    def test_average_requires_published_and_distinct_executed_checks(self):
        function_source = REFERENCE_SOLUTIONS[2460].split(
            "print(average",
            1,
        )[0]
        repeated = function_source + """
for _ in range(5):
    average([2, 4, 6])
"""
        missing_published = function_source + """
for case in ([2, 4, 6], [10], [-1, 1], [3], [7]):
    average(case)
"""
        never_executed = function_source + """
if 1 == 2:
    for case in ([2, 4, 6], [1.5, 2.5], [], [10], [-1, 1]):
        average(case)
"""
        for source in (repeated, missing_published, never_executed):
            with self.subTest(source=source[-120:]):
                points, _ = perform_task(2460, LocalRunner(source), source)
                self.assertLess(points, TASK_MAX_POINTS[2460])

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
    cases = [
        "   иВАН   иВАНОВ  ",
        "аЛИСА",
        "",
        "анна   мария",
        "  ПЁТР петров ",
        "сЕРГЕЙ иВАНОВИЧ пЕТРОВ",
    ]
    for case in cases:
        print(normalize_name(case))

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

    def test_hardcoded_output_does_not_solve_deduplication(self):
        source = """
input()
print("кот, пёс, лиса, сова")
"""
        points, _ = perform_task(2451, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2451])

    def test_deduplication_requires_comma_separated_output(self):
        source = """
words = [item.strip() for item in input().split(",") if item.strip()]
unique = []
for word in words:
    if word not in unique:
        unique.append(word)
print(" ".join(unique))
"""
        points, _ = perform_task(2451, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2451])

    def test_deduplication_allows_prompt_and_does_not_require_words_name(self):
        source = """
raw = input("Введите слова: ")
items = [item.strip() for item in raw.split(",") if item.strip()]
answer = []
for item in items:
    if item not in answer:
        answer.append(item)
print(", ".join(answer))
"""
        points, comments = perform_task(2451, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2451], comments)

    def test_deduplication_allows_arbitrary_literal_input_prompts(self):
        for prompt in (
            "Список слов: ",
            "Элементы >>> ",
            "Строка? ",
            "Результат: ",
        ):
            with self.subTest(prompt=prompt):
                source = REFERENCE_SOLUTIONS[2451].replace(
                    "input()",
                    f"input({prompt!r})",
                )
                points, comments = perform_task(
                    2451,
                    LocalRunner(source),
                    source,
                )

                self.assertEqual(points, TASK_MAX_POINTS[2451], comments)

    def test_deduplication_rejects_arbitrary_output_prefix(self):
        source = REFERENCE_SOLUTIONS[2451].replace(
            'print(", ".join(unique))',
            'print("Результат: " + ", ".join(unique))',
        )
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

    def test_interest_labels_are_case_sensitive(self):
        mutations = (
            ('print("Общие:"', 'print("общие:"'),
            ('print("Общие:"', 'print("xОбщие:"'),
        )
        for old, new in mutations:
            with self.subTest(new=new):
                source = REFERENCE_SOLUTIONS[2453].replace(old, new)
                points, _ = perform_task(2453, LocalRunner(source), source)

                self.assertLess(points, TASK_MAX_POINTS[2453])

    def test_interest_input_prompts_may_be_arbitrary_literals(self):
        source = REFERENCE_SOLUTIONS[2453].replace(
            'input("Интересы Алисы: ")',
            'input("Введите первую строку >>> ")',
        ).replace(
            'input("Интересы Бориса: ")',
            'input("А теперь вторую? ")',
        )
        points, comments = perform_task(2453, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2453], comments)

        label_prompts = REFERENCE_SOLUTIONS[2453].replace(
            'input("Интересы Алисы: ")',
            'input("Общие: ")',
        ).replace(
            'input("Интересы Бориса: ")',
            'input("Все: ")',
        )
        points, comments = perform_task(
            2453,
            LocalRunner(label_prompts),
            label_prompts,
        )
        self.assertEqual(points, TASK_MAX_POINTS[2453], comments)

    def test_interest_output_rejects_prefix_not_used_by_input(self):
        source = 'print("Введите первую строку: ", end="")\n' + (
            REFERENCE_SOLUTIONS[2453]
        )
        points, _ = perform_task(2453, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2453])

    def test_rare_words_requires_a_frequency_dictionary(self):
        source = """
words = input().lower().split()
rare = sorted({word for word in words if words.count(word) == 1})
if rare:
    print(", ".join(rare))
else:
    print("Редких слов нет")
"""
        points, _ = perform_task(2456, LocalRunner(source), source)

        self.assertEqual(points, 5)

    def test_rare_words_accepts_dict_constructor(self):
        source = REFERENCE_SOLUTIONS[2456].replace("counts = {}", "counts = dict()")
        points, comments = perform_task(2456, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2456], comments)

    def test_rare_words_allows_literal_prompt_but_rejects_output_prefix(self):
        for prompt in ("Строка: ", "Сообщение >>> ", "енот, "):
            with self.subTest(prompt=prompt):
                source = REFERENCE_SOLUTIONS[2456].replace(
                    "Введите текст: ",
                    prompt,
                )
                points, comments = perform_task(2456, LocalRunner(source), source)
                self.assertEqual(points, TASK_MAX_POINTS[2456], comments)

        prefixed = 'print("Строка: ", end="")\n' + REFERENCE_SOLUTIONS[2456]
        points, _ = perform_task(2456, LocalRunner(prefixed), prefixed)
        self.assertLess(points, TASK_MAX_POINTS[2456])

    def test_no_rare_words_message_is_exact(self):
        for replacement in (
            "Редких слов не найдено",
            "редких слов нет",
            "Редких слов нет.",
        ):
            with self.subTest(replacement=replacement):
                source = REFERENCE_SOLUTIONS[2456].replace(
                    "Редких слов нет",
                    replacement,
                )
                points, _ = perform_task(2456, LocalRunner(source), source)

                self.assertLess(points, TASK_MAX_POINTS[2456])

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

    def test_frequency_output_accepts_reasonable_separators(self):
        original = 'print(f"{word}: {count}")'
        for replacement in (
            'print(f"{word} — {count}")',
            'print(f"{word} - {count}")',
            'print(f"{word} = {count}")',
        ):
            with self.subTest(replacement=replacement):
                source = REFERENCE_SOLUTIONS[2452].replace(original, replacement)
                points, comments = perform_task(2452, LocalRunner(source), source)
                self.assertEqual(points, TASK_MAX_POINTS[2452], comments)

    def test_frequency_output_rejects_unrelated_separator(self):
        source = REFERENCE_SOLUTIONS[2452].replace(
            'print(f"{word}: {count}")',
            'print(f"{word} / {count}")',
        )
        points, _ = perform_task(2452, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2452])

    def test_three_rounds_are_accumulated(self):
        source = """
totals = {}
rounds = {}
for _ in range(int(input())):
    row = input()
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

    def test_result_table_requires_declared_numbering(self):
        source = """
totals = {}
for _ in range(int(input())):
    row = input()
    name, raw_points = row.split(":")
    totals[name] = totals.get(name, 0) + int(raw_points)
for name, points in sorted(
    totals.items(),
    key=lambda item: (-item[1], item[0]),
):
    print(f"{name} — {points}")
"""
        points, comments = perform_task(2454, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2454], comments)

    def test_result_table_requires_declared_em_dash(self):
        source = REFERENCE_SOLUTIONS[2454].replace(
            'print(f"{place}. {name} — {points}")',
            'print(f"{place}. {name}: {points}")',
        )
        points, _ = perform_task(2454, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2454])

    def test_result_table_checks_multiword_names_and_negative_scores(self):
        source = """
totals = {}
for _ in range(int(input())):
    name, raw_points = input().split(":")
    name = name.split()[0]
    totals[name] = totals.get(name, 0) + abs(int(raw_points))
for place, (name, points) in enumerate(
    sorted(totals.items(), key=lambda item: (-item[1], item[0])), 1
):
    print(f"{place}. {name} — {points}")
"""
        points, _ = perform_task(2454, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2454])

    def test_result_table_requires_alphabetical_tiebreak(self):
        source = """
totals = {}
for _ in range(int(input())):
    name, raw_points = input().split(":")
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

    def test_inventory_objects_must_be_changed_in_place(self):
        source = """
player = {}
chest = {}
updated_player = player.copy()
for item, amount in chest.items():
    updated_player[item] = updated_player.get(item, 0) + amount
player = updated_player
chest = {}
"""
        points, _ = perform_task(2455, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2455])

    def test_error_comments_must_identify_each_original_fragment(self):
        comment_lines = [
            line
            for line in REFERENCE_SOLUTIONS[2457].splitlines()
            if line.startswith("#")
        ]
        self.assertEqual(len(comment_lines), 5)
        for comment in comment_lines:
            with self.subTest(omitted=comment):
                source = REFERENCE_SOLUTIONS[2457].replace(
                    comment + "\n",
                    "",
                    1,
                )
                points, _ = perform_task(2457, LocalRunner(source), source)

                self.assertLess(points, TASK_MAX_POINTS[2457])

    def test_error_comments_need_types_and_code_fragments(self):
        source = REFERENCE_SOLUTIONS[2457]
        comments = "\n".join(
            line
            for line in source.splitlines()
            if line.startswith("#")
        )
        source = source.replace(
            comments,
            (
                "# Синтаксические ошибки исправлены.\n"
                "# Ошибки имени исправлены.\n"
                "# Логическая ошибка исправлена."
            ),
        )
        points, _ = perform_task(2457, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2457])

    def test_five_errors_must_be_in_separate_comments(self):
        source = REFERENCE_SOLUTIONS[2457]
        comments = "\n".join(
            line
            for line in source.splitlines()
            if line.startswith("#")
        )
        source = source.replace(
            comments,
            (
                "# Синтаксические ошибки: в def count_even(numbers) нет "
                "двоеточия, а в условии стоит = вместо ==; ошибки имени: "
                "count_evens и value; логическая ошибка: return внутри цикла."
            ),
        )
        points, _ = perform_task(2457, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2457])

    def test_return_error_may_be_described_as_wrong_indentation(self):
        source = REFERENCE_SOLUTIONS[2457].replace(
            "# Логическая ошибка: return стоял внутри цикла.",
            (
                "# Логическая ошибка: исходный return count "
                "находится на неверном уровне отступа."
            ),
        )
        points, comments = perform_task(2457, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2457], comments)

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

    def test_statistics_checks_single_and_negative_inputs(self):
        single_wrong = REFERENCE_SOLUTIONS[2458].replace(
            "total = sum(numbers)",
            "total = 0 if len(numbers) == 1 else sum(numbers)",
        )
        negatives_wrong = REFERENCE_SOLUTIONS[2458].replace(
            "minimum = min(numbers)",
            "minimum = min(abs(number) for number in numbers)",
        ) if "minimum = min(numbers)" in REFERENCE_SOLUTIONS[2458] else """
def read_numbers():
    return list(map(int, input().split()))

def calculate_statistics(numbers):
    total = sum(numbers)
    positives = [abs(number) for number in numbers]
    return total, total / len(numbers), min(positives), max(positives)

def show_statistics(statistics):
    total, average, minimum, maximum = statistics
    print("Сумма:", total)
    print("Среднее:", average)
    print("Минимум:", minimum)
    print("Максимум:", maximum)

show_statistics(calculate_statistics(read_numbers()))
"""
        for source in (single_wrong, negatives_wrong):
            with self.subTest(source=source[:80]):
                points, _ = perform_task(2458, LocalRunner(source), source)

                self.assertEqual(points, 10)

    def test_normalize_name_requires_all_published_and_distinct_own_checks(self):
        function = """
def normalize_name(name):
    return " ".join(part.capitalize() for part in name.split())
"""
        missing_published = function + """
for case in ["аЛИСА", "", "анна", "борис", "вера", "глеб"]:
    print(normalize_name(case))
"""
        repeated_own = function + """
for case in [
    "   иВАН   иВАНОВ  ", "аЛИСА", "", "анна", "анна", "анна"
]:
    print(normalize_name(case))
"""
        for source in (missing_published, repeated_own):
            with self.subTest(source=source[-100:]):
                points, _ = perform_task(2459, LocalRunner(source), source)

                self.assertLess(points, TASK_MAX_POINTS[2459])

    def test_normalize_name_requires_every_result_to_be_printed(self):
        source = """
def normalize_name(name):
    return " ".join(part.capitalize() for part in name.split())

cases = [
    "   иВАН   иВАНОВ  ", "аЛИСА", "", "анна", "борис", "вера"
]
for case in cases[:-1]:
    print(normalize_name(case))
last_result = normalize_name(cases[-1])
"""
        points, _ = perform_task(2459, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2459])

    def test_normalize_name_results_may_have_output_labels(self):
        source = """
def normalize_name(name):
    return " ".join(part.capitalize() for part in name.split())

cases = [
    "   иВАН   иВАНОВ  ", "аЛИСА", "", "анна", "борис", "вера"
]
for case in cases:
    print("Результат:", normalize_name(case))
"""
        points, comments = perform_task(2459, LocalRunner(source), source)

        self.assertEqual(points, TASK_MAX_POINTS[2459], comments)

    def test_password_messages_require_exact_case_and_punctuation(self):
        for replacement in ("Нет цифры", "нет цифры."):
            with self.subTest(replacement=replacement):
                source = REFERENCE_SOLUTIONS[2461].replace(
                    '"нет цифры"',
                    f'"{replacement}"',
                )
                points, _ = perform_task(2461, LocalRunner(source), source)

                self.assertLess(points, TASK_MAX_POINTS[2461])

    def test_password_requires_all_published_calls_to_execute(self):
        function_source = REFERENCE_SOLUTIONS[2461].split(
            "for value in",
            1,
        )[0]
        source = function_source + """
if 1 == 2:
    for value in [
        "Python12", "python12", "Password", "PASSWORD1",
        "Pyth on12", "Pw1", "pw 1",
    ]:
        check_password(value)
"""
        points, _ = perform_task(2461, LocalRunner(source), source)

        self.assertLess(points, TASK_MAX_POINTS[2461])

    def test_test_report_requires_exact_case_punctuation_and_summary(self):
        mutations = (
            (
                'f"Тест {number}: пройден"',
                'f"тест {number}: пройден"',
            ),
            ('f"Тест {number}: ошибка — "', 'f"Тест {number}: ошибка - "'),
            (
                'f"Пройдено {passed} из {len(tests)} тестов"',
                'f"Итого пройдено {passed} из {len(tests)} тестов"',
            ),
        )
        for old, new in mutations:
            with self.subTest(old=old):
                source = REFERENCE_SOLUTIONS[2462].replace(old, new)
                self.assertNotEqual(source, REFERENCE_SOLUTIONS[2462])
                points, _ = perform_task(2462, LocalRunner(source), source)

                self.assertLess(points, TASK_MAX_POINTS[2462])

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

    def test_test_system_requires_two_distinct_function_objects(self):
        source = REFERENCE_SOLUTIONS[2462].replace(
            'run_tests(lambda number: number > 0, [(1, True), (-1, True)])',
            'same_function = is_even\nrun_tests(same_function, [(1, True)])',
        )
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
input()
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
