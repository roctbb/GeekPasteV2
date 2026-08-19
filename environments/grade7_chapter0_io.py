"""Shared input/output tests for the first two lessons of grade 7.

Students may choose their own ``input`` prompts, so most checks compare the
meaningful end of stdout instead of the whole stream.  The exceptional
matchers below encode formats that the published tasks intentionally leave
flexible.
"""

from dataclasses import dataclass
import ast
import re
from typing import Callable, Dict, Tuple
import unicodedata

from runner import ExecutionException


ExpectedLines = Tuple[str, ...]
ExpectedVariants = Tuple[ExpectedLines, ...]
CaseGroups = Tuple[Tuple[str, ...], ...]

MAX_STDOUT_BYTES = 100_000
FEEDBACK_PREVIEW_CHARS = 320


@dataclass(frozen=True)
class OutputCase:
    key: str
    label: str
    input_data: str
    expected: ExpectedVariants
    matcher: str = "suffix"


@dataclass(frozen=True)
class Criterion:
    description: str
    case_groups: CaseGroups


@dataclass(frozen=True)
class TaskSpec:
    task_id: int
    title: str
    max_points: int
    cases: Tuple[OutputCase, ...]
    criteria: Tuple[Criterion, ...]
    coherent_families: Tuple[str, ...] = ()


def _as_lines(value):
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _case(key, label, input_data, expected, *alternatives, matcher="suffix"):
    variants = (_as_lines(expected),) + tuple(
        _as_lines(item) for item in alternatives
    )
    return OutputCase(key, label, input_data, variants, matcher)


def _criterion(description, *case_keys):
    return Criterion(description, (tuple(case_keys),))


def _family_criterion(description, english, russian):
    return Criterion(description, (tuple(english), tuple(russian)))


TASK_SPECS: Dict[int, TaskSpec] = {
    2440: TaskSpec(
        2440,
        "Остаток времени",
        5,
        (
            _case("1", "135 минут", "135\n", "2 ч. 15 мин."),
            _case("2", "меньше часа", "45\n", "0 ч. 45 мин."),
            _case("3", "ровно час", "60\n", "1 ч. 0 мин."),
            _case("4", "полные сутки", "1440\n", "24 ч. 0 мин."),
            _case("5", "ноль минут", "0\n", "0 ч. 0 мин."),
        ),
        (
            _criterion(
                "минуты правильно переведены в часы и минуты на всех проверках",
                "1",
                "2",
                "3",
                "4",
                "5",
            ),
        ),
    ),
    2441: TaskSpec(
        2441,
        "Электронный турникет",
        10,
        (
            _case(
                "1",
                "ребёнок младше 7 лет",
                "6\n",
                "Проход разрешён",
                matcher="turnstile",
            ),
            _case(
                "2",
                "посетитель с билетом",
                "7\nда\n",
                "Проход разрешён",
                matcher="turnstile",
            ),
            _case(
                "3",
                "посетитель без билета",
                "14\nнет\n",
                "Для прохода нужен билет",
                matcher="turnstile",
            ),
            _case(
                "4",
                "непонятный ответ",
                "30\nага\n",
                "Непонятный ответ",
                matcher="turnstile",
            ),
            _case(
                "5",
                "нулевой возраст",
                "0\n",
                "Проход разрешён",
                matcher="turnstile",
            ),
            _case(
                "6",
                "семилетний посетитель без билета",
                "7\nнет\n",
                "Для прохода нужен билет",
                matcher="turnstile",
            ),
        ),
        (
            _criterion("правильно обработан возраст посетителя", "1", "5"),
            _criterion(
                "учитывается билет и обрабатывается неправильный ответ",
                "2",
                "3",
                "4",
                "6",
            ),
        ),
    ),
    2442: TaskSpec(
        2442,
        "Координатный детектив",
        10,
        (
            _case(
                "1",
                "начало координат",
                "0\n0\n",
                "Точка находится в начале координат",
                "Начало координат",
                matcher="coordinate",
            ),
            _case(
                "2",
                "положительная полуось X",
                "5\n0\n",
                "Точка находится на оси X",
                "Ось X",
                matcher="coordinate",
            ),
            _case(
                "3",
                "отрицательная полуось Y",
                "0\n-3\n",
                "Точка находится на оси Y",
                "Ось Y",
                matcher="coordinate",
            ),
            _case(
                "4",
                "первая четверть",
                "3\n2\n",
                "Точка находится в первой четверти",
                "Первая четверть",
                matcher="coordinate",
            ),
            _case(
                "5",
                "вторая четверть",
                "-3\n5\n",
                "Точка находится во второй четверти",
                "Вторая четверть",
                matcher="coordinate",
            ),
            _case(
                "6",
                "третья четверть",
                "-1\n-1\n",
                "Точка находится в третьей четверти",
                "Третья четверть",
                matcher="coordinate",
            ),
            _case(
                "7",
                "четвёртая четверть",
                "4\n-2\n",
                "Точка находится в четвёртой четверти",
                "Четвёртая четверть",
                matcher="coordinate",
            ),
            _case(
                "8",
                "отрицательная полуось X",
                "-5\n0\n",
                "Точка находится на оси X",
                "Ось X",
                matcher="coordinate",
            ),
            _case(
                "9",
                "положительная полуось Y",
                "0\n3\n",
                "Точка находится на оси Y",
                "Ось Y",
                matcher="coordinate",
            ),
        ),
        (
            _criterion(
                "различаются начало координат, обе оси и первая четверть",
                "1",
                "2",
                "3",
                "4",
                "8",
                "9",
            ),
            _criterion(
                "решение проходит проверки для остальных координатных четвертей",
                "5",
                "6",
                "7",
            ),
        ),
    ),
    2443: TaskSpec(
        2443,
        "Треугольник",
        15,
        (
            _case(
                "1",
                "равнобедренный треугольник",
                "5\n5\n8\n",
                "Равнобедренный треугольник",
            ),
            _case(
                "2",
                "разносторонний треугольник",
                "3\n4\n5\n",
                "Разносторонний треугольник",
            ),
            _case(
                "3",
                "равносторонний треугольник",
                "5\n5\n5\n",
                "Равносторонний треугольник",
            ),
            _case(
                "4",
                "явно невозможный треугольник",
                "1\n2\n10\n",
                "Треугольник не существует",
            ),
            _case(
                "5",
                "вырожденный треугольник",
                "1\n2\n3\n",
                "Треугольник не существует",
            ),
            _case(
                "6",
                "равные вторая и третья стороны",
                "8\n5\n5\n",
                "Равнобедренный треугольник",
            ),
            _case(
                "7",
                "равные первая и третья стороны",
                "5\n8\n5\n",
                "Равнобедренный треугольник",
            ),
            _case(
                "8",
                "наибольшая сторона введена первой",
                "10\n1\n2\n",
                "Треугольник не существует",
            ),
            _case(
                "9",
                "наибольшая сторона введена второй",
                "1\n10\n2\n",
                "Треугольник не существует",
            ),
        ),
        (
            _criterion(
                "правильно проверяется существование треугольника",
                "4",
                "5",
                "8",
                "9",
            ),
            _criterion(
                "правильно определяются все три вида треугольника",
                "1",
                "2",
                "3",
            ),
            _criterion(
                "вид не зависит от порядка введённых сторон",
                "6",
                "7",
            ),
        ),
    ),
    2444: TaskSpec(
        2444,
        "Электронные часы",
        15,
        (
            _case(
                "1",
                "переход через полночь",
                "23\n50\n25\n",
                "Событие закончится в 00:15",
                matcher="clock",
            ),
            _case(
                "2",
                "продолжительность больше часа",
                "10\n0\n90\n",
                "Событие закончится в 11:30",
                matcher="clock",
            ),
            _case(
                "3",
                "переход к следующему часу",
                "12\n40\n20\n",
                "Событие закончится в 13:00",
                matcher="clock",
            ),
            _case(
                "4",
                "полные сутки",
                "0\n0\n1440\n",
                "Событие закончится в 00:00",
                matcher="clock",
            ),
            _case(
                "5",
                "ведущие нули",
                "9\n5\n0\n",
                "Событие закончится в 09:05",
                matcher="clock",
            ),
            _case(
                "6",
                "последняя минута суток",
                "23\n59\n1\n",
                "Событие закончится в 00:00",
                matcher="clock",
            ),
            _case(
                "7",
                "продолжительность больше двух суток",
                "10\n15\n3000\n",
                "Событие закончится в 12:15",
                matcher="clock",
            ),
        ),
        (
            _criterion("время правильно вычисляется в пределах суток", "2", "3"),
            _criterion(
                "корректно обработан переход через полночь",
                "1",
                "4",
                "7",
            ),
            _criterion(
                "результат имеет формат ЧЧ:ММ с ведущими нулями",
                "5",
                "6",
            ),
        ),
    ),
    2445: TaskSpec(
        2445,
        "Статистика сообщения",
        10,
        (
            _case(
                "1",
                "смешанная строка",
                "Кот №7 спит!\n",
                ("Букв: 7", "Цифр: 1", "Пробелов: 2", "Других символов: 2"),
            ),
            _case(
                "2",
                "только цифры",
                "12345\n",
                ("Букв: 0", "Цифр: 5", "Пробелов: 0", "Других символов: 0"),
            ),
            _case(
                "3",
                "только пробелы",
                "   \n",
                ("Букв: 0", "Цифр: 0", "Пробелов: 3", "Других символов: 0"),
            ),
            _case(
                "4",
                "буквы и пробел",
                "абв где\n",
                ("Букв: 6", "Цифр: 0", "Пробелов: 1", "Других символов: 0"),
            ),
            _case(
                "5",
                "табуляция как пробельный символ",
                "\t\t\n",
                ("Букв: 0", "Цифр: 0", "Пробелов: 2", "Других символов: 0"),
            ),
            _case(
                "6",
                "цифра ноль",
                "0\n",
                ("Букв: 0", "Цифр: 1", "Пробелов: 0", "Других символов: 0"),
            ),
            _case(
                "7",
                "Unicode-пробелы",
                "\u00a0\u2003\n",
                ("Букв: 0", "Цифр: 0", "Пробелов: 2", "Других символов: 0"),
            ),
        ),
        (
            _criterion(
                (
                    "за один проход правильно различаются буквы, цифры, "
                    "пробелы и остальные символы"
                ),
                "1",
            ),
            _criterion(
                "все четыре счётчика верны на однородных строках",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
            ),
        ),
    ),
    2446: TaskSpec(
        2446,
        "Палиндром",
        10,
        (
            _case(
                "1",
                "фраза с пробелами и разным регистром",
                "А роза упала на лапу Азора\n",
                "Это палиндром",
            ),
            _case("2", "не палиндром", "Привет, мир!\n", "Это не палиндром"),
            _case("3", "слово с разным регистром", "Шалаш\n", "Это палиндром"),
            _case("4", "дефис не влияет", "До-вод\n", "Это палиндром"),
            _case("5", "цифровой палиндром", "12321\n", "Это палиндром"),
            _case(
                "6",
                "длинная фраза с пробелами",
                "Кит на море романтик\n",
                "Это палиндром",
            ),
            _case(
                "7",
                "точка и вопросительный знак не влияют",
                "А? роза упала. на лапу Азора\n",
                "Это палиндром",
            ),
            _case(
                "8",
                "запятая и восклицательный знак не влияют",
                "А, роза упала на лапу Азора!\n",
                "Это палиндром",
            ),
        ),
        (
            _criterion(
                "палиндром правильно проверяется без учёта пробелов",
                "1",
                "3",
                "5",
            ),
            _criterion(
                "регистр и указанные знаки препинания не влияют на результат",
                "2",
                "4",
                "6",
                "7",
                "8",
            ),
        ),
    ),
    2447: TaskSpec(
        2447,
        "Самая длинная серия",
        15,
        (
            _case(
                "1",
                "несколько серий",
                "aaabbccccdaaaaa\n",
                "Самая длинная серия: 5",
                matcher="final_integer",
            ),
            _case(
                "2",
                "один символ",
                "a\n",
                "Самая длинная серия: 1",
                matcher="final_integer",
            ),
            _case(
                "3",
                "все символы различны",
                "abcde\n",
                "Самая длинная серия: 1",
                matcher="final_integer",
            ),
            _case(
                "4",
                "серия в начале",
                "aaab\n",
                "Самая длинная серия: 3",
                matcher="final_integer",
            ),
            _case(
                "5",
                "серия в конце",
                "abbb\n",
                "Самая длинная серия: 3",
                matcher="final_integer",
            ),
            _case(
                "6",
                "чередование символов",
                "ababab\n",
                "Самая длинная серия: 1",
                matcher="final_integer",
            ),
            _case(
                "7",
                "самая длинная серия в середине",
                "abbba\n",
                "Самая длинная серия: 3",
                matcher="final_integer",
            ),
            _case(
                "8",
                "регистр символов сохраняется",
                "aAAa\n",
                "Самая длинная серия: 2",
                matcher="final_integer",
            ),
            _case(
                "9",
                "пробелы по краям являются символами",
                "  a \n",
                "Самая длинная серия: 2",
                matcher="final_integer",
            ),
        ),
        (
            _criterion("находится самая длинная серия в обычной строке", "1"),
            _criterion(
                "обработаны один символ и строки без одинаковых соседей",
                "2",
                "3",
                "6",
            ),
            _criterion(
                "обработаны серии в начале, середине и конце строки",
                "4",
                "5",
                "7",
                "8",
                "9",
            ),
        ),
    ),
    2448: TaskSpec(
        2448,
        "Проверка пароля",
        15,
        (
            _case(
                "1",
                "надёжный пароль",
                "Python12\n",
                "Пароль подходит",
                matcher="password",
            ),
            _case(
                "2",
                "нет заглавной буквы",
                "python12\n",
                ("Пароль не подходит:", "- нет заглавной буквы"),
                matcher="password",
            ),
            _case(
                "3",
                "нет цифры",
                "Password\n",
                ("Пароль не подходит:", "- нет цифры"),
                matcher="password",
            ),
            _case(
                "4",
                "нет строчной буквы",
                "PASSWORD1\n",
                ("Пароль не подходит:", "- нет строчной буквы"),
                matcher="password",
            ),
            _case(
                "5",
                "есть пробел",
                "Pyth on12\n",
                ("Пароль не подходит:", "- есть пробел"),
                matcher="password",
            ),
            _case(
                "6",
                "короткий пароль",
                "Pw1\n",
                ("Пароль не подходит:", "- короче 8 символов"),
                matcher="password",
            ),
            _case(
                "7",
                "несколько нарушений",
                "pw 1\n",
                (
                    "Пароль не подходит:",
                    "- короче 8 символов",
                    "- нет заглавной буквы",
                    "- есть пробел",
                ),
                matcher="password",
            ),
            _case(
                "8",
                "цифра ноль учитывается",
                "Python00\n",
                "Пароль подходит",
                matcher="password",
            ),
            _case(
                "9",
                "разрешён знак пунктуации",
                "Py!thon1\n",
                "Пароль подходит",
                matcher="password",
            ),
        ),
        (
            _criterion("проверяются длина и отсутствие пробелов", "5", "6"),
            _criterion(
                "проверяется наличие цифр, строчных и заглавных букв",
                "2",
                "3",
                "4",
            ),
            _criterion(
                "выводится полный список невыполненных требований",
                "1",
                "7",
                "8",
                "9",
            ),
        ),
    ),
    2449: TaskSpec(
        2449,
        "Сжатие строки",
        15,
        (
            _case(
                "1",
                "несколько серий",
                "aaabbccccd\n",
                "a3b2c4d1",
                matcher="exact_suffix",
            ),
            _case(
                "2",
                "серии длины один",
                "abc\n",
                "a1b1c1",
                matcher="exact_suffix",
            ),
            _case("3", "один символ", "a\n", "a1", matcher="exact_suffix"),
            _case(
                "4",
                "повторная несмежная серия",
                "aabbaa\n",
                "a2b2a2",
                matcher="exact_suffix",
            ),
            _case(
                "5",
                "одна длинная серия",
                "zzzzz\n",
                "z5",
                matcher="exact_suffix",
            ),
            _case(
                "6",
                "серия длины больше девяти",
                "aaaaaaaaaaaa\n",
                "a12",
                matcher="exact_suffix",
            ),
            _case(
                "7",
                "регистр символов сохраняется",
                "aAAa\n",
                "a1A2a1",
                matcher="exact_suffix",
            ),
            _case(
                "8",
                "пробелы в конце являются символами",
                "a  \n",
                "a1 2",
                matcher="exact_suffix",
            ),
            _case(
                "9",
                "пробелы в начале являются символами",
                "  a\n",
                " 2a1",
                matcher="exact_suffix",
            ),
        ),
        (
            _criterion("каждая серия заменяется символом и её длиной", "1"),
            _criterion(
                "обрабатываются серии длины один и конец строки",
                "2",
                "3",
            ),
            _criterion(
                "обрабатываются одна, несколько и длинная серии",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
            ),
        ),
    ),
    2450: TaskSpec(
        2450,
        "Шифр Цезаря",
        20,
        (
            _case(
                "1",
                "английский текст",
                "Hello, World!\n3\n",
                "Khoor, Zruog!",
                matcher="exact_suffix",
            ),
            _case(
                "2",
                "сдвиг больше английского алфавита",
                "abc\n30\n",
                "efg",
                matcher="exact_suffix",
            ),
            _case(
                "3",
                "переход через конец английского алфавита",
                "XYZ\n3\n",
                "ABC",
                matcher="exact_suffix",
            ),
            _case(
                "4",
                "русский текст",
                "Привет, мир!\n5\n",
                "Фхнзкч, снх!",
                "Фхнжйч, снх!",
                matcher="exact_suffix",
            ),
            _case(
                "5",
                "регистр и переход я → а",
                "яЯ\n1\n",
                "аА",
                matcher="exact_suffix",
            ),
            _case(
                "6",
                "большой русский сдвиг и неизменяемые цифры",
                "Тест 123\n33\n",
                "Ужту 123",
                "Тест 123",
                matcher="exact_suffix",
            ),
            _case(
                "7",
                "английский большой сдвиг и неизменяемые символы",
                "Az-9!\n27\n",
                "Ba-9!",
                matcher="exact_suffix",
            ),
            _case(
                "8",
                "очень большой английский сдвиг",
                "z\n55\n",
                "c",
                matcher="exact_suffix",
            ),
            _case(
                "9",
                "очень большой русский сдвиг",
                "яЯ\n67\n",
                "вВ",
                "аА",
                matcher="exact_suffix",
            ),
        ),
        (
            _family_criterion(
                "буквы сдвигаются на указанное число позиций",
                english=("1",),
                russian=("4",),
            ),
            _family_criterion(
                "работают переход через конец и большой сдвиг",
                english=("2", "3", "7", "8"),
                russian=("5", "6", "9"),
            ),
            _family_criterion(
                "сохраняется регистр букв",
                english=("1", "3", "7"),
                russian=("4", "5"),
            ),
            _family_criterion(
                "пробелы, цифры и знаки препинания не изменяются",
                english=("1", "7"),
                russian=("4", "6"),
            ),
        ),
        coherent_families=("английский алфавит", "русский алфавит"),
    ),
}


_TIME_AT_END = re.compile(r"(?<!\d)((?:[01]\d|2[0-3]):[0-5]\d)\s*$")
_INTEGER_AT_END = re.compile(r"(?<![+\-\d])([+-]?\d+)\s*$")
_LITERAL_PROMPT_TASK_IDS = frozenset({2441, 2442, 2448})


def _literal_input_prompts(source_code):
    """Return non-empty string literals passed directly to built-in input()."""
    if not source_code:
        return ()
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, TypeError, ValueError):
        return ()

    prompts = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "input"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value
        ):
            continue
        prompts.append(node.args[0].value)
    return tuple(dict.fromkeys(prompts))


def _without_leading_input_prompt_candidates(actual, prompts):
    """Yield stdout suffixes reachable by removing only declared prompts."""
    actual = str(actual)
    positions = {0}
    pending = [0]
    while pending:
        position = pending.pop()
        for prompt in prompts:
            if not actual.startswith(prompt, position):
                continue
            next_position = position + len(prompt)
            if next_position not in positions:
                positions.add(next_position)
                pending.append(next_position)
    return tuple(actual[position:] for position in sorted(positions))


def _normalise(text):
    text = unicodedata.normalize("NFKC", str(text)).replace("\u00a0", " ")
    return " ".join(text.split())


def _normalise_casefold(text):
    return _normalise(text).casefold().replace("ё", "е")


def _matches_suffix(actual, variants):
    normalised_actual = _normalise(actual)
    return any(
        normalised_actual.endswith(_normalise("\n".join(expected)))
        for expected in variants
    )


def _matches_exact_suffix(actual, variants):
    actual_text = str(actual).replace("\r\n", "\n").replace("\r", "\n")
    actual_text = actual_text.rstrip("\n")
    return any(
        actual_text.endswith("\n".join(expected))
        for expected in variants
    )


def _matches_coordinate(actual, variants):
    actual_text = _normalise_casefold(actual)
    expected_text = _normalise_casefold("\n".join(variants[0]))

    def categories(text):
        found = set()
        if "начал" in text and "координат" in text:
            found.add("origin")
        if re.search(r"\bос(?:ь|и)\s*x\b", text):
            found.add("axis_x")
        if re.search(r"\bос(?:ь|и)\s*y\b", text):
            found.add("axis_y")
        for key, root in (
            ("first", "перв"),
            ("second", "втор"),
            ("third", "трет"),
            ("fourth", "четв"),
        ):
            if re.search(r"\b{}\w*\s+четверт".format(root), text):
                found.add(key)
        return found

    expected_categories = categories(expected_text)
    if len(expected_categories) != 1:
        return False

    patterns = {
        "origin": (
            r"(?:(?:точка(?:\s+находится)?\s+)?в\s+начале\s+координат|"
            r"начало\s+координат)[.!]?"
        ),
        "axis_x": (
            r"(?:(?:точка(?:\s+находится)?\s+)?на\s+оси\s+x|ось\s+x)[.!]?"
        ),
        "axis_y": (
            r"(?:(?:точка(?:\s+находится)?\s+)?на\s+оси\s+y|ось\s+y)[.!]?"
        ),
        "first": (
            r"(?:(?:точка(?:\s+находится)?\s+)?в\s+первой\s+четверти|"
            r"первая\s+четверть)[.!]?"
        ),
        "second": (
            r"(?:(?:точка(?:\s+находится)?\s+)?во?\s+второй\s+четверти|"
            r"вторая\s+четверть)[.!]?"
        ),
        "third": (
            r"(?:(?:точка(?:\s+находится)?\s+)?в\s+третьей\s+четверти|"
            r"третья\s+четверть)[.!]?"
        ),
        "fourth": (
            r"(?:(?:точка(?:\s+находится)?\s+)?в\s+четвертой\s+четверти|"
            r"четвертая\s+четверть)[.!]?"
        ),
    }
    expected_category = next(iter(expected_categories))
    return re.fullmatch(patterns[expected_category], actual_text) is not None


def _matches_clock(actual, variants):
    expected_match = _TIME_AT_END.search(_normalise("\n".join(variants[0])))
    actual_match = _TIME_AT_END.search(str(actual))
    return bool(
        expected_match
        and actual_match
        and actual_match.group(1) == expected_match.group(1)
    )


def _matches_final_integer(actual, variants):
    expected_match = _INTEGER_AT_END.search(_normalise("\n".join(variants[0])))
    actual_match = _INTEGER_AT_END.search(str(actual))
    return bool(
        expected_match
        and actual_match
        and int(actual_match.group(1)) == int(expected_match.group(1))
    )


def _matches_turnstile(actual, variants):
    actual_text = str(actual).replace("\r\n", "\n").replace("\r", "\n")
    if actual_text.endswith("\n"):
        actual_text = actual_text[:-1]
    return any(
        actual_text == "\n".join(expected)
        for expected in variants
    )


def _matches_password(actual, variants):
    actual_text = str(actual).replace("\r\n", "\n").replace("\r", "\n")
    if actual_text.endswith("\n"):
        actual_text = actual_text[:-1]
    return any(
        actual_text == "\n".join(expected)
        for expected in variants
    )


_MATCHERS: Dict[str, Callable[[str, ExpectedVariants], bool]] = {
    "clock": _matches_clock,
    "coordinate": _matches_coordinate,
    "exact_suffix": _matches_exact_suffix,
    "final_integer": _matches_final_integer,
    "password": _matches_password,
    "suffix": _matches_suffix,
    "turnstile": _matches_turnstile,
}


def _preview(
    value,
    limit=FEEDBACK_PREVIEW_CHARS,
    empty_label="<пустой вывод>",
):
    value = str(value).replace("\r\n", "\n").replace("\r", "\n")
    # The final newline terminates console input/output and is not content.
    value = value.rstrip("\n")
    if not value:
        return empty_label

    visible_lines = []
    for line in value.split("\n"):
        line = line.replace("\t", r"\t")
        line = re.sub(r"^ +", lambda match: "␠" * len(match.group()), line)
        line = re.sub(r" +$", lambda match: "␠" * len(match.group()), line)
        visible_lines.append(line)
    visible = " ↵ ".join(visible_lines)
    if len(visible) <= limit:
        return visible
    return visible[:limit] + "…"


def _expected_preview(case):
    return " ИЛИ ".join(" / ".join(variant) for variant in case.expected)


def _validate_specs():
    for task_id, spec in TASK_SPECS.items():
        if task_id != spec.task_id:
            raise ValueError("Идентификатор спецификации задачи не совпадает с ключом.")
        if spec.max_points != len(spec.criteria) * 5:
            raise ValueError(
                "Максимальный балл задачи {} не соответствует критериям.".format(
                    task_id
                )
            )

        expected_group_count = len(spec.coherent_families) or 1
        for criterion in spec.criteria:
            if len(criterion.case_groups) != expected_group_count:
                raise ValueError(
                    "Критерии задачи {} имеют несовместимые семейства.".format(task_id)
                )

        case_keys = {case.key for case in spec.cases}
        referenced = {
            case_key
            for criterion in spec.criteria
            for group in criterion.case_groups
            for case_key in group
        }
        if len(case_keys) != len(spec.cases):
            raise ValueError("В задаче {} повторяются ключи тестов.".format(task_id))
        if referenced != case_keys:
            raise ValueError(
                "В задаче {} каждый тест должен входить хотя бы в один критерий.".format(
                    task_id
                )
            )


def _score_criteria(spec, results):
    group_count = len(spec.coherent_families) or 1
    candidates = []

    for group_index in range(group_count):
        passed = tuple(
            criterion
            for criterion in spec.criteria
            if all(
                results[case_key]
                for case_key in criterion.case_groups[group_index]
            )
        )
        relevant = {
            case_key
            for criterion in spec.criteria
            for case_key in criterion.case_groups[group_index]
        }
        candidates.append((len(passed), -group_index, passed, relevant, group_index))

    _, _, passed, relevant, group_index = max(candidates)
    family = (
        spec.coherent_families[group_index]
        if spec.coherent_families
        else None
    )
    return passed, relevant, family


def _assigned_names(node):
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return {
        target.id
        for target in targets
        if isinstance(target, ast.Name)
    }


def _uses_single_text_pass(source_code):
    if not source_code:
        return True

    try:
        tree = ast.parse(source_code)
    except (SyntaxError, TypeError, ValueError):
        return False

    text_names = set()

    def reads_text(node):
        return any(
            (
                isinstance(item, ast.Name)
                and item.id in text_names
            )
            or (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "input"
            )
            for item in ast.walk(node)
        )

    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and node.value is not None
    ]
    changed = True
    while changed:
        changed = False
        for node in assignments:
            names = _assigned_names(node)
            if names - text_names and reads_text(node.value):
                text_names.update(names)
                changed = True

    traversals = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)):
            traversals += int(reads_text(node.iter))
        elif isinstance(node, ast.While):
            traversals += int(reads_text(node.test))
        elif isinstance(node, ast.comprehension):
            traversals += int(reads_text(node.iter))
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "count"
                and reads_text(node.func.value)
            ):
                traversals += 1
            elif (
                isinstance(node.func, ast.Name)
                and node.func.id in {"Counter", "filter", "list", "map", "set", "sorted", "tuple"}
                and any(reads_text(argument) for argument in node.args)
            ):
                traversals += 1

    return traversals == 1


_validate_specs()


def perform_task(task_id, runner, source_code=None):
    """Run a task specification and return ``(points, Russian feedback)``."""

    try:
        spec = TASK_SPECS[task_id]
    except KeyError:
        raise ValueError("Неизвестная задача вводной главы: {}".format(task_id))

    results = {}
    output_previews = {}
    literal_input_prompts = (
        _literal_input_prompts(source_code)
        if task_id in _LITERAL_PROMPT_TASK_IDS
        else ()
    )

    for case in spec.cases:
        try:
            actual = runner(case.input_data)
        except ExecutionException:
            raise
        except Exception as error:  # A single crashing scenario must not hide the rest.
            results[case.key] = False
            output_previews[case.key] = "Ошибка выполнения {}: {}".format(
                type(error).__name__,
                _preview(error),
            )
            continue

        if isinstance(actual, bytes):
            actual = actual.decode("utf-8", errors="replace")
        elif not isinstance(actual, str):
            actual = str(actual)

        stdout_size = len(actual.encode("utf-8", errors="replace"))
        if stdout_size > MAX_STDOUT_BYTES:
            results[case.key] = False
            output_previews[case.key] = (
                "Вывод отклонён: {} байт, разрешено не более {}.".format(
                    stdout_size,
                    MAX_STDOUT_BYTES,
                )
            )
            continue

        output_previews[case.key] = _preview(actual)
        try:
            matcher = _MATCHERS[case.matcher]
            if task_id in _LITERAL_PROMPT_TASK_IDS:
                results[case.key] = any(
                    matcher(candidate, case.expected)
                    for candidate in _without_leading_input_prompt_candidates(
                        actual,
                        literal_input_prompts,
                    )
                )
            else:
                results[case.key] = matcher(actual, case.expected)
        except Exception as error:
            results[case.key] = False
            output_previews[case.key] = "Не удалось разобрать вывод: {}".format(
                _preview(error)
            )

    passed_criteria, relevant_case_keys, family = _score_criteria(spec, results)
    if task_id == 2445 and not _uses_single_text_pass(source_code):
        passed_criteria = tuple(
            criterion
            for criterion in passed_criteria
            if criterion is not spec.criteria[0]
        )
    points = len(passed_criteria) * 5

    if points == spec.max_points:
        if family:
            return points, (
                "Все критерии пройдены для семейства «{}». "
                "Начислено {} из {} баллов.".format(
                    family,
                    points,
                    spec.max_points,
                )
            )
        return points, (
            "Все {} проверок пройдены. Начислено {} из {} баллов.".format(
                len(spec.cases),
                points,
                spec.max_points,
            )
        )

    failed_cases = [
        case
        for case in spec.cases
        if case.key in relevant_case_keys and not results[case.key]
    ]
    failed_criteria = [
        criterion
        for criterion in spec.criteria
        if criterion not in passed_criteria
    ]
    passed_relevant_count = sum(
        results[case_key] for case_key in relevant_case_keys
    )
    lines = [
        "Пройдено {} из {} значимых проверок. Начислено {} из {} баллов.".format(
            passed_relevant_count,
            len(relevant_case_keys),
            points,
            spec.max_points,
        ),
        "Не выполнены критерии:",
    ]
    if family:
        lines.insert(1, "Проверено семейство: {}.".format(family))
    lines.extend("- " + criterion.description for criterion in failed_criteria)
    lines.append("Проблемные проверки:")

    has_invisible_input_markers = False
    for case in failed_cases:
        input_preview = _preview(case.input_data, empty_label="<пустой ввод>")
        has_invisible_input_markers = has_invisible_input_markers or (
            r"\t" in input_preview or "␠" in input_preview
        )
        lines.extend(
            (
                "- {}. Ввод: {}".format(
                    case.label,
                    input_preview,
                ),
                "  Ожидаемый содержательный ответ: {}".format(
                    _expected_preview(case)
                ),
                "  Полученный вывод: {}".format(output_previews[case.key]),
            )
        )

    if has_invisible_input_markers:
        lines.append(
            "Обозначения: \\t — табуляция; "
            "␠ — пробел на краю строки."
        )
    lines.append(
        "Тексты приглашений вводить данные не проверяются; сравнивается только ответ программы."
    )
    return points, "\n".join(lines)
