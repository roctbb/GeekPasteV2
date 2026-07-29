import ast
import base64
import copy
import json
import random
import re
import string

from runner import ExecutionException, SolutionException


TASK_MAX_POINTS = {
    2451: 10,
    2452: 10,
    2453: 15,
    2454: 15,
    2455: 10,
    2456: 10,
    2457: 15,
    2458: 15,
    2459: 10,
    2460: 10,
    2461: 15,
    2462: 20,
}


def perform_task(task_id, runner, source_code=None):
    handler = _TASK_HANDLERS.get(task_id)
    if handler is None:
        raise ExecutionException(
            f"Для задачи #{task_id} не найден проверяющий сценарий."
        )

    source_code = source_code or ""
    try:
        return handler(runner, source_code)
    except ExecutionException:
        raise
    except SolutionException:
        return 0, "Программа завершилась с ошибкой или превысила время выполнения."
    except SyntaxError as error:
        return 0, (
            "Программа не разбирается как Python-код: "
            f"строка {error.lineno or '?'}, {error.msg}."
        )
    except Exception as error:
        raise ExecutionException(
            "Внутренняя ошибка проверяющего сценария."
        ) from error


def _finish(task_id, criteria):
    maximum = TASK_MAX_POINTS[task_id]
    points = sum(5 for passed, _ in criteria if passed)

    lines = []
    for passed, message in criteria:
        lines.append(f"{'✓' if passed else '✗'} {message}")

    if points == maximum:
        heading = f"Все проверки пройдены. Баллы: {points}/{maximum}."
    else:
        heading = f"Проверки пройдены не полностью. Баллы: {points}/{maximum}."
    return points, "\n".join([heading, *lines])


def _parse_source(source_code):
    if not source_code.strip():
        raise SyntaxError("отправлен пустой файл")
    return ast.parse(source_code)


def _literal_node(value):
    if isinstance(value, dict):
        return ast.Dict(
            keys=[_literal_node(key) for key in value],
            values=[_literal_node(item) for item in value.values()],
        )
    if isinstance(value, list):
        return ast.List(elts=[_literal_node(item) for item in value], ctx=ast.Load())
    if isinstance(value, tuple):
        return ast.Tuple(elts=[_literal_node(item) for item in value], ctx=ast.Load())
    return ast.Constant(value=value)


def _replace_top_level_assignment(tree, name, value):
    replacement = _literal_node(value)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    node.value = copy.deepcopy(replacement)
                    ast.fix_missing_locations(tree)
                    return True
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            node.value = copy.deepcopy(replacement)
            ast.fix_missing_locations(tree)
            return True
    return False


def _definitions_source(tree):
    definitions = (
        ast.Import,
        ast.ImportFrom,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )

    unsafe_initializers = (
        ast.Await,
        ast.Call,
        ast.Lambda,
        ast.NamedExpr,
        ast.Yield,
        ast.YieldFrom,
    )

    def keep(node):
        if isinstance(node, definitions):
            return True
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            return False
        if node.value is None:
            return False
        return not any(
            isinstance(child, unsafe_initializers)
            for child in ast.walk(node.value)
        )

    module = ast.Module(
        body=[copy.deepcopy(node) for node in tree.body if keep(node)],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    return ast.unparse(module)


def _encoded_json(value):
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _run_probe(runner, source, probe_source, input_data="", time_limit=3):
    raw_result = runner.run_source(
        source,
        input_data,
        time_limit,
        probe_source=probe_source,
    )
    try:
        result = json.loads(raw_result)
    except json.JSONDecodeError:
        raise ExecutionException(
            "Изолированный проверочный процесс вернул повреждённый ответ."
        ) from None

    if not isinstance(result, dict):
        raise ExecutionException(
            "Изолированный проверочный процесс вернул ответ неверного типа."
        )
    if not result.get("ok"):
        return "", {"__error__": "решение не прошло изолированный запуск"}

    encoded_output = result.get("output_b64")
    payload = result.get("payload")
    if not isinstance(encoded_output, str) or not isinstance(payload, dict):
        raise ExecutionException(
            "Изолированный проверочный процесс нарушил схему ответа."
        )
    try:
        output = base64.b64decode(
            encoded_output,
            validate=True,
        ).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise ExecutionException(
            "Изолированный проверочный процесс повредил вывод программы."
        ) from None
    return output, payload


def _run_function_cases(runner, tree, function_name, cases):
    encoded_cases = _encoded_json(cases)
    probe = f"""
import base64 as __gc_base64
__gc_cases = __gc_json.loads(
    __gc_base64.b64decode({json.dumps(encoded_cases)}).decode("utf-8")
)
__gc_function = globals().get({json.dumps(function_name)})
__gc_results = []
if not callable(__gc_function):
    __gc_payload = {{"exists": False, "results": []}}
else:
    for __gc_case in __gc_cases:
        __gc_args = __gc_case["args"]
        try:
            __gc_value = __gc_function(*__gc_args)
            __gc_results.append({{
                "ok": True,
                "value": __gc_value,
                "args_after": __gc_args,
            }})
        except BaseException as __gc_case_error:
            __gc_results.append({{
                "ok": False,
                "error": type(__gc_case_error).__name__ + ": " + str(__gc_case_error),
                "args_after": __gc_args,
            }})
    __gc_payload = {{"exists": True, "results": __gc_results}}
"""
    return _run_probe(runner, _definitions_source(tree), probe)


def _safe_program_run(runner, input_data, time_limit=2):
    try:
        return True, runner(input_data, time_limit)
    except ExecutionException:
        raise
    except SolutionException:
        raise


def _safe_source_run(runner, source_code, input_data="", time_limit=2):
    try:
        return True, runner.run_source(source_code, input_data, time_limit)
    except ExecutionException:
        raise
    except SolutionException:
        raise


def _function_calls(tree, name, top_level_only=False):
    roots = tree.body
    count = 0
    for root in roots:
        if top_level_only and isinstance(
            root, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        for node in ast.walk(root):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            ):
                count += 1
    return count


def _function_definitions(tree, name=None):
    definitions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if name is not None:
        definitions = [node for node in definitions if node.name == name]
    return definitions


def _top_level_string_constants(tree):
    values = []
    for root in tree.body:
        if isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        values.extend(
            node.value
            for node in ast.walk(root)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    return values


def _nested_case_collection_size(tree):
    maximum = 0
    for root in tree.body:
        if isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for node in ast.walk(root):
            if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
                continue
            if all(isinstance(item, (ast.List, ast.Tuple)) for item in node.elts):
                maximum = max(maximum, len(node.elts))
    return maximum


def _contains_word_sequence(output, expected):
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+", output.lower())
    expected_words = [str(item).lower() for item in expected]
    if not expected_words:
        return "[]" in output or not output.strip()
    size = len(expected_words)
    return any(
        words[index:index + size] == expected_words
        for index in range(len(words) - size + 1)
    )


def _frequency_map(output):
    pairs = re.findall(
        r"[\"']?([A-Za-zА-Яа-яЁё]+)[\"']?\s*:\s*(-?\d+)",
        output.lower(),
    )
    return {word: int(count) for word, count in pairs}


def _parse_items(value):
    cleaned = re.sub(r"[\[\]{}()\"']", "", value.strip().lower())
    if not cleaned or cleaned in {"set", "none"}:
        return []
    return [
        item.strip()
        for item in cleaned.split(",")
        if item.strip()
    ]


def _interest_output(output):
    labels = ("Общие", "Все", "Только у Алисы", "Только у Бориса")
    result = {}
    for label in labels:
        matches = list(re.finditer(
            rf"{re.escape(label)}[ \t]*:[ \t]*([^\r\n]*)",
            output,
            flags=re.IGNORECASE,
        ))
        if not matches:
            result[label] = None
            continue
        result[label] = _parse_items(matches[-1].group(1))
    return result


def _rankings(output):
    found = re.findall(
        r"(?m)^\s*(?:(\d+)\s*[.)]\s*)?"
        r"([A-Za-zА-Яа-яЁё_-]+)\s*[—–-]\s*(-?\d+)\s*$",
        output,
    )
    return [
        (int(place) if place else None, name, int(points))
        for place, name, points in found
    ]


def _rare_items(output):
    text = output.replace("\r", "")
    prompt = re.search(
        r"(?:введите|ввод)[^:\n]*:\s*",
        text,
        flags=re.IGNORECASE,
    )
    if prompt:
        text = text[prompt.end():]
    lowered = text.lower().replace("ё", "е")
    if (
        re.search(r"\bнет\s+редк", lowered)
        or re.search(r"\bредк\w*\s+слов\w*\s+нет\b", lowered)
        or "редкие слова отсутствуют" in lowered
        or "редких слов не найдено" in lowered
    ):
        return []
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return _parse_items(text.splitlines()[-1] if text.splitlines() else text)


def _random_words(count):
    generator = random.SystemRandom()
    words = set()
    while len(words) < count:
        words.add(
            "".join(
                generator.choice(string.ascii_lowercase)
                for _ in range(12)
            )
        )
    return list(words)


def _direct_function_definitions(tree):
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _called_names(nodes):
    names = set()

    class CallVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            return None

        def visit_AsyncFunctionDef(self, node):
            return None

        def visit_ClassDef(self, node):
            return None

        def visit_If(self, node):
            if isinstance(node.test, ast.Constant):
                branch = node.body if node.test.value else node.orelse
                for child in branch:
                    self.visit(child)
                return None
            self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            self.generic_visit(node)

    visitor = CallVisitor()
    for node in nodes:
        visitor.visit(node)
    return names


def _reachable_execution_nodes(tree, excluded=()):
    definitions = _direct_function_definitions(tree)
    excluded = set(excluded)
    roots = [
        node
        for node in tree.body
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Import,
                ast.ImportFrom,
            ),
        )
    ]
    reachable = list(roots)
    pending = list(_called_names(roots))
    visited = set()

    while pending:
        name = pending.pop()
        if name in visited or name in excluded or name not in definitions:
            continue
        visited.add(name)
        body = definitions[name].body
        reachable.extend(body)
        pending.extend(_called_names(body))
    return reachable


def _literal_collection_sizes(tree):
    sizes = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                sizes[target.id] = len(value.elts)
    return sizes


def _iterable_size(node, collection_sizes):
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts)
    if isinstance(node, ast.Name):
        return collection_sizes.get(node.id, 1)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
    ):
        try:
            arguments = [ast.literal_eval(argument) for argument in node.args]
            return len(range(*arguments))
        except (TypeError, ValueError):
            return 1
    return 1


def _executed_call_count(tree, function_name):
    roots = _reachable_execution_nodes(tree, excluded={function_name})
    collection_sizes = _literal_collection_sizes(tree)
    total = 0

    def count(node, multiplier=1):
        nonlocal total
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Constant)
            and not node.test.value
        ):
            for child in node.orelse:
                count(child, multiplier)
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            iterations = _iterable_size(node.iter, collection_sizes)
            for child in node.body:
                count(child, multiplier * iterations)
            for child in node.orelse:
                count(child, multiplier)
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == function_name
        ):
            total += multiplier
        for child in ast.iter_child_nodes(node):
            count(child, multiplier)

    for root in roots:
        count(root)
    return total


def _reachable_calls(tree, function_name):
    calls = []

    class ReachableCallVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            return None

        def visit_AsyncFunctionDef(self, node):
            return None

        def visit_ClassDef(self, node):
            return None

        def visit_If(self, node):
            if isinstance(node.test, ast.Constant):
                branch = node.body if node.test.value else node.orelse
                for child in branch:
                    self.visit(child)
                return None
            self.generic_visit(node)

        def visit_Call(self, node):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == function_name
            ):
                calls.append(node)
            self.generic_visit(node)

    visitor = ReachableCallVisitor()
    for root in _reachable_execution_nodes(tree, excluded={function_name}):
        visitor.visit(root)
    return calls


def _uses_frequency_dictionary(tree):
    dictionary_names = set()
    counter_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = {
            target.id
            for target in targets
            if isinstance(target, ast.Name)
        }
        if isinstance(value, (ast.Dict, ast.DictComp)):
            dictionary_names.update(names)
        elif (
            isinstance(value, ast.Call)
            and (
                (
                    isinstance(value.func, ast.Name)
                    and value.func.id == "Counter"
                )
                or (
                    isinstance(value.func, ast.Attribute)
                    and value.func.attr == "Counter"
                )
            )
        ):
            dictionary_names.update(names)
            counter_names.update(names)

    for name in dictionary_names:
        reads = 0
        writes = name in counter_names
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == name
                and node.attr in {
                    "get",
                    "items",
                    "keys",
                    "setdefault",
                    "update",
                    "values",
                }
            ):
                reads += 1
                writes = writes or node.attr in {"setdefault", "update"}
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == name
            ):
                if isinstance(node.ctx, ast.Store):
                    writes = True
                else:
                    reads += 1
        if reads and writes:
            return True
    return False


def _used_top_level_functions(tree):
    definitions = _direct_function_definitions(tree)
    roots = [
        node
        for node in tree.body
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Import,
                ast.ImportFrom,
            ),
        )
    ]
    pending = list(_called_names(roots))
    used = set()
    while pending:
        name = pending.pop()
        if name in used or name not in definitions:
            continue
        used.add(name)
        pending.extend(_called_names(definitions[name].body))
    return [definitions[name] for name in used]


def _error_classification_complete(source_code):
    comments = "\n".join(
        match.group(1)
        for match in re.finditer(r"(?m)^\s*#(.*)$", source_code)
    ).lower()
    syntax_described = (
        "синтакс" in comments
        and (
            "двоеточ" in comments
            or "знак равенства" in comments
            or "сравнен" in comments
        )
    )
    names_described = (
        ("ошиб" in comments and "имен" in comments)
        and "count_evens" in comments
        and re.search(r"\bvalues?\b", comments)
    )
    logic_described = (
        "логическ" in comments
        and "return" in comments
        and "цикл" in comments
    )
    return bool(syntax_described and names_described and logic_described)


def _statistics_values(output):
    values = {}
    for label in ("сумма", "среднее", "минимум", "максимум"):
        match = re.search(
            rf"{label}\s*:\s*(-?\d+(?:[.,]\d+)?)",
            output.lower(),
        )
        if match:
            values[label] = float(match.group(1).replace(",", "."))
    return values


def _report_statuses(output, count):
    normalized = output.lower().replace("ё", "е")
    statuses = []
    for number in range(1, count + 1):
        match = re.search(
            rf"тест\s*{number}\s*:\s*(пройден|ошибк\w*)",
            normalized,
        )
        if not match:
            return None
        statuses.append(match.group(1).startswith("пройден"))
    summary = re.search(
        r"пройдено\s*(\d+)\s*из\s*(\d+)",
        normalized,
    )
    if not summary:
        return statuses, None
    return statuses, (int(summary.group(1)), int(summary.group(2)))


def _case_values(payload):
    if payload.get("__error__") or not payload.get("exists"):
        return []
    return payload.get("results", [])


def _matches_cases(results, expected):
    if len(results) != len(expected):
        return False
    return all(
        result.get("ok") and result.get("value") == expected_value
        for result, expected_value in zip(results, expected)
    )


def _task_2451(runner, source_code):
    tree = _parse_source(source_code)
    generated = _random_words(7)
    variants = [
        (
            [
                generated[0],
                generated[1],
                generated[0],
                generated[2],
                generated[1],
                generated[3],
            ],
            generated[:4],
        ),
        (generated[4:], generated[4:]),
        ([], []),
    ]
    checks = []
    assignment_found = True
    for words, expected in variants:
        variant_tree = copy.deepcopy(tree)
        assignment_found = (
            _replace_top_level_assignment(variant_tree, "words", words)
            and assignment_found
        )
        probe = """
__gc_payload = {
    "words": globals().get("words"),
}
"""
        output, payload = _run_probe(
            runner,
            ast.unparse(variant_tree),
            probe,
        )
        visible_result = _contains_word_sequence(output, expected)
        transformed_words = payload.get("words") == expected
        checks.append(
            not payload.get("__error__")
            and (visible_result or transformed_words)
        )

    return _finish(2451, [
        (
            assignment_found and checks[0],
            "повторы удалены с сохранением порядка первого появления",
        ),
        (
            assignment_found and all(checks[1:]),
            "решение работает для списка без повторов и пустого списка",
        ),
    ])


def _task_2452(runner, source_code):
    _parse_source(source_code)
    scenarios = [
        ("кот пёс кот\n", {"кот": 2, "пёс": 1}),
        (
            "Кот, пёс, кот и ещё один кот!\n",
            {"кот": 3, "пёс": 1, "и": 1, "ещё": 1, "один": 1},
        ),
        (
            "ЯБЛОКО; яблоко: груша? Слива. слива!\n",
            {"яблоко": 2, "груша": 1, "слива": 2},
        ),
    ]
    passed = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        passed.append(ok and _frequency_map(output) == expected)

    return _finish(2452, [
        (passed[0], "частоты слов правильно посчитаны в простой строке"),
        (
            all(passed[1:]),
            "регистр и знаки препинания не влияют на подсчёт",
        ),
    ])


def _task_2453(runner, source_code):
    _parse_source(source_code)
    scenarios = [
        (
            "Python, музыка, игры\nспорт, Игры, музыка\n",
            {
                "Общие": {"игры", "музыка"},
                "Все": {"python", "музыка", "игры", "спорт"},
                "Только у Алисы": {"python"},
                "Только у Бориса": {"спорт"},
            },
        ),
        (
            "  Чтение, МУЗЫКА  \nчтение, спорт\n",
            {
                "Общие": {"чтение"},
                "Все": {"чтение", "музыка", "спорт"},
                "Только у Алисы": {"музыка"},
                "Только у Бориса": {"спорт"},
            },
        ),
        (
            "чтение\nЧТЕНИЕ\n",
            {
                "Общие": {"чтение"},
                "Все": {"чтение"},
                "Только у Алисы": set(),
                "Только у Бориса": set(),
            },
        ),
    ]
    parsed = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        parsed.append((ok, _interest_output(output), expected))

    labels_present = all(
        ok and all(value is not None for value in actual.values())
        for ok, actual, _ in parsed
    )
    without_duplicates = all(
        all(
            len(items) == len(set(items))
            for items in actual.values()
            if items is not None
        )
        for _, actual, _ in parsed
    )
    common_and_union = all(
        set(actual["Общие"] or []) == expected["Общие"]
        and set(actual["Все"] or []) == expected["Все"]
        for _, actual, expected in parsed
    ) and without_duplicates
    differences = all(
        set(actual["Только у Алисы"] or []) == expected["Только у Алисы"]
        and set(actual["Только у Бориса"] or []) == expected["Только у Бориса"]
        for _, actual, expected in parsed
    ) and without_duplicates

    return _finish(2453, [
        (
            labels_present,
            "ввод корректно разобран независимо от регистра и пробелов",
        ),
        (common_and_union, "правильно найдены общие и все интересы"),
        (differences, "правильно найдены интересы только каждого пользователя"),
    ])


def _task_2454(runner, source_code):
    tree = _parse_source(source_code)
    variants = [
        (
            ["Алиса:15", "Борис:9", "Алиса:7", "Виктор:12", "Борис:8"],
            [("Алиса", 22), ("Борис", 17), ("Виктор", 12)],
        ),
        (
            [
                "Аня:5",
                "Борис:2",
                "Аня:4",
                "Вера:10",
                "Аня:8",
                "Борис:3",
            ],
            [("Аня", 17), ("Вера", 10), ("Борис", 5)],
        ),
    ]
    parsed_runs = []
    assignment_found = True
    for source_results, expected in variants:
        variant_tree = copy.deepcopy(tree)
        assignment_found = (
            _replace_top_level_assignment(variant_tree, "results", source_results)
            and assignment_found
        )
        ok, output = _safe_source_run(
            runner,
            ast.unparse(variant_tree),
        )
        rankings = _rankings(output)
        parsed_runs.append((ok, rankings[-len(expected):], expected))

    parsed_all = all(
        ok and len(actual) == len(expected)
        for ok, actual, expected in parsed_runs
    )
    totals_all = all(
        {name: score for _, name, score in actual}
        == {name: score for name, score in expected}
        for _, actual, expected in parsed_runs
    )
    ordered_all = all(
        [(name, score) for _, name, score in actual] == expected
        for _, actual, expected in parsed_runs
    )

    return _finish(2454, [
        (
            assignment_found and parsed_all,
            "строки результатов разобраны на имя и баллы",
        ),
        (
            assignment_found and totals_all,
            "баллы каждого участника правильно суммируются",
        ),
        (
            assignment_found and ordered_all,
            "таблица отсортирована по убыванию итоговых баллов",
        ),
    ])


def _task_2455(runner, source_code):
    tree = _parse_source(source_code)
    generated = _random_words(5)
    variants = [
        (
            {"золото": 3, "ключ": 1},
            {"золото": 15, "зелье": 2, "карта": 1},
            {"золото": 18, "ключ": 1, "зелье": 2, "карта": 1},
        ),
        (
            {generated[0]: 2, generated[1]: 1, generated[2]: 4},
            {generated[0]: 5, generated[2]: 6, generated[3]: 3},
            {
                generated[0]: 7,
                generated[1]: 1,
                generated[2]: 10,
                generated[3]: 3,
            },
        ),
    ]
    results = []
    assignments_found = True
    for player, chest, expected in variants:
        variant_tree = copy.deepcopy(tree)
        assignments_found = (
            _replace_top_level_assignment(variant_tree, "player", player)
            and _replace_top_level_assignment(variant_tree, "chest", chest)
            and assignments_found
        )
        probe = """
__gc_payload = {
    "player": globals().get("player"),
    "chest": globals().get("chest"),
}
"""
        _, payload = _run_probe(runner, ast.unparse(variant_tree), probe)
        results.append((payload, expected))

    inventory_correct = all(
        not payload.get("__error__") and payload.get("player") == expected
        for payload, expected in results
    )
    chest_empty = all(payload.get("chest") == {} for payload, _ in results)
    return _finish(2455, [
        (
            assignments_found and inventory_correct,
            "новые предметы добавлены, количества совпадающих предметов сложены",
        ),
        (
            assignments_found and inventory_correct and chest_empty,
            "сундук полностью очищен, итоговый инвентарь верен",
        ),
    ])


def _task_2456(runner, source_code):
    tree = _parse_source(source_code)
    scenarios = [
        ("кот пёс кот сова лиса пёс енот\n", ["енот", "лиса", "сова"]),
        ("а а б б\n", []),
        ("яблоко груша слива\n", ["груша", "слива", "яблоко"]),
    ]
    results = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        results.append((ok, _rare_items(output), expected))

    selected = all(
        ok and set(actual) == set(expected)
        for ok, actual, expected in results
    )
    sorted_and_empty = all(
        actual == expected
        for _, actual, expected in results
    )
    return _finish(2456, [
        (
            selected and _uses_frequency_dictionary(tree),
            "словарь частот построен и выбраны слова с частотой один",
        ),
        (
            sorted_and_empty,
            "слова отсортированы, случай без редких слов обработан",
        ),
    ])


def _task_2457(runner, source_code):
    tree = _parse_source(source_code)
    generator = random.SystemRandom()
    random_case = [
        2 * generator.randint(-50, 50),
        2 * generator.randint(-50, 50) + 1,
        2 * generator.randint(-50, 50),
        2 * generator.randint(-50, 50) + 1,
        2 * generator.randint(-50, 50),
    ]
    cases = [
        {"args": [[1, 2, 4, 7, 10]]},
        {"args": [[]]},
        {"args": [[1, 3, 5]]},
        {"args": [[2, 4, 6]]},
        {"args": [random_case]},
    ]
    _, payload = _run_function_cases(runner, tree, "count_even", cases)
    results = _case_values(payload)
    expected = [3, 0, 0, 3, 3]
    fixed = (
        len(results) == len(expected)
        and results[0].get("ok")
        and results[0].get("value") == 3
    )
    all_checks = _matches_cases(results, expected)
    classified = _error_classification_complete(source_code)
    return _finish(2457, [
        (fixed, "функция count_even исправлена и считает чётные числа"),
        (
            classified,
            "в комментариях отмечены синтаксические, именные и логические ошибки",
        ),
        (
            all_checks,
            "заданные и дополнительная проверка дают ожидаемый результат",
        ),
    ])


def _task_2458(runner, source_code):
    tree = _parse_source(source_code)
    definitions = _used_top_level_functions(tree)
    has_three_functions = len(definitions) >= 3
    has_parameters = sum(bool(node.args.args) for node in definitions) >= 2
    has_return = any(
        isinstance(node, ast.Return) and node.value is not None
        for definition in definitions
        for node in ast.walk(definition)
    )

    scenarios = [
        (
            "1 2 3\n",
            {
                "сумма": 6.0,
                "среднее": 2.0,
                "минимум": 1.0,
                "максимум": 3.0,
            },
        ),
        (
            "-5 2 9 4\n",
            {
                "сумма": 10.0,
                "среднее": 2.5,
                "минимум": -5.0,
                "максимум": 9.0,
            },
        ),
    ]
    behavior = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        behavior.append(ok and _statistics_values(output) == expected)
    normal_behavior = all(behavior)

    empty_ok, _ = _safe_program_run(runner, "\n")
    return _finish(2458, [
        (
            has_three_functions,
            "программа разделена как минимум на три функции",
        ),
        (
            has_parameters and has_return and normal_behavior,
            "функции используют параметры/return и правильно считают статистику",
        ),
        (
            empty_ok,
            "пустой ввод не приводит к необработанной ошибке",
        ),
    ])


def _task_2459(runner, source_code):
    tree = _parse_source(source_code)
    random_parts = _random_words(3)
    random_name = "   ".join(
        part.swapcase()
        for part in random_parts
    )
    cases = [
        {"args": ["   иВАН   иВАНОВ  "]},
        {"args": ["аЛИСА"]},
        {"args": [""]},
        {"args": ["анна   мария"]},
        {"args": ["  ПЁТР петров "]},
        {"args": ["сЕРГЕЙ   иВАНОВИЧ   пЕТРОВ"]},
        {"args": [f"  {random_name}   "]},
    ]
    expected = [
        "Иван Иванов",
        "Алиса",
        "",
        "Анна Мария",
        "Пётр Петров",
        "Сергей Иванович Петров",
        " ".join(part.capitalize() for part in random_parts),
    ]
    _, payload = _run_function_cases(runner, tree, "normalize_name", cases)
    results = _case_values(payload)
    core_ok = _matches_cases(results[:3], expected[:3])
    own_checks = _executed_call_count(tree, "normalize_name") >= 6
    hidden_ok = _matches_cases(results[3:], expected[3:])
    return _finish(2459, [
        (
            core_ok,
            "normalize_name удаляет лишние пробелы и исправляет регистр",
        ),
        (
            hidden_ok and own_checks,
            "проходят дополнительные случаи и добавлены собственные проверки",
        ),
    ])


def _task_2460(runner, source_code):
    tree = _parse_source(source_code)
    generator = random.SystemRandom()
    random_integers = [
        generator.randint(-100, 100)
        for _ in range(7)
    ]
    random_halves = [
        generator.randint(-20, 20) / 2
        for _ in range(5)
    ]
    original_lists = [
        [2, 4, 6],
        [1.5, 2.5],
        [],
        [10],
        [-1, 1],
        [0.1, 0.2, 0.3],
        random_integers,
        random_halves,
    ]
    cases = [{"args": [value]} for value in original_lists]
    expected = [
        4.0,
        2.0,
        None,
        10.0,
        0.0,
        0.2,
        sum(random_integers) / len(random_integers),
        sum(random_halves) / len(random_halves),
    ]
    _, payload = _run_function_cases(runner, tree, "average", cases)
    results = _case_values(payload)
    values_ok = _matches_cases(results[:3], expected[:3])
    all_values_ok = (
        len(results) == len(expected)
        and all(
            result.get("ok")
            and (
                result.get("value") == expected_value
                or (
                    isinstance(expected_value, float)
                    and isinstance(result.get("value"), (int, float))
                    and abs(result["value"] - expected_value) < 1e-9
                )
            )
            for result, expected_value in zip(results, expected)
        )
    )
    unchanged = (
        len(results) == len(original_lists)
        and all(
            result.get("args_after") == [original]
            for result, original in zip(results, original_lists)
        )
    )
    own_checks = _executed_call_count(tree, "average") >= 5
    return _finish(2460, [
        (
            values_ok,
            "average верно работает с целыми, дробными и пустым списком",
        ),
        (
            all_values_ok and unchanged and own_checks,
            "список не изменяется и добавлено не менее пяти проверок",
        ),
    ])


def _password_result(result):
    if not result.get("ok"):
        return None
    value = result.get("value")
    if not isinstance(value, list) or len(value) != 2:
        return None
    valid, errors = value
    if not isinstance(valid, bool) or not isinstance(errors, list):
        return None
    return valid, [str(error).strip().lower() for error in errors]


def _task_2461(runner, source_code):
    tree = _parse_source(source_code)
    published_passwords = [
        "Python12",
        "python12",
        "Password",
        "PASSWORD1",
        "Pyth on12",
        "Pw1",
        "pw 1",
    ]
    published_expected = [
        (True, []),
        (False, ["нет заглавной буквы"]),
        (False, ["нет цифры"]),
        (False, ["нет строчной буквы"]),
        (False, ["есть пробел"]),
        (False, ["короче 8 символов"]),
        (
            False,
            ["короче 8 символов", "нет заглавной буквы", "есть пробел"],
        ),
    ]
    random_word = _random_words(1)[0]
    generated_passwords = [
        random_word.capitalize() + "42",
        random_word + "42",
        random_word.capitalize(),
        random_word.upper() + "7",
        random_word[:6].capitalize() + " 42",
    ]
    generated_expected = [
        (True, []),
        (False, ["нет заглавной буквы"]),
        (False, ["нет цифры"]),
        (False, ["нет строчной буквы"]),
        (False, ["есть пробел"]),
    ]
    passwords = published_passwords + generated_passwords
    expected = published_expected + generated_expected
    cases = [{"args": [password]} for password in passwords]
    _, payload = _run_function_cases(runner, tree, "check_password", cases)
    normalized = [_password_result(item) for item in _case_values(payload)]
    booleans_ok = (
        len(normalized) == len(expected)
        and all(
            actual is not None and actual[0] == wanted[0]
            for actual, wanted in zip(normalized, expected)
        )
    )
    errors_ok = (
        len(normalized) == len(expected)
        and all(
            actual is not None
            and len(actual[1]) == len(wanted[1])
            and set(actual[1]) == set(wanted[1])
            for actual, wanted in zip(normalized, expected)
        )
    )
    mentioned_passwords = set()
    for root in _reachable_execution_nodes(
        tree,
        excluded={"check_password"},
    ):
        mentioned_passwords.update(
            node.value
            for node in ast.walk(root)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in published_passwords
        )
    own_checks = (
        _executed_call_count(tree, "check_password") >= 7
        and len(mentioned_passwords) == len(published_passwords)
    )
    return _finish(2461, [
        (booleans_ok, "функция возвращает верный логический результат"),
        (errors_ok, "функция возвращает полный список проблем"),
        (
            booleans_ok and errors_ok and own_checks,
            "в программе подготовлены проверки для всех семи случаев",
        ),
    ])


def _distinct_tested_functions(calls):
    functions = set()
    for call in calls:
        if len(call.args) < 2:
            continue
        functions.add(ast.dump(call.args[0], include_attributes=False))
    return len(functions) >= 2


def _task_2462(runner, source_code):
    tree = _parse_source(source_code)
    definitions = _function_definitions(tree, "run_tests")
    accepts_arguments = bool(
        definitions and len(definitions[0].args.args) >= 2
    )

    generator = random.SystemRandom()
    first_arguments = generator.sample(range(-100, 101), 4)
    first_actual = [value % 3 == 0 for value in first_arguments]
    first_expected = list(first_actual)
    first_mismatch = generator.randrange(len(first_expected))
    first_expected[first_mismatch] = not first_expected[first_mismatch]

    second_arguments = generator.sample(range(110, 310), 6)
    second_actual = [value * 2 + 1 for value in second_arguments]
    second_expected = list(second_actual)
    mismatch_positions = generator.sample(range(len(second_expected)), 2)
    for position in mismatch_positions:
        second_expected[position] += generator.choice((1, 3, 5))

    scenarios = [
        {
            "arguments": first_arguments,
            "actual": first_actual,
            "expected": first_expected,
        },
        {
            "arguments": second_arguments,
            "actual": second_actual,
            "expected": second_expected,
        },
    ]
    encoded_scenarios = _encoded_json(scenarios)
    probe = f"""
import base64 as __gc_base64
import contextlib as __gc_contextlib
import io as __gc_io
__gc_scenarios = __gc_json.loads(
    __gc_base64.b64decode({json.dumps(encoded_scenarios)}).decode("utf-8")
)
__gc_reports = []
for __gc_scenario in __gc_scenarios:
    __gc_calls = []
    __gc_values = dict(zip(
        __gc_scenario["arguments"],
        __gc_scenario["actual"],
    ))
    def __gc_checked(argument):
        __gc_calls.append(argument)
        return __gc_values[argument]
    __gc_tests = list(zip(
        __gc_scenario["arguments"],
        __gc_scenario["expected"],
    ))
    __gc_buffer = __gc_io.StringIO()
    with __gc_contextlib.redirect_stdout(__gc_buffer):
        globals()["run_tests"](__gc_checked, __gc_tests)
    __gc_reports.append({{
        "calls": __gc_calls,
        "output": __gc_buffer.getvalue(),
    }})
__gc_payload = {{"reports": __gc_reports}}
"""
    _, payload = _run_probe(
        runner,
        _definitions_source(tree),
        probe,
    )
    reports = payload.get("reports", [])

    calls_ok = len(reports) == len(scenarios) and all(
        report.get("calls") == scenario["arguments"]
        for report, scenario in zip(reports, scenarios)
    )
    statuses_ok = len(reports) == len(scenarios)
    report_ok = statuses_ok
    for report, scenario in zip(reports, scenarios):
        expected_statuses = [
            actual == expected
            for actual, expected in zip(
                scenario["actual"],
                scenario["expected"],
            )
        ]
        parsed = _report_statuses(
            str(report.get("output", "")),
            len(expected_statuses),
        )
        if parsed is None:
            statuses_ok = False
            report_ok = False
            continue
        statuses, summary = parsed
        statuses_ok = statuses_ok and statuses == expected_statuses
        report_ok = report_ok and (
            statuses == expected_statuses
            and summary == (
                sum(expected_statuses),
                len(expected_statuses),
            )
        )

    own_calls = _reachable_calls(tree, "run_tests")
    own_runs = _distinct_tested_functions(own_calls)
    _, own_output = _safe_source_run(
        runner,
        source_code,
        time_limit=3,
    )
    intentional_failure = bool(
        re.search(
            r"тест\s*\d+\s*:\s*ошиб",
            own_output.lower().replace("ё", "е"),
        )
    )

    return _finish(2462, [
        (
            accepts_arguments and calls_ok,
            "run_tests принимает функцию и список тестов и запускает каждый тест",
        ),
        (
            statuses_ok,
            "совпадение ожидаемого и фактического результата определяется верно",
        ),
        (
            report_ok,
            "выводится отчёт по каждому тесту и верный итог",
        ),
        (
            own_runs and intentional_failure,
            "система проверена на разных функциях и содержит падающий тест",
        ),
    ])


_TASK_HANDLERS = {
    2451: _task_2451,
    2452: _task_2452,
    2453: _task_2453,
    2454: _task_2454,
    2455: _task_2455,
    2456: _task_2456,
    2457: _task_2457,
    2458: _task_2458,
    2459: _task_2459,
    2460: _task_2460,
    2461: _task_2461,
    2462: _task_2462,
}
