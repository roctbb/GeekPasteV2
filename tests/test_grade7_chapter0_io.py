import importlib
import unittest

from environments.grade7_chapter0_io import (
    MAX_STDOUT_BYTES,
    TASK_SPECS,
    perform_task,
)
from runner import ExecutionException


EXPECTED_TASKS = {
    2440: (5, 5),
    2441: (10, 6),
    2442: (10, 9),
    2443: (15, 9),
    2444: (15, 7),
    2445: (10, 7),
    2446: (10, 8),
    2447: (15, 9),
    2448: (15, 9),
    2449: (15, 8),
    2450: (20, 9),
}


def runner_for(spec, failed_key=None, variant_index=0, reverse_password=False):
    cases = {case.input_data: case for case in spec.cases}

    def runner(input_data):
        case = cases[input_data]
        if case.key == failed_key:
            return "Любое приглашение: заведомо неправильный ответ\n"

        variants = case.expected
        chosen_index = min(variant_index, len(variants) - 1)
        lines = list(variants[chosen_index])
        if reverse_password and case.matcher == "password" and len(lines) > 2:
            lines = lines[:1] + list(reversed(lines[1:]))
        return "Собственные приглашения ученика: " + "\n".join(lines) + "\n"

    return runner


def runner_with_override(spec, case_key, replacement):
    reference = runner_for(spec)
    target = next(case for case in spec.cases if case.key == case_key)

    def runner(input_data):
        if input_data == target.input_data:
            if isinstance(replacement, Exception):
                raise replacement
            return replacement
        return reference(input_data)

    return runner


def shift_text(text, shift, alphabet):
    result = []
    for character in text:
        lower = character.lower()
        if lower not in alphabet:
            result.append(character)
            continue
        replacement = alphabet[(alphabet.index(lower) + shift) % len(alphabet)]
        result.append(replacement.upper() if character.isupper() else replacement)
    return "".join(result)


class Grade7Chapter0IOTests(unittest.TestCase):
    def assert_not_max(self, task_id, runner):
        spec = TASK_SPECS[task_id]
        points, feedback = perform_task(task_id, runner)
        self.assertGreaterEqual(points, 0)
        self.assertLess(points, spec.max_points)
        return feedback

    def test_specs_match_published_ids_points_and_case_counts(self):
        self.assertEqual(set(TASK_SPECS), set(EXPECTED_TASKS))
        for task_id, (max_points, case_count) in EXPECTED_TASKS.items():
            spec = TASK_SPECS[task_id]
            self.assertEqual(spec.max_points, max_points)
            self.assertEqual(len(spec.cases), case_count)

    def test_adversarial_cases_are_present_verbatim(self):
        inputs = {
            task_id: {case.input_data for case in spec.cases}
            for task_id, spec in TASK_SPECS.items()
        }
        self.assertTrue({"-5\n0\n", "0\n3\n"} <= inputs[2442])
        self.assertTrue(
            {"5\n8\n5\n", "10\n1\n2\n", "1\n10\n2\n"} <= inputs[2443]
        )
        self.assertIn("10\n15\n3000\n", inputs[2444])
        self.assertTrue(
            {
                "А? роза упала. на лапу Азора\n",
                "А, роза упала на лапу Азора!\n",
            }
            <= inputs[2446]
        )
        self.assertTrue({"abbba\n", "aAAa\n", "  a \n"} <= inputs[2447])
        self.assertTrue({"aaaaaaaaaaaa\n", "aAAa\n", "a  \n"} <= inputs[2449])
        self.assertTrue({"Az-9!\n27\n", "z\n55\n", "яЯ\n67\n"} <= inputs[2450])

    def test_all_reference_outputs_receive_exact_maximum(self):
        for task_id, spec in TASK_SPECS.items():
            with self.subTest(task_id=task_id):
                points, feedback = perform_task(task_id, runner_for(spec))
                self.assertEqual(points, spec.max_points)
                self.assertIn("Все", feedback)

    def test_each_failed_required_case_reduces_non_caesar_score(self):
        for task_id, spec in TASK_SPECS.items():
            if task_id == 2450:
                continue
            for case in spec.cases:
                with self.subTest(task_id=task_id, case=case.key):
                    feedback = self.assert_not_max(
                        task_id,
                        runner_for(spec, failed_key=case.key),
                    )
                    self.assertIn("Проблемные проверки", feedback)
                    self.assertIn(case.label, feedback)

    def test_completely_wrong_solution_receives_zero(self):
        def wrong_runner(input_data):
            del input_data
            return "неверный ответ\n"

        for task_id, spec in TASK_SPECS.items():
            with self.subTest(task_id=task_id):
                points, _ = perform_task(task_id, wrong_runner)
                self.assertEqual(points, 0)
                self.assertLess(points, spec.max_points)

    def test_partial_solution_keeps_five_point_criterion_scale(self):
        spec = TASK_SPECS[2441]
        reference = runner_for(spec)

        def age_only_runner(input_data):
            if input_data in {"6\nнет\n", "0\nнет\n"}:
                return reference(input_data)
            return "неверный ответ\n"

        points, _ = perform_task(2441, age_only_runner)
        self.assertEqual(points, 5)

    def test_statistics_requires_one_text_traversal(self):
        spec = TASK_SPECS[2445]
        runner = runner_for(spec)
        four_passes = """
text = input()
letters = sum(1 for symbol in text if symbol.isalpha())
digits = sum(1 for symbol in text if symbol.isdigit())
spaces = sum(1 for symbol in text if symbol.isspace())
others = sum(1 for symbol in text if not (
    symbol.isalpha() or symbol.isdigit() or symbol.isspace()
))
"""
        points, feedback = perform_task(2445, runner, four_passes)
        self.assertEqual(points, 5)
        self.assertIn("за один проход", feedback)

    def test_statistics_recognizes_zero_as_a_digit(self):
        def forgets_zero(input_data):
            text = input_data.rstrip("\n")
            letters = digits = spaces = others = 0
            for symbol in text:
                if symbol.isalpha():
                    letters += 1
                elif symbol in "123456789":
                    digits += 1
                elif symbol.isspace():
                    spaces += 1
                else:
                    others += 1
            return (
                f"Букв: {letters}\n"
                f"Цифр: {digits}\n"
                f"Пробелов: {spaces}\n"
                f"Других символов: {others}\n"
            )

        source = """
text = input()
for symbol in text:
    pass
"""
        points, _ = perform_task(2445, forgets_zero, source)
        self.assertLess(points, TASK_SPECS[2445].max_points)

    def test_prompts_and_whitespace_before_answer_are_ignored(self):
        spec = TASK_SPECS[2445]
        cases = {case.input_data: case for case in spec.cases}

        def runner(input_data):
            answer = "\n\n".join(cases[input_data].expected[0])
            return "\nВведите что-нибудь:\t   \n" + answer + "  \n"

        points, _ = perform_task(
            2445,
            runner,
            source_code=(
                "text = input()\n"
                "for symbol in text:\n"
                "    print(symbol)\n"
            ),
        )
        self.assertEqual(points, spec.max_points)

    def test_turnstile_accepts_only_an_explicit_error(self):
        spec = TASK_SPECS[2441]
        clear_error = runner_with_override(
            spec,
            "4",
            "Возраст: Билет: Ошибка: укажите «да» или «нет»\n",
        )
        points, _ = perform_task(2441, clear_error)
        self.assertEqual(points, spec.max_points)

        instruction_only = runner_with_override(
            spec,
            "4",
            "Ответьте только «да» или «нет»\n",
        )
        self.assert_not_max(2441, instruction_only)

        contradictory = runner_with_override(
            spec,
            "4",
            "Проход разрешён\nОшибка: непонятный ответ\n",
        )
        self.assert_not_max(2441, contradictory)

        without_newline = runner_with_override(spec, "4", "Ошибка: непонятный ответ")
        points, _ = perform_task(2441, without_newline)
        self.assertEqual(points, spec.max_points)

        allowed_without_newline_or_yo = runner_with_override(
            spec,
            "1",
            "Проход разрешен",
        )
        points, _ = perform_task(2441, allowed_without_newline_or_yo)
        self.assertEqual(points, spec.max_points)

    def test_password_problem_order_is_not_significant(self):
        spec = TASK_SPECS[2448]
        points, _ = perform_task(
            2448,
            runner_for(spec, reverse_password=True),
        )
        self.assertEqual(points, spec.max_points)

        prompt_with_requirement = runner_with_override(
            spec,
            "1",
            "Подсказка: пароль должен быть не короче 8 символов. Пароль подходит\n",
        )
        points, _ = perform_task(2448, prompt_with_requirement)
        self.assertEqual(points, spec.max_points)

    def test_password_accepts_clear_semantic_problem_wording(self):
        spec = TASK_SPECS[2448]
        reference = runner_for(spec)
        replacements = {
            "python12\n": "Пароль не подходит:\n- не хватает заглавной буквы\n",
            "Password\n": "Пароль не подходит:\n- не хватает цифры\n",
            "PASSWORD1\n": "Пароль не подходит:\n- без строчных букв\n",
            "Pyth on12\n": "Пароль не подходит:\n- пробелы запрещены\n",
            "Pw1\n": "Пароль не подходит:\n- пароль слишком короткий\n",
            "pw 1\n": (
                "Пароль не подходит:\n"
                "- пароль слишком короткий\n"
                "- не хватает заглавной буквы\n"
                "- пробелы запрещены\n"
            ),
        }

        def semantic_runner(input_data):
            return replacements.get(input_data, reference(input_data))

        points, feedback = perform_task(2448, semantic_runner)
        self.assertEqual(points, spec.max_points, feedback)

    def test_password_rejects_contradictory_and_unknown_results(self):
        spec = TASK_SPECS[2448]
        contradictory = runner_with_override(
            spec,
            "1",
            "Пароль не подходит:\nПароль подходит\n",
        )
        self.assert_not_max(2448, contradictory)

        unknown_problem = runner_with_override(
            spec,
            "2",
            "Пароль не подходит:\n- нет заглавной буквы\n- слишком простой\n",
        )
        self.assert_not_max(2448, unknown_problem)

    def test_triangle_mutants_are_rejected(self):
        def misses_first_third_equality(input_data):
            first, second, third = map(int, input_data.split())
            sides = sorted((first, second, third))
            if sides[0] + sides[1] <= sides[2]:
                answer = "Треугольник не существует"
            elif first == second == third:
                answer = "Равносторонний треугольник"
            elif first == second or second == third:
                answer = "Равнобедренный треугольник"
            else:
                answer = "Разносторонний треугольник"
            return answer + "\n"

        def assumes_third_side_is_largest(input_data):
            first, second, third = map(int, input_data.split())
            if first + second <= third:
                answer = "Треугольник не существует"
            elif first == second == third:
                answer = "Равносторонний треугольник"
            elif first == second or first == third or second == third:
                answer = "Равнобедренный треугольник"
            else:
                answer = "Разносторонний треугольник"
            return answer + "\n"

        self.assert_not_max(2443, misses_first_third_equality)
        self.assert_not_max(2443, assumes_third_side_is_largest)

    def test_turnstile_age_boundary_mutant_is_rejected(self):
        def treats_seven_as_free(input_data):
            values = input_data.split()
            age = int(values[0])
            if age <= 7:
                return "Проход разрешён\n"
            if values[1] == "да":
                return "Проход разрешён\n"
            if values[1] == "нет":
                return "Для прохода нужен билет\n"
            return "Ошибка: неверный ответ\n"

        self.assert_not_max(2441, treats_seven_as_free)

    def test_axis_sign_mutant_is_rejected(self):
        def handles_only_one_sign_per_axis(input_data):
            x, y = map(int, input_data.split())
            if x == 0 and y == 0:
                category = "начало координат"
            elif y == 0:
                category = "ось X" if x > 0 else "третья четверть"
            elif x == 0:
                category = "ось Y" if y < 0 else "первая четверть"
            elif x > 0 and y > 0:
                category = "первая четверть"
            elif x < 0 < y:
                category = "вторая четверть"
            elif x < 0 and y < 0:
                category = "третья четверть"
            else:
                category = "четвёртая четверть"
            return category + "\n"

        self.assert_not_max(2442, handles_only_one_sign_per_axis)

    def test_coordinate_negation_is_rejected(self):
        spec = TASK_SPECS[2442]
        reference = runner_for(spec)

        def negating_runner(input_data):
            answer = reference(input_data).strip()
            return "Точка не находится: " + answer + "\n"

        self.assert_not_max(2442, negating_runner)

    def test_single_midnight_subtraction_mutant_is_rejected(self):
        def subtracts_one_day(input_data):
            hours, minutes, duration = map(int, input_data.split())
            total = hours * 60 + minutes + duration
            if total >= 24 * 60:
                total -= 24 * 60
            return "{:02d}:{:02d}\n".format(total // 60, total % 60)

        self.assert_not_max(2444, subtracts_one_day)

    def test_punctuation_palindrome_mutant_is_rejected(self):
        def forgets_dot_and_question_mark(input_data):
            text = input_data.rstrip("\n").casefold()
            for symbol in " ,!-":
                text = text.replace(symbol, "")
            answer = (
                "Это палиндром"
                if text == text[::-1]
                else "Это не палиндром"
            )
            return answer + "\n"

        self.assert_not_max(2446, forgets_dot_and_question_mark)

        def forgets_comma_and_exclamation(input_data):
            text = input_data.rstrip("\n").casefold()
            for symbol in " .?-":
                text = text.replace(symbol, "")
            answer = (
                "Это палиндром"
                if text == text[::-1]
                else "Это не палиндром"
            )
            return answer + "\n"

        self.assert_not_max(2446, forgets_comma_and_exclamation)

    def test_middle_series_mutant_is_rejected(self):
        def checks_only_edges(input_data):
            text = input_data.strip()
            prefix = 1
            while prefix < len(text) and text[prefix] == text[0]:
                prefix += 1
            suffix = 1
            while suffix < len(text) and text[-suffix - 1] == text[-1]:
                suffix += 1
            return "{}\n".format(max(prefix, suffix))

        self.assert_not_max(2447, checks_only_edges)

        def normalizes_the_input(input_data):
            text = input_data.strip().casefold()
            longest = current = 1
            for index in range(1, len(text)):
                if text[index] == text[index - 1]:
                    current += 1
                    longest = max(longest, current)
                else:
                    current = 1
            return "{}\n".format(longest)

        self.assert_not_max(2447, normalizes_the_input)

    def test_multi_digit_compression_mutant_is_rejected(self):
        def splits_long_runs(input_data):
            text = input_data.strip()
            chunks = []
            run_start = 0
            for index in range(1, len(text) + 1):
                if index < len(text) and text[index] == text[run_start]:
                    continue
                count = index - run_start
                if count > 9:
                    chunks.extend((text[run_start] + "9", text[run_start] + str(count - 9)))
                else:
                    chunks.append(text[run_start] + str(count))
                run_start = index
            return "".join(chunks) + "\n"

        self.assert_not_max(2449, splits_long_runs)

        def normalizes_the_input(input_data):
            text = input_data.strip().casefold()
            chunks = []
            start = 0
            for index in range(1, len(text) + 1):
                if index < len(text) and text[index] == text[start]:
                    continue
                chunks.append(text[start] + str(index - start))
                start = index
            return "".join(chunks) + "\n"

        self.assert_not_max(2449, normalizes_the_input)

    def test_password_accepts_zero_and_punctuation(self):
        spec = TASK_SPECS[2448]
        cases = {case.input_data: case for case in spec.cases}

        def rejects_valid_characters(input_data):
            password = input_data.rstrip("\n")
            if "0" in password or "!" in password:
                return "Пароль не подходит:\n- слишком простой\n"
            return "\n".join(cases[input_data].expected[0]) + "\n"

        self.assert_not_max(2448, rejects_valid_characters)

    def test_flexible_semantic_formats_are_accepted(self):
        coordinate_answers = {
            "0\n0\n": "в начале координат",
            "5\n0\n": "на оси X",
            "0\n-3\n": "на оси Y",
            "3\n2\n": "в первой четверти",
            "-3\n5\n": "во второй четверти",
            "-1\n-1\n": "в третьей четверти",
            "4\n-2\n": "в четвертой четверти",
            "-5\n0\n": "на оси X",
            "0\n3\n": "на оси Y",
        }
        points, _ = perform_task(
            2442,
            lambda data: coordinate_answers[data] + "\n",
        )
        self.assertEqual(points, TASK_SPECS[2442].max_points)

        clock_answers = {
            "23\n50\n25\n": "00:15",
            "10\n0\n90\n": "11:30",
            "12\n40\n20\n": "13:00",
            "0\n0\n1440\n": "00:00",
            "9\n5\n0\n": "09:05",
            "23\n59\n1\n": "00:00",
            "10\n15\n3000\n": "12:15",
        }
        points, _ = perform_task(2444, lambda data: clock_answers[data] + "\n")
        self.assertEqual(points, TASK_SPECS[2444].max_points)

        def integer_only_series(input_data):
            text = input_data.rstrip("\n")
            longest = current = 1
            for index in range(1, len(text)):
                if text[index] == text[index - 1]:
                    current += 1
                    longest = max(longest, current)
                else:
                    current = 1
            return str(longest) + "\n"

        points, _ = perform_task(2447, integer_only_series)
        self.assertEqual(points, TASK_SPECS[2447].max_points)

        negative_length = runner_with_override(
            TASK_SPECS[2447],
            "4",
            "-3\n",
        )
        self.assert_not_max(2447, negative_length)

    def test_caesar_accepts_either_complete_language_family(self):
        english = "abcdefghijklmnopqrstuvwxyz"
        russian = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"

        def english_only(input_data):
            text, shift = input_data.rstrip("\n").rsplit("\n", 1)
            return shift_text(text, int(shift), english) + "\n"

        def russian_only(input_data):
            text, shift = input_data.rstrip("\n").rsplit("\n", 1)
            return shift_text(text, int(shift), russian) + "\n"

        for runner in (english_only, russian_only):
            with self.subTest(runner=runner.__name__):
                points, _ = perform_task(2450, runner)
                self.assertEqual(points, TASK_SPECS[2450].max_points)

    def test_whitespace_sensitive_answers_are_not_collapsed(self):
        caesar_spec = TASK_SPECS[2450]
        caesar_reference = runner_for(caesar_spec)
        caesar_cases = {
            case.input_data: case.key for case in caesar_spec.cases
        }

        def doubles_spaces_in_both_alphabets(input_data):
            output = caesar_reference(input_data)
            if caesar_cases[input_data] in {"1", "4"}:
                return output.replace(" ", "  ")
            return output

        self.assert_not_max(2450, doubles_spaces_in_both_alphabets)

        compression = runner_with_override(
            TASK_SPECS[2449],
            "8",
            "a1  2\n",
        )
        self.assert_not_max(2449, compression)

    def test_caesar_cannot_mix_criteria_from_different_families(self):
        spec = TASK_SPECS[2450]
        reference = runner_for(spec)
        accepted_keys = {"1", "3", "5", "6", "7"}
        cases = {case.input_data: case for case in spec.cases}

        def mixed_runner(input_data):
            if cases[input_data].key in accepted_keys:
                return reference(input_data)
            return "неверный результат\n"

        self.assert_not_max(2450, mixed_runner)

    def test_caesar_requires_modulo_for_very_large_shifts(self):
        english = "abcdefghijklmnopqrstuvwxyz"
        russian = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"

        def subtracts_alphabet_length_once(input_data):
            text, raw_shift = input_data.rstrip("\n").rsplit("\n", 1)
            shift = int(raw_shift)
            alphabet = (
                russian
                if any(character.casefold() in russian for character in text)
                else english
            )
            if shift >= len(alphabet):
                shift -= len(alphabet)
            result = []
            for character in text:
                lower = character.casefold()
                if lower not in alphabet:
                    result.append(character)
                    continue
                index = alphabet.index(lower) + shift
                if index >= len(alphabet):
                    index -= len(alphabet)
                if index >= len(alphabet):
                    result.append("?")
                    continue
                replacement = alphabet[index]
                result.append(
                    replacement.upper() if character.isupper() else replacement
                )
            return "".join(result) + "\n"

        self.assert_not_max(2450, subtracts_alphabet_length_once)

    def test_case_exception_is_reported_and_remaining_cases_run(self):
        spec = TASK_SPECS[2440]
        reference = runner_for(spec)
        calls = []

        def crashing_runner(input_data):
            calls.append(input_data)
            if input_data == "135\n":
                raise RuntimeError("авария в решении")
            return reference(input_data)

        feedback = self.assert_not_max(2440, crashing_runner)
        self.assertEqual(len(calls), len(spec.cases))
        self.assertIn("RuntimeError", feedback)
        self.assertIn("авария в решении", feedback)

    def test_infrastructure_exception_is_not_graded_as_a_student_failure(self):
        def unavailable_runner(input_data):
            del input_data
            raise ExecutionException("Docker unavailable")

        with self.assertRaisesRegex(ExecutionException, "Docker unavailable"):
            perform_task(2440, unavailable_runner)

    def test_oversized_stdout_is_rejected_without_echoing_payload(self):
        spec = TASK_SPECS[2440]
        payload = "СЕКРЕТ" * (MAX_STDOUT_BYTES // 2)
        runner = runner_with_override(spec, "1", payload)
        feedback = self.assert_not_max(2440, runner)
        self.assertIn("Вывод отклонён", feedback)
        self.assertNotIn("СЕКРЕТ", feedback)

    def test_each_tiny_wrapper_uses_standard_api(self):
        for task_id, (max_points, _) in EXPECTED_TASKS.items():
            with self.subTest(task_id=task_id):
                module = importlib.import_module(
                    "environments.task_{}.tester".format(task_id)
                )
                source_code = (
                    "text = input()\n"
                    "for symbol in text:\n"
                    "    print(symbol)\n"
                    if task_id == 2445
                    else "print('student code')"
                )
                points, _ = module.perform_tests(
                    runner_for(TASK_SPECS[task_id]),
                    source_code=source_code,
                )
                self.assertEqual(points, max_points)


if __name__ == "__main__":
    unittest.main()
