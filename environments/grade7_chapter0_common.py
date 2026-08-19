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


def _replace_top_level_assignment(tree, name, value, capture_as=None):
    replacement = _literal_node(value)
    if capture_as is not None:
        replacement = ast.NamedExpr(
            target=ast.Name(id=capture_as, ctx=ast.Store()),
            value=replacement,
        )
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


def _literal_input_prompts(tree):
    """Return string literals passed directly to ``input`` in source code."""
    prompts = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id == "input"
        ):
            continue
        try:
            prompt = ast.literal_eval(node.args[0])
        except (TypeError, ValueError):
            continue
        if isinstance(prompt, str) and prompt:
            prompts.append(prompt)
    return tuple(prompts)


def _without_literal_input_prompts(output, prompts, prompt_count):
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]

    # With redirected stdin, ``input(prompt)`` writes prompts without echoing
    # entered data.  Remove only exact prompt literals found in the submitted
    # source, never an arbitrary human-looking prefix.
    candidates = sorted(set(prompts), key=len, reverse=True)
    for _ in range(prompt_count):
        match = next(
            (prompt for prompt in candidates if normalized.startswith(prompt)),
            None,
        )
        if match is None:
            break
        normalized = normalized[len(match):]
    return normalized


def _matches_prompted_exact_output(output, expected, prompts, prompt_count):
    """Ignore submitted literal input prompts and compare the answer exactly."""
    return (
        _without_literal_input_prompts(output, prompts, prompt_count)
        == expected
    )


def _frequency_map(output):
    pairs = re.findall(
        (
            r"[\"']?([A-Za-zА-Яа-яЁё]+)[\"']?\s*"
            r"(?::|=|[—–-])\s*(-?\d+)"
        ),
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


def _interest_output(output, prompts):
    output = _without_literal_input_prompts(output, prompts, 2)
    labels = ("Общие", "Все", "Только у Алисы", "Только у Бориса")
    result = {label: None for label in labels}
    lines = output.split("\n") if output else []
    if len(lines) != len(labels):
        return result

    for line in lines:
        matched_label = None
        matched_value = None
        for label in labels:
            match = re.fullmatch(
                rf"[ \t]*{re.escape(label)}[ \t]*:[ \t]*([^\r\n]*)",
                line,
            )
            if match is not None:
                matched_label = label
                matched_value = match.group(1)
                break
        if matched_label is None or result[matched_label] is not None:
            return {label: None for label in labels}
        result[matched_label] = _parse_items(matched_value)
    return result


def _rankings(output, prompts, prompt_count):
    text = _without_literal_input_prompts(output, prompts, prompt_count)
    if not text:
        return []
    rankings = []
    for line in text.split("\n"):
        match = re.fullmatch(
            r"[ \t]*(\d+)\.[ \t]+(.+?)[ \t]+—[ \t]+(-?\d+)[ \t]*",
            line,
        )
        if match is None:
            return []
        rankings.append(
            (int(match.group(1)), match.group(2).strip(), int(match.group(3)))
        )
    return rankings


def _rare_items(output, prompts):
    text = _without_literal_input_prompts(output, prompts, 1)
    lowered = text.lower().replace("ё", "е")
    if (
        re.search(r"\bнет\s+редк", lowered)
        or re.search(r"\bредк\w*\s+слов\w*\s+нет\b", lowered)
        or "редкие слова отсутствуют" in lowered
        or "редких слов не найдено" in lowered
    ):
        return []
    if "\n" in text:
        return None
    return _parse_items(text)


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
        elif isinstance(value, ast.Call):
            constructor = None
            if isinstance(value.func, ast.Name):
                constructor = value.func.id
            elif isinstance(value.func, ast.Attribute):
                constructor = value.func.attr
            if constructor in {"dict", "Counter"}:
                dictionary_names.update(names)
            if constructor == "Counter":
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
    comments = [
        match.group(1)
        for match in re.finditer(r"(?m)^\s*#(.*)$", source_code)
    ]
    comments = [comment.lower() for comment in comments]

    def matching_indices(category_parts, fragment):
        return {
            index
            for index, comment in enumerate(comments)
            if (
                all(part in comment for part in category_parts)
                and fragment(comment)
            )
        }

    matches = [matching_indices(
        ("синтакс",),
        lambda comment: (
            "двоеточ" in comment
            and "def" in comment
            and re.search(r"\bcount_even\b", comment) is not None
        ),
    )]
    matches.append(matching_indices(
        ("синтакс",),
        lambda comment: (
            "==" in comment
            and re.search(r"(?<![=])=(?!=)", comment) is not None
            and ("услов" in comment or re.search(r"\bif\b", comment))
        ),
    ))
    matches.append(matching_indices(
        ("ошиб", "имен"),
        lambda comment: re.search(r"\bcount_evens\b", comment) is not None,
    ))
    matches.append(matching_indices(
        ("ошиб", "имен"),
        lambda comment: re.search(r"\bvalue\b", comment) is not None,
    ))
    matches.append(matching_indices(
        ("логическ",),
        lambda comment: (
            "return" in comment
            and any(
                marker in comment
                for marker in ("цикл", "отступ", "вложен")
            )
        ),
    ))

    def can_choose_distinct(position, used):
        if position == len(matches):
            return True
        return any(
            can_choose_distinct(position + 1, used | {index})
            for index in matches[position] - used
        )

    return len(comments) >= 5 and can_choose_distinct(0, set())


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


def _output_lines(output):
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return []
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return normalized.split("\n")


def _instrument_function_call_log(tree, function_name):
    """Wrap a top-level function and record calls made by student code."""
    instrumented = copy.deepcopy(tree)
    for index, node in enumerate(instrumented.body):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue

        wrapper = ast.parse(f"""
__gc_original_function = {function_name}
__gc_observed_calls = []
__gc_function_call_depth = 0
__gc_original_print = print
__gc_printed_strings = []
def __gc_record_print(*__gc_values, **__gc_print_kwargs):
    __gc_printed_strings.extend(
        __gc_value
        for __gc_value in __gc_values
        if isinstance(__gc_value, str)
    )
    return __gc_original_print(*__gc_values, **__gc_print_kwargs)
print = __gc_record_print
def __gc_record_function_call(*__gc_args, **__gc_kwargs):
    global __gc_function_call_depth
    __gc_outer_call = __gc_function_call_depth == 0
    __gc_function_call_depth += 1
    try:
        __gc_result = __gc_original_function(*__gc_args, **__gc_kwargs)
    finally:
        __gc_function_call_depth -= 1
    if __gc_outer_call:
        __gc_observed_calls.append({{
            "argument": (
                __gc_args[0]
                if __gc_args and isinstance(__gc_args[0], str)
                else None
            ),
            "result": __gc_result if isinstance(__gc_result, str) else None,
        }})
    return __gc_result
{function_name} = __gc_record_function_call
""").body
        instrumented.body[index + 1:index + 1] = wrapper
        ast.fix_missing_locations(instrumented)
        return instrumented
    return None


def _instrument_first_argument_log(tree, function_name, keyword_name):
    """Wrap a top-level function and retain arguments from real outer calls."""
    instrumented = copy.deepcopy(tree)
    for index, node in enumerate(instrumented.body):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue

        wrapper = ast.parse(f"""
import copy as __gc_copy
__name__ = "__main__"
__gc_original_observed_function = {function_name}
__gc_observed_arguments = []
__gc_observed_call_depth = 0
def __gc_record_observed_call(*__gc_args, **__gc_kwargs):
    global __gc_observed_call_depth
    __gc_outer_call = __gc_observed_call_depth == 0
    if __gc_outer_call:
        __gc_argument = (
            __gc_args[0]
            if __gc_args
            else __gc_kwargs.get({keyword_name!r})
        )
        try:
            __gc_argument = __gc_copy.deepcopy(__gc_argument)
        except BaseException:
            __gc_argument = None
        __gc_observed_arguments.append(__gc_argument)
    __gc_observed_call_depth += 1
    try:
        return __gc_original_observed_function(*__gc_args, **__gc_kwargs)
    finally:
        __gc_observed_call_depth -= 1
{function_name} = __gc_record_observed_call
""").body
        instrumented.body[index + 1:index + 1] = wrapper
        ast.fix_missing_locations(instrumented)
        return instrumented
    return None


def _instrument_callable_argument_log(tree, function_name, keyword_name):
    """Wrap a function and retain callable objects passed by student code."""
    instrumented = copy.deepcopy(tree)
    for index, node in enumerate(instrumented.body):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue

        wrapper = ast.parse(f"""
__name__ = "__main__"
__gc_original_callable_consumer = {function_name}
__gc_observed_callables = []
__gc_callable_consumer_depth = 0
def __gc_record_callable_argument(*__gc_args, **__gc_kwargs):
    global __gc_callable_consumer_depth
    __gc_outer_call = __gc_callable_consumer_depth == 0
    if __gc_outer_call:
        __gc_callable = (
            __gc_args[0]
            if __gc_args
            else __gc_kwargs.get({keyword_name!r})
        )
        if callable(__gc_callable):
            __gc_observed_callables.append(__gc_callable)
    __gc_callable_consumer_depth += 1
    try:
        return __gc_original_callable_consumer(*__gc_args, **__gc_kwargs)
    finally:
        __gc_callable_consumer_depth -= 1
{function_name} = __gc_record_callable_argument
""").body
        instrumented.body[index + 1:index + 1] = wrapper
        ast.fix_missing_locations(instrumented)
        return instrumented
    return None


def _all_call_results_are_printed(output, calls, printed_strings=()):
    remaining_lines = _output_lines(output)
    remaining_strings = list(printed_strings)
    for call in calls:
        result = call.get("result")
        if not isinstance(result, str):
            return False
        if result in remaining_strings:
            remaining_strings.remove(result)
            continue
        if not result:
            if "" not in remaining_lines:
                return False
            remaining_lines.remove("")
            continue

        pattern = re.compile(rf"(?<!\w){re.escape(result)}(?!\w)")
        for index, line in enumerate(remaining_lines):
            match = pattern.search(line)
            if match is None:
                continue
            remaining_lines[index] = line[:match.start()] + line[match.end():]
            break
        else:
            return False
    return True


def _exact_test_report_lines(actual_values, expected_values):
    lines = []
    passed = 0
    for number, (actual, expected) in enumerate(
        zip(actual_values, expected_values),
        1,
    ):
        if actual == expected:
            passed += 1
            lines.append(f"Тест {number}: пройден")
        else:
            lines.append(
                f"Тест {number}: ошибка — "
                f"ожидалось {expected}, получено {actual}"
            )
    lines.append(f"Пройдено {passed} из {len(expected_values)} тестов")
    return lines


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
    prompts = _literal_input_prompts(tree)
    generated = _random_words(7)
    scenarios = [
        (
            ", ".join((
                generated[0],
                generated[1],
                generated[0],
                generated[2],
                generated[1],
                generated[3],
            )) + "\n",
            generated[:4],
        ),
        (
            "  {} ,{},  {}  \n".format(*generated[4:]),
            generated[4:],
        ),
        (", ".join(generated[4:]) + "\n", generated[4:]),
        (", ".join([generated[0]] * 4) + "\n", [generated[0]]),
    ]
    checks = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        checks.append(
            ok
            and _matches_prompted_exact_output(
                output,
                ", ".join(expected),
                prompts,
                1,
            )
        )

    return _finish(2451, [
        (
            checks[0] and checks[1] and checks[3],
            (
                "слова читаются из строки через запятую; повторы "
                "удалены с сохранением порядка"
            ),
        ),
        (
            checks[2],
            "решение работает для строки без повторов",
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
    tree = _parse_source(source_code)
    prompts = _literal_input_prompts(tree)
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
        parsed.append((ok, _interest_output(output, prompts), expected))

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
    prompts = _literal_input_prompts(tree)
    generated = sorted(_random_words(3))
    scenarios = [
        (
            "5\nАлиса:15\nБорис:9\nАлиса:7\nВиктор:12\nБорис:8\n",
            [("Алиса", 22), ("Борис", 17), ("Виктор", 12)],
        ),
        (
            "6\nАня:5\nБорис:2\nАня:4\nВера:10\nАня:8\nБорис:3\n",
            [("Аня", 17), ("Вера", 10), ("Борис", 5)],
        ),
        (
            "4\n{}:5\n{}:3\n{}:2\n{}:5\n".format(
                generated[2],
                generated[0],
                generated[0],
                generated[1],
            ),
            [(name, 5) for name in generated],
        ),
        (
            (
                "6\n"
                "Анна Мария:-5\n"
                "Борис Петров:4\n"
                "Анна Мария:2\n"
                "Ян:-1\n"
                "Борис Петров:-8\n"
                "Ян:-2\n"
            ),
            [
                ("Анна Мария", -3),
                ("Ян", -3),
                ("Борис Петров", -4),
            ],
        ),
    ]
    parsed_runs = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        rankings = _rankings(output, prompts, len(input_data.splitlines()))
        parsed_runs.append((ok, rankings, expected))

    parsed_all = all(
        ok and len(actual) == len(expected)
        and [place for place, _, _ in actual]
        == list(range(1, len(expected) + 1))
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
            parsed_all,
            "N строк результатов вида Имя:баллы правильно разобраны",
        ),
        (
            totals_all,
            "баллы каждого участника правильно суммируются",
        ),
        (
            ordered_all,
            (
                "таблица отсортирована по убыванию баллов, а при "
                "равенстве — по имени"
            ),
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
            _replace_top_level_assignment(
                variant_tree,
                "player",
                player,
                capture_as="__gc_initial_player",
            )
            and _replace_top_level_assignment(
                variant_tree,
                "chest",
                chest,
                capture_as="__gc_initial_chest",
            )
            and assignments_found
        )
        probe = """
__gc_payload = {
    "player": globals().get("player"),
    "chest": globals().get("chest"),
    "player_in_place": (
        globals().get("player") is globals().get("__gc_initial_player")
    ),
    "chest_in_place": (
        globals().get("chest") is globals().get("__gc_initial_chest")
    ),
}
"""
        _, payload = _run_probe(runner, ast.unparse(variant_tree), probe)
        results.append((payload, expected))

    inventory_correct = all(
        not payload.get("__error__")
        and payload.get("player") == expected
        and payload.get("player_in_place") is True
        for payload, expected in results
    )
    chest_empty = all(
        payload.get("chest") == {}
        and payload.get("chest_in_place") is True
        for payload, _ in results
    )
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
    prompts = _literal_input_prompts(tree)
    scenarios = [
        ("кот пёс кот сова лиса пёс енот\n", ["енот", "лиса", "сова"]),
        ("а а б б\n", []),
        ("яблоко груша слива\n", ["груша", "слива", "яблоко"]),
    ]
    results = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        results.append((ok, output, _rare_items(output, prompts), expected))

    selected = all(
        ok and isinstance(actual, list) and set(actual) == set(expected)
        for ok, _, actual, expected in results
    )
    sorted_nonempty = all(
        actual == expected
        for _, _, actual, expected in results
        if expected
    )
    no_rare_message = all(
        ok
        and _matches_prompted_exact_output(
            output,
            "Редких слов нет",
            prompts,
            1,
        )
        for ok, output, _, expected in results
        if not expected
    )
    return _finish(2456, [
        (
            selected and _uses_frequency_dictionary(tree),
            "словарь частот построен и выбраны слова с частотой один",
        ),
        (
            sorted_nonempty and no_rare_message,
            (
                "слова отсортированы, а при их отсутствии выведено "
                "«Редких слов нет»"
            ),
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
        (
            "-7\n",
            {
                "сумма": -7.0,
                "среднее": -7.0,
                "минимум": -7.0,
                "максимум": -7.0,
            },
        ),
    ]
    behavior = []
    for input_data, expected in scenarios:
        ok, output = _safe_program_run(runner, input_data)
        behavior.append(ok and _statistics_values(output) == expected)
    return _finish(2458, [
        (
            has_three_functions,
            "программа разделена как минимум на три функции",
        ),
        (
            has_parameters and has_return and behavior[0],
            "функции используют параметры/return и правильно считают статистику",
        ),
        (
            all(behavior[1:]),
            (
                "статистика верна для нескольких наборов, включая "
                "отрицательные числа и одно число"
            ),
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
    hidden_ok = _matches_cases(results[3:], expected[3:])

    instrumented = _instrument_function_call_log(tree, "normalize_name")
    observed_calls = []
    printed_strings = []
    own_output = ""
    if instrumented is not None:
        own_output, own_payload = _run_probe(
            runner,
            ast.unparse(instrumented),
            (
                '__gc_payload = {'
                '"calls": globals().get("__gc_observed_calls", []), '
                '"printed": globals().get("__gc_printed_strings", []),'
                '}'
            ),
        )
        candidate_calls = own_payload.get("calls", [])
        if isinstance(candidate_calls, list):
            observed_calls = candidate_calls
        candidate_printed = own_payload.get("printed", [])
        if isinstance(candidate_printed, list):
            printed_strings = candidate_printed

    published_arguments = {
        "   иВАН   иВАНОВ  ",
        "аЛИСА",
        "",
    }
    observed_arguments = [
        call.get("argument")
        for call in observed_calls
        if isinstance(call, dict)
    ]
    own_arguments = {
        argument
        for argument in observed_arguments
        if isinstance(argument, str) and argument not in published_arguments
    }
    own_checks = (
        len(observed_calls) >= 6
        and published_arguments.issubset(observed_arguments)
        and len(own_arguments) >= 3
        and _all_call_results_are_printed(
            own_output,
            observed_calls,
            printed_strings,
        )
    )
    return _finish(2459, [
        (
            core_ok,
            "normalize_name удаляет лишние пробелы и исправляет регистр",
        ),
        (
            hidden_ok and own_checks,
            (
                "выполнены и напечатаны три заданные и не менее трёх "
                "различных собственных проверок"
            ),
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
    observed_arguments = []
    instrumented = _instrument_first_argument_log(
        tree,
        "average",
        "numbers",
    )
    if instrumented is not None:
        _, observed_payload = _run_probe(
            runner,
            ast.unparse(instrumented),
            """
__gc_payload = {
    "arguments": [
        __gc_value
        for __gc_value in globals().get("__gc_observed_arguments", [])
        if isinstance(__gc_value, list)
        and all(
            isinstance(__gc_item, (int, float))
            and not isinstance(__gc_item, bool)
            for __gc_item in __gc_value
        )
    ],
}
""",
        )
        candidate_arguments = observed_payload.get("arguments", [])
        if isinstance(candidate_arguments, list):
            observed_arguments = candidate_arguments

    published_arguments = ([2, 4, 6], [1.5, 2.5], [])
    published_keys = {tuple(argument) for argument in published_arguments}
    observed_keys = {
        tuple(argument)
        for argument in observed_arguments
        if isinstance(argument, list)
    }
    own_keys = observed_keys - published_keys
    own_checks = (
        published_keys.issubset(observed_keys)
        and len(own_keys) >= 2
    )
    return _finish(2460, [
        (
            values_ok,
            "average верно работает с целыми, дробными и пустым списком",
        ),
        (
            all_values_ok and unchanged and own_checks,
            (
                "список не изменяется; выполнены три заданные "
                "и не менее двух различных собственных проверок"
            ),
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
    if not all(isinstance(error, str) for error in errors):
        return None
    return valid, errors


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
            and actual[1] == wanted[1]
            for actual, wanted in zip(normalized, expected)
        )
    )
    observed_passwords = []
    instrumented = _instrument_first_argument_log(
        tree,
        "check_password",
        "password",
    )
    if instrumented is not None:
        _, observed_payload = _run_probe(
            runner,
            ast.unparse(instrumented),
            """
__gc_payload = {
    "arguments": [
        __gc_value
        for __gc_value in globals().get("__gc_observed_arguments", [])
        if isinstance(__gc_value, str)
    ],
}
""",
        )
        candidate_passwords = observed_payload.get("arguments", [])
        if isinstance(candidate_passwords, list):
            observed_passwords = candidate_passwords
    own_checks = set(published_passwords).issubset(observed_passwords)
    return _finish(2461, [
        (booleans_ok, "функция возвращает верный логический результат"),
        (
            errors_ok,
            "функция возвращает точные сообщения в заданном порядке",
        ),
        (
            booleans_ok and errors_ok and own_checks,
            "в программе подготовлены проверки для всех семи случаев",
        ),
    ])


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
        expected_lines = _exact_test_report_lines(
            scenario["actual"],
            scenario["expected"],
        )
        report_ok = report_ok and _output_lines(
            str(report.get("output", ""))
        ) == expected_lines

    own_runs = False
    own_output = ""
    instrumented = _instrument_callable_argument_log(
        tree,
        "run_tests",
        "function",
    )
    if instrumented is not None:
        own_output, own_payload = _run_probe(
            runner,
            ast.unparse(instrumented),
            """
__gc_unique_callables = []
for __gc_candidate in globals().get("__gc_observed_callables", []):
    if not any(
        __gc_candidate is __gc_existing
        for __gc_existing in __gc_unique_callables
    ):
        __gc_unique_callables.append(__gc_candidate)
__gc_payload = {"distinct_function_count": len(__gc_unique_callables)}
""",
            time_limit=3,
        )
        own_runs = own_payload.get("distinct_function_count", 0) >= 2
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
            "отчёт и итог выведены в точном заданном формате",
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
