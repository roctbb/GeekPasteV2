"""Autotests for the 2026 grade-8 course, chapters 1 through 4.

The module deliberately keeps large algorithm-separating inputs lazy: importing
the grade-8 registry must not allocate tens of megabytes for a task that is not
being checked.  Every random case uses a local, fixed seed so reruns are exactly
reproducible.
"""

from __future__ import annotations

import json
import random
import re

from environments.grade8_2026_common import (
    finish_criteria,
    finish_groups,
    run_case_group,
    run_cpp_harness_case,
    tokens_equal,
)


TASKS = {}
TASK_CASES = {}
HARNESS_CASES = {}
HARNESS_PROGRAM_CASES = {}

_DEFAULT_CAPTURE_LIMIT = 100 * 1024
_MAX_CAPTURE_LIMIT = 4 * 1024 * 1024


def strict_text_equal(actual, expected):
    """Compare text exactly, except for line-ending style/final newlines."""

    def clean(value):
        return str(value).replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")

    return clean(actual) == clean(expected)


def _selected_line_equal(actual, expected, index):
    # Task 2615 always requires exactly two output lines.  Looking only at the
    # selected line used to accept a correct prefix followed by arbitrary extra
    # output (or even by a prompt/debug dump).
    actual_lines = str(actual).replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return len(actual_lines) == 2 and actual_lines[index] == str(expected)


def first_line_equal(actual, expected):
    return _selected_line_equal(actual, expected, 0)


def second_line_equal(actual, expected):
    return _selected_line_equal(actual, expected, 1)


def _trusted_capture_limit(expected):
    expected_text = str(expected)
    size = len(expected_text.encode("utf-8"))
    if size <= _DEFAULT_CAPTURE_LIMIT:
        return None
    if size > _MAX_CAPTURE_LIMIT:
        raise ValueError("A hidden-test oracle exceeds the trusted 4 MiB capture ceiling")
    # Leave enough headroom for CRLF (accepted by the course-wide contract) and
    # small harmless formatting differences while retaining a finite trusted
    # limit.  Powers of two make the resulting limits easy to audit.
    required = size + max(64 * 1024, expected_text.count("\n") + 16)
    return min(_MAX_CAPTURE_LIMIT, 1 << required.bit_length())


def _case(input_data, expected, *, time_limit=1, comparator=None, key=None):
    result = {"input": input_data, "expected": expected, "time_limit": time_limit}
    capture_limit = _trusted_capture_limit(expected)
    if capture_limit is not None:
        result["capture_limit"] = capture_limit
    if comparator is not None:
        result["comparator"] = comparator
    if key is not None:
        result["key"] = key
    return result


def _materialize(groups):
    return [
        [item() if callable(item) else item for item in group]
        for group in groups
    ]


def materialize_task_groups(task_id):
    """Public test aid: return concrete case dictionaries for a task."""

    return _materialize(TASK_CASES[task_id])


def _source_check_passes(source_check, source_code):
    if source_check is None:
        return True
    try:
        return bool(source_check(source_code or ""))
    except (TypeError, ValueError, OverflowError, re.error):
        return False


def _add_program(task_id, maximum, groups, *, comparator=tokens_equal,
                 source_checks=None, descriptions=None):
    source_checks = source_checks or [None] * len(groups)
    if len(source_checks) != len(groups):
        raise ValueError("Every program group needs a source-check slot")
    if descriptions is not None and len(descriptions) != len(groups):
        raise ValueError("Every program group needs a feedback description")
    TASK_CASES[task_id] = groups

    def handler(runner, source_code):
        if any(check is not None for check in source_checks):
            criteria = []
            for index, (group, source_check) in enumerate(zip(groups, source_checks), start=1):
                source_ok = _source_check_passes(source_check, source_code)
                passed = source_ok and run_case_group(
                    runner, _materialize([group])[0], comparator
                )
                description = (
                    descriptions[index - 1]
                    if descriptions is not None
                    else "пройдена группа скрытых тестов {}".format(index)
                )
                criteria.append((passed, description))
            return finish_criteria(task_id, maximum, criteria)
        return finish_groups(
            task_id,
            maximum,
            runner,
            _materialize(groups),
            comparator,
        )

    TASKS[task_id] = (maximum, handler)


def _tag_harness(task_id, key, body):
    return "/* GP_CASE {}:{} */\n{}".format(task_id, key, body)


def _add_harness(task_id, maximum, groups, descriptions, *, program_groups=None,
                 program_comparator=tokens_equal, source_checks=None):
    if len(groups) != len(descriptions):
        raise ValueError("Every harness group needs a feedback description")
    if program_groups is not None and len(program_groups) != len(groups):
        raise ValueError("Program and harness groups must have the same shape")
    source_checks = source_checks or [None] * len(groups)
    if len(source_checks) != len(groups):
        raise ValueError("Every harness group needs a source-check slot")
    TASK_CASES[task_id] = groups
    HARNESS_PROGRAM_CASES[task_id] = program_groups or [[] for _ in groups]
    for group in groups:
        for item in group:
            if not callable(item):
                HARNESS_CASES[(task_id, item["key"])] = item

    def handler(runner, source_code):
        concrete_groups = _materialize(groups)
        concrete_program_groups = _materialize(HARNESS_PROGRAM_CASES[task_id])
        criteria = []
        for group, program_group, description, source_check in zip(
            concrete_groups, concrete_program_groups, descriptions, source_checks
        ):
            for item in group:
                HARNESS_CASES[(task_id, item["key"])] = item
            passed = (
                _source_check_passes(source_check, source_code)
                and run_case_group(runner, program_group, program_comparator)
            ) and all(
                run_cpp_harness_case(runner, source_code, item) for item in group
            )
            criteria.append((passed, description))
        return finish_criteria(task_id, maximum, criteria)

    TASKS[task_id] = (maximum, handler)


def _hcase(task_id, key, body, expected, *, input_data="", time_limit=3,
           comparator=tokens_equal):
    return {
        "key": key,
        "harness": _tag_harness(task_id, key, body),
        "input": input_data,
        "expected": expected,
        "time_limit": time_limit,
        "comparator": comparator,
    }


def _numbers(values):
    return " ".join(map(str, values))


def _array_input(values):
    return "{}\n{}\n".format(len(values), _numbers(values))


def _cpp_literal(value):
    return json.dumps(value, ensure_ascii=True)


def _cpp_views(source_code):
    """Return equal-length code-only text and the actual C++ comments."""

    source = str(source_code or "")
    code = list(source)
    comments = []
    index = 0
    state = "code"
    quote = None
    comment_start = None
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if character == "/" and following == "/":
                state = "line_comment"
                comment_start = index + 2
                code[index] = code[index + 1] = " "
                index += 2
                continue
            if character == "/" and following == "*":
                state = "block_comment"
                comment_start = index + 2
                code[index] = code[index + 1] = " "
                index += 2
                continue
            if character in {'"', "'"}:
                state = "literal"
                quote = character
                code[index] = " "
                index += 1
                continue
        elif state == "line_comment":
            if character == "\n":
                comments.append(source[comment_start:index])
                state = "code"
            else:
                code[index] = " "
            index += 1
            continue
        elif state == "block_comment":
            if character == "*" and following == "/":
                comments.append(source[comment_start:index])
                code[index] = code[index + 1] = " "
                state = "code"
                index += 2
                continue
            if character != "\n":
                code[index] = " "
            index += 1
            continue
        else:  # string or character literal
            code[index] = " "
            if character == "\\" and index + 1 < len(source):
                if source[index + 1] != "\n":
                    code[index + 1] = " "
                index += 2
                continue
            if character == quote:
                state = "code"
            index += 1
            continue
        index += 1

    if state == "line_comment":
        comments.append(source[comment_start:])
    elif state == "block_comment":
        comments.append(source[comment_start:])
    return "".join(code), "\n".join(comments)


def _cpp_function_body(source_code, function_name):
    code, _comments = _cpp_views(source_code)
    signature = re.compile(
        r"\b(?:int|void|bool|size_t|std\s*::\s*size_t)\s+"
        + re.escape(function_name)
        + r"\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{"
    )
    match = signature.search(code)
    if match is None:
        return None
    opening = code.find("{", match.start(), match.end())
    depth = 0
    for index in range(opening, len(code)):
        if code[index] == "{":
            depth += 1
        elif code[index] == "}":
            depth -= 1
            if depth == 0:
                return code[opening + 1:index]
    return None


_BANNED_MANUAL_STRING_CODE = re.compile(
    r"\b(?:strlen|strcpy|strcat)\s*\(", flags=re.IGNORECASE
)


def _manual_string_function(source_code, function_name):
    body = _cpp_function_body(source_code, function_name)
    return body is not None and _BANNED_MANUAL_STRING_CODE.search(body) is None


def _manual_string_len_source(source_code):
    code, _comments = _cpp_views(source_code)
    exact_signature = re.search(
        r"\bint\s+string_len\s*\(\s*const\s+char\s+str\s*\[\s*\]\s*\)\s*\{",
        code,
    )
    body = _cpp_function_body(source_code, "string_len")
    return (
        exact_signature is not None
        and body is not None
        and re.search(r"\bstrlen\s*\(", body) is None
    )


def _copy_source_requirement(source_code):
    return _manual_string_function(source_code, "string_copy")


def _overflow_explanation_present(source_code):
    required = (
        "// BUFFER_OVERFLOW: destination capacity is unknown; "
        "writing past it is undefined behavior."
    )
    return any(line.strip() == required for line in str(source_code or "").splitlines())


def _concat_source_requirement(source_code):
    return (
        _manual_string_function(source_code, "string_concat")
        and _overflow_explanation_present(source_code)
    )


def _transition_table_present(source_code):
    line_end = r"[ \t]*\r?\n[ \t]*"
    pattern = (
        r"/\*" + line_end
        + r"TRANSITIONS" + line_end
        + r"state;letter;semicolon;quote;end" + line_end
        + r"outside;append;emit_field;enter_quotes;emit_record" + line_end
        + r"inside;append;append;leave_quotes;invalid" + line_end
        + r"\*/"
    )
    return re.search(pattern, str(source_code or "")) is not None


def _benchmark_report_present(source_code):
    text = str(source_code or "")
    benchmark = re.search(
        r"(?m)^\s*// BENCHMARK n=1000000 counting_ms=(\d{1,9}) quicksort_ms=(\d{1,9})\s*$",
        text,
    )
    verified = re.search(r"(?m)^\s*// VERIFIED_EQUAL: yes\s*$", text)
    if benchmark is None or verified is None:
        return False
    counting_time, quick_time = map(int, benchmark.groups())
    return 0 < counting_time < quick_time


def _separate_two_key_comparator(source_code):
    code, _comments = _cpp_views(source_code)
    exact_signature = re.search(
        r"\bbool\s+comes_before\s*\(\s*long\s+long\s+number_a\s*,\s*"
        r"long\s+long\s+score_a\s*,\s*long\s+long\s+number_b\s*,\s*"
        r"long\s+long\s+score_b\s*\)\s*\{",
        code,
    )
    if exact_signature is None:
        return False
    comparator_body = _cpp_function_body(source_code, "comes_before")
    main_body = _cpp_function_body(source_code, "main")
    if comparator_body is None or main_body is None:
        return False
    all_parameters_used = all(
        re.search(r"\b" + name + r"\b", comparator_body)
        for name in ("number_a", "score_a", "number_b", "score_b")
    )
    return (
        all_parameters_used
        and re.search(r"[<>]", comparator_body) is not None
        and re.search(r"\bcomes_before\s*\(", main_body) is not None
    )


_NAND_LEVELS = ("Nand", "Invert", "And", "Or", "Xor")
_NANDGAME_MISSIONS = {
    "Nand": "RELAY_NAND",
    "Invert": "INV",
    "And": "AND",
    "Or": "OR",
    "Xor": "XOR",
}
_NAND_ALLOWED_COMPONENTS = {
    "Nand": {"RELAY-ON", "RELAY-OFF"},
    # These are the exact persistent node keys used by the current NandGame
    # export (the labels shown in the toolbox are lower-case, but the JSON is
    # not).  Accepting the labels made the checker incompatible with a real
    # Settings -> Export snapshot.
    "Invert": {"NAND"},
    "And": {"NAND", "INV"},
    "Or": {"NAND", "INV", "AND"},
    "Xor": {"NAND", "INV", "AND", "OR"},
}
_NAND_MIN_COMPONENTS = {"Nand": 2, "Invert": 1, "And": 2, "Or": 3, "Xor": 3}
_NAND_NODE_ARITY = {"NAND": 2, "INV": 1, "AND": 2, "OR": 2}


def _json_export(source_code):
    text = (source_code or "").strip()
    # The published contract accepts exactly one raw JSON object: no Markdown
    # fence, explanation, comment, or other text before or after the export.
    if not text.startswith("{"):
        return None
    try:
        value = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def _valid_nandgame_diagram(diagram, level, component_costs):
    if not isinstance(diagram, dict):
        return None
    nodes = diagram.get("nodes")
    connections = diagram.get("connections")
    if not isinstance(nodes, list) or not isinstance(connections, list):
        return None
    if len(nodes) < _NAND_MIN_COMPONENTS[level] or not connections:
        return None
    allowed = _NAND_ALLOWED_COMPONENTS[level]
    identifiers = set()
    nand_count = 0
    for node in nodes:
        if not isinstance(node, dict):
            return None
        node_type = node.get("type")
        identifier = node.get("id")
        if node_type not in allowed or not isinstance(identifier, str) or not identifier.isdigit():
            return None
        if identifier in identifiers:
            return None
        if not isinstance(node.get("x"), (int, float)) or not isinstance(node.get("y"), (int, float)):
            return None
        identifiers.add(identifier)
        if node_type == "NAND":
            nand_count += 1
        elif node_type in {"INV", "AND", "OR"}:
            dependency = {"INV": "Invert", "AND": "And", "OR": "Or"}[node_type]
            if dependency not in component_costs:
                return None
            nand_count += component_costs[dependency]
    has_output = False
    referenced_nodes = set()
    for connection in connections:
        if not isinstance(connection, dict):
            return None
        source = connection.get("source")
        target = connection.get("target")
        if not isinstance(source, dict) or not isinstance(target, dict):
            return None
        for endpoint, permitted_special in ((source, "input"), (target, "output")):
            node_id = endpoint.get("nodeId")
            connector_id = endpoint.get("connectorId")
            if not isinstance(node_id, str) or not isinstance(connector_id, str):
                return None
            if not connector_id.isdigit():
                return None
            if node_id != permitted_special and node_id not in identifiers:
                return None
            if node_id in identifiers:
                referenced_nodes.add(node_id)
        has_output = has_output or target.get("nodeId") == "output"
    if not has_output or referenced_nodes != identifiers:
        return None
    if level != "Nand" and not _nandgame_diagram_matches_level(diagram, level):
        return None
    return nand_count


def _nandgame_diagram_matches_level(diagram, level):
    nodes = {node["id"]: node for node in diagram["nodes"]}
    incoming = {}
    for connection in diagram["connections"]:
        source = connection["source"]
        target = connection["target"]
        target_key = (target["nodeId"], target["connectorId"])
        if target_key in incoming:
            return False
        incoming[target_key] = source

    if level == "Invert":
        truth = [((False,), True), ((True,), False)]
    elif level == "And":
        truth = [
            ((False, False), False), ((False, True), False),
            ((True, False), False), ((True, True), True),
        ]
    elif level == "Or":
        truth = [
            ((False, False), False), ((False, True), True),
            ((True, False), True), ((True, True), True),
        ]
    else:
        truth = [
            ((False, False), False), ((False, True), True),
            ((True, False), True), ((True, True), False),
        ]

    def evaluate(external_inputs):
        outputs = {}

        def source_value(endpoint):
            node_id = endpoint["nodeId"]
            connector = int(endpoint["connectorId"])
            if node_id == "input":
                if not 0 <= connector < len(external_inputs):
                    return None
                return external_inputs[connector]
            if connector != 0 or node_id not in outputs:
                return None
            return outputs[node_id]

        pending = set(nodes)
        while pending:
            progressed = False
            for node_id in list(pending):
                node_type = nodes[node_id]["type"]
                arguments = []
                for connector in range(_NAND_NODE_ARITY[node_type]):
                    endpoint = incoming.get((node_id, str(connector)))
                    if endpoint is None:
                        return None
                    value = source_value(endpoint)
                    if value is None:
                        break
                    arguments.append(value)
                else:
                    if node_type == "NAND":
                        result = not (arguments[0] and arguments[1])
                    elif node_type == "INV":
                        result = not arguments[0]
                    elif node_type == "AND":
                        result = arguments[0] and arguments[1]
                    else:
                        result = arguments[0] or arguments[1]
                    outputs[node_id] = result
                    pending.remove(node_id)
                    progressed = True
            if not progressed:
                return None
        output_endpoint = incoming.get(("output", "0"))
        return None if output_endpoint is None else source_value(output_endpoint)

    return all(evaluate(inputs) is expected for inputs, expected in truth)


def _completed_nand_levels(export):
    # The settings page exports one *flat* snapshot of NandGame localStorage.
    # Accepting nested arbitrary dictionaries made it possible to submit a
    # hand-written {"Xor": {"anything": 1}} instead of a game export.
    activated = export.get("NandGame:Levels") if isinstance(export, dict) else None
    if not isinstance(activated, list) or not all(isinstance(item, str) for item in activated):
        return set(), {}
    found = set()
    component_costs = {}
    for level in _NAND_LEVELS:
        mission = _NANDGAME_MISSIONS[level]
        if mission not in activated:
            continue
        key = "NandGame:Levels:" + mission
        nand_count = _valid_nandgame_diagram(export.get(key), level, component_costs)
        if nand_count is None:
            continue
        found.add(level)
        component_costs[level] = nand_count
    return found, component_costs


def _nand_handler(_runner, source_code):
    export = _json_export(source_code)
    levels, _component_costs = _completed_nand_levels(export) if export is not None else (set(), {})
    return finish_criteria(
        2570,
        15,
        [
            ({"Nand", "Invert"} <= levels, "в экспорте пройдены Nand и Invert"),
            ({"And", "Or"} <= levels, "в экспорте пройдены And и Or"),
            ({"Xor"} <= levels, "в экспорте пройден Xor"),
        ],
    )


TASKS[2570] = (15, _nand_handler)


# Remaining registrations are grouped by course chapter below.


# Chapter 2: procedural C++ -------------------------------------------------


def _swap_harness(a, b, key):
    return _hcase(
        2602,
        key,
        """
#include <iostream>
int main() {
    int a = %d, b = %d;
    swap_values(a, b);
    std::cout << a << ' ' << b << '\\n';
}
""" % (a, b),
        "{} {}\n".format(b, a),
    )


_add_harness(
    2602,
    5,
    [[
        _swap_harness(1, 2, "different"),
        _swap_harness(5, 5, "equal"),
        _swap_harness(-1000000000, 1000000000, "bounds"),
    ]],
    ["функция swap_values с параметрами-ссылками действительно меняет значения"],
    program_groups=[[
        _case("1 2\n", "2 1\n"),
        _case("5 5\n", "5 5\n"),
        _case("-1000000000 1000000000\n", "1000000000 -1000000000\n"),
    ]],
)


def _minmax_harness(values, key):
    a, b, c = values
    return _hcase(
        2603,
        key,
        """
#include <iostream>
int main() {
    int lo = 123456789, hi = -123456789;
    min_and_max(%d, %d, %d, lo, hi);
    std::cout << lo << ' ' << hi << '\\n';
}
""" % (a, b, c),
        "{} {}\n".format(min(values), max(values)),
    )


_add_harness(
    2603,
    5,
    [[
        _minmax_harness((1, 2, 3), "ascending"),
        _minmax_harness((3, 2, 1), "descending"),
        _minmax_harness((4, 4, 4), "equal"),
        _minmax_harness((0, -1000000000, 1000000000), "bounds"),
    ]],
    ["min_and_max возвращает оба результата через выходные параметры"],
    program_groups=[[
        _case("7 2 9\n", "2 9\n"),
        _case("4 4 4\n", "4 4\n"),
        _case("0 -1000000000 1000000000\n", "-1000000000 1000000000\n"),
    ]],
)


def _symmetric_harness(values, key):
    initializer = _numbers(values)
    return _hcase(
        2610,
        key,
        """
#include <iostream>
int main() {
    const int a[] = {%s};
    std::cout << (is_symmetric(a, %d) ? "YES" : "NO") << '\\n';
}
""" % (initializer.replace(" ", ", "), len(values)),
        "{}\n".format("YES" if values == values[::-1] else "NO"),
        comparator=strict_text_equal,
    )


_add_harness(
    2610,
    5,
    [[
        _symmetric_harness([7], "one"),
        _symmetric_harness([1, 2, 3, 2, 1], "odd"),
        _symmetric_harness([1, 2, 2, 1], "even"),
        _symmetric_harness([1, 2, 2, 3], "not_even"),
        _symmetric_harness([1, 9, 3, 2, 1], "late_difference"),
    ]],
    ["is_symmetric корректно сравнивает элементы с двух концов"],
    program_groups=[[
        _case(_array_input([1, 2, 3, 2, 1]), "YES\n"),
        _case(_array_input([1, 2, 2, 3]), "NO\n"),
    ]],
    program_comparator=strict_text_equal,
)


def _strlen_harness(text, key):
    return _hcase(
        2614,
        key,
        """
#include <iostream>
int main() {
    const char value[] = %s;
    std::cout << string_len(value) << '\\n';
}
""" % _cpp_literal(text),
        "{}\n".format(len(text)),
    )


_add_harness(
    2614,
    5,
    [[
        _strlen_harness("", "empty"),
        _strlen_harness("a", "one"),
        _strlen_harness("Hello", "hello"),
        _strlen_harness(" a b ", "spaces"),
        _strlen_harness("x" * 200, "max"),
    ]],
    ["string_len считает символы до нулевого терминатора, включая пробелы"],
    program_groups=[[
        _case("Hello\n", "5\n"),
        _case("\n", "0\n"),
        _case(" a b \n", "5\n"),
    ]],
    source_checks=[_manual_string_len_source],
)


def _copy_harness(first, second, key, operation):
    if operation == "copy":
        call = "string_copy(destination, source);"
        expected = first
        initial = "sentinel"
    else:
        call = "string_concat(destination, source);"
        expected = first + second
        initial = first
    return _hcase(
        2615,
        key,
        """
#include <iostream>
#include <cstring>
int main() {
    char destination[512] = %s;
    const char source[] = %s;
    %s
    std::cout << destination << '\\n';
}
""" % (_cpp_literal(initial), _cpp_literal(first if operation == "copy" else second), call),
        expected + "\n",
        comparator=strict_text_equal,
    )


_add_harness(
    2615,
    10,
    [
        [
            _copy_harness("Hip", "", "copy_normal", "copy"),
            _copy_harness("", "", "copy_empty", "copy"),
            _copy_harness("to be ", "", "copy_spaces", "copy"),
            _copy_harness("x" * 200, "", "copy_max", "copy"),
        ],
        [
            _copy_harness("Hip", "Hop", "concat_normal", "concat"),
            _copy_harness("", "abc", "concat_empty_left", "concat"),
            _copy_harness("abc", "", "concat_empty_right", "concat"),
            _copy_harness("a" * 200, "b" * 200, "concat_max", "concat"),
        ],
    ],
    [
        "string_copy копирует строку вместе с нулевым терминатором",
        "string_concat дописывает вторую строку, сохраняя первую",
    ],
    program_groups=[
        [
            _case("Hip\nHop\n", "Hip", comparator=first_line_equal),
            _case("\nabc\n", "", comparator=first_line_equal),
        ],
        [
            _case("Hip\nHop\n", "HipHop", comparator=second_line_equal),
            _case("abc\n\n", "abc", comparator=second_line_equal),
            _case("\nabc\n", "abc", comparator=second_line_equal),
        ],
    ],
    source_checks=[_copy_source_requirement, _concat_source_requirement],
)


def _compare_harness(first, second, key):
    expected = (first > second) - (first < second)
    return _hcase(
        2616,
        key,
        """
#include <iostream>
int main() {
    const char first[] = %s;
    const char second[] = %s;
    std::cout << string_compare(first, second) << '\\n';
}
""" % (_cpp_literal(first), _cpp_literal(second)),
        "{}\n".format(expected),
    )


_add_harness(
    2616,
    5,
    [[
        _compare_harness("cat", "cat", "equal"),
        _compare_harness("cat", "cats", "prefix_short"),
        _compare_harness("cats", "cat", "prefix_long"),
        _compare_harness("dog", "cat", "greater"),
        _compare_harness("Cat", "cat", "case"),
        _compare_harness("", "a", "empty"),
    ]],
    ["string_compare возвращает нормализованный результат -1, 0 или 1"],
    program_groups=[[
        _case("cat\ncat\n", "0\n"),
        _case("cat\ncats\n", "-1\n"),
        _case("Cat\ncat\n", "-1\n"),
    ]],
)


def _find_harness(haystack, needle, key):
    expected = haystack.find(needle)
    return _hcase(
        2617,
        key,
        """
#include <iostream>
int main() {
    const char haystack[] = %s;
    const char needle[] = %s;
    std::cout << string_find(haystack, needle) << '\\n';
}
""" % (_cpp_literal(haystack), _cpp_literal(needle)),
        "{}\n".format(expected),
    )


_add_harness(
    2617,
    10,
    [
        [
            _find_harness("ababc", "abc", "fallback"),
            _find_harness("cat", "dog", "absent"),
            _find_harness("middle", "mid", "start"),
        ],
        [
            _find_harness("aaaa", "aaa", "overlap_first"),
            _find_harness("xxabc", "abc", "end"),
            _find_harness("abc", "", "empty_needle"),
            _find_harness("", "", "both_empty"),
            _find_harness("short", "long needle", "needle_longer"),
        ],
    ],
    [
        "string_find находит подстроку и возвращает -1 при отсутствии",
        "верно обработаны первое вхождение, конец строки и пустая игла",
    ],
    program_groups=[
        [
            _case("ababc\nabc\n", "2\n"),
            _case("cat\ndog\n", "-1\n"),
        ],
        [
            _case("aaaa\naaa\n", "0\n"),
            _case("abc\n\n", "0\n"),
        ],
    ],
)


# Chapter 3: algorithms and linear techniques ------------------------------


_COMPLEXITY_ANSWER = "n n2 logn 1 nlogn"


def _structured_text_answer(source_code):
    text = str(source_code or "").strip()
    fence = re.fullmatch(r"```(?:text)?\s*\n(.*?)\n```", text, flags=re.IGNORECASE | re.DOTALL)
    if fence is not None:
        text = fence.group(1).strip()
    if "\n" in text or "\r" in text:
        return None
    tokens = text.split()
    allowed = {"1", "logn", "n", "nlogn", "n2"}
    if len(tokens) != 5 or any(token not in allowed for token in tokens):
        return None
    return " ".join(tokens)


def _complexity_text_handler(_runner, source_code):
    return finish_criteria(
        2621,
        5,
        [
            (
                _structured_text_answer(source_code) == _COMPLEXITY_ANSWER,
                "прислана одна строка из пяти верных обозначений сложности",
            )
        ],
    )


TASK_CASES[2621] = [[_case("", _COMPLEXITY_ANSWER + "\n")]]
TASKS[2621] = (5, _complexity_text_handler)


def _power_harness(base, exponent, key, *, time_limit=3):
    expected = pow(base, exponent)
    return _hcase(
        2626,
        key,
        """
#include <iostream>
int main() {
    std::cout << power(%dLL, %d) << '\\n';
}
""" % (base, exponent),
        "{}\n".format(expected),
        time_limit=time_limit,
    )


_add_harness(
    2626,
    5,
    [[
        _power_harness(7, 0, "zero"),
        _power_harness(2, 10, "even"),
        _power_harness(-3, 5, "negative_odd"),
        _power_harness(-3, 6, "negative_even"),
        _power_harness(1, 1000000000, "large_one", time_limit=2),
        _power_harness(-1, 999999999, "large_minus_one", time_limit=2),
        _power_harness(0, 1000000000, "large_zero", time_limit=2),
    ]],
    ["power считает степень за логарифмическое число шагов"],
    program_groups=[[
        _case("2 10\n", "1024\n"),
        _case("7 0\n", "1\n"),
        _case("-1 999999999\n", "-1\n", time_limit=2),
        _case("1 1000000000\n", "1\n", time_limit=2),
    ]],
)


def _parse_journal_line(line):
    fields = []
    current = []
    quoted = False
    for character in line:
        if character == '"':
            quoted = not quoted
        elif character == ";" and not quoted:
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    fields.append("".join(current))
    return fields


def _journal_batch(lines, *, time_limit=1):
    output = []
    for line in lines:
        fields = _parse_journal_line(line)
        output.append("{}:{}".format(len(fields), "/".join(fields)))
    return _case(
        "\n".join(lines) + "\n",
        "\n".join(output) + "\n",
        time_limit=time_limit,
    )


def _journal_stress():
    lines = []
    for index in range(10000):
        if index % 3 == 0:
            lines.append('"surname;{}";8A;comment'.format(index))
        elif index % 3 == 1:
            lines.append("name{};;".format(index))
        else:
            lines.append('"";8B;ok')
    return _journal_batch(lines, time_limit=5)


_add_program(
    2638,
    15,
    [
        [],
        [
            _journal_batch(["Petrov;9A;good", "Sidorova;9B;"]),
            _journal_batch(["a;;b", ";a;"]),
        ],
        [
            _journal_batch(['"Ivanov; starosta";9A;the best']),
            _journal_batch(['"a;b;c"', '""', 'a;"b;c";d']),
            _journal_stress,
        ],
    ],
    comparator=strict_text_equal,
    source_checks=[_transition_table_present, None, None],
    descriptions=[
        "в комментарии приложена полная таблица переходов автомата",
        "верно разбираются строки без кавычек и пустые поля",
        "верно разбираются поля в кавычках, включая большой вход",
    ],
)


# Chapter 4: searching and sorting -----------------------------------------


def _census_case(values, *, time_limit=1):
    return _case(_array_input(values), _numbers(sorted(values)) + "\n", time_limit=time_limit)


def _census_stress():
    rng = random.Random(2656)
    values = [rng.randint(0, 120) for _ in range(350000)]
    return _census_case(values, time_limit=6)


_add_program(
    2656,
    10,
    [
        [
            _census_case([30, 15, 30, 0, 120, 15]),
            _census_case([42] * 5),
            _census_case([0, 120, 0, 120]),
            _census_stress,
        ],
        [],
    ],
    source_checks=[None, _benchmark_report_present],
    descriptions=[
        "сортировка подсчётом выдаёт верный результат, включая большой вход",
        "в комментариях приложен сверенный замер с быстрой сортировкой",
    ],
)


def _protocol_case(records, *, time_limit=1):
    ordered = sorted(records, key=lambda item: (-item[1], item[0]))
    expected = "\n".join("{} {}".format(*record) for record in ordered) + "\n"
    input_data = "{}\n{}\n".format(
        len(records),
        "\n".join("{} {}".format(*record) for record in records),
    )
    return _case(input_data, expected, time_limit=time_limit)


def _protocol_stress():
    records = [(50000 - index, index % 11) for index in range(50000)]
    return _protocol_case(records, time_limit=5)


_add_program(
    2658,
    10,
    [
        [
            _protocol_case([(101, 80), (102, 95), (103, 80), (104, 60)]),
            _protocol_case([(9, 50), (3, 50), (7, 50), (1, 50)]),
        ],
        [
            _protocol_case([(5, 0), (4, 100), (3, 100), (2, 50), (1, 50)]),
            _protocol_stress,
        ],
    ],
    comparator=strict_text_equal,
    source_checks=[None, _separate_two_key_comparator],
    descriptions=[
        "протокол сортируется по убыванию балла и возрастанию номера",
        "отдельная функция comes_before с двумя ключами вызывается из main",
    ],
)


EXPECTED_TASK_IDS = frozenset({
    2570, 2602, 2603, 2610, 2614, 2615, 2616, 2617,
    2621, 2626, 2638, 2656, 2658,
})

if set(TASKS) != EXPECTED_TASK_IDS:
    missing = sorted(EXPECTED_TASK_IDS - set(TASKS))
    extra = sorted(set(TASKS) - EXPECTED_TASK_IDS)
    raise RuntimeError("grade8 chapter 1-4 registry mismatch: missing={}, extra={}".format(
        missing, extra
    ))
