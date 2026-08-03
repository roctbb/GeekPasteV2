"""Autotests for the 2026 grade-8 course, chapters 1 through 4.

The module deliberately keeps large algorithm-separating inputs lazy: importing
the grade-8 registry must not allocate tens of megabytes for a task that is not
being checked.  Every random case uses a local, fixed seed so reruns are exactly
reproducible.
"""

from __future__ import annotations

from collections import deque
import bisect
import json
import math
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


def _query_input(values, queries):
    return "{}\n{}\n{}\n{}\n".format(
        len(values),
        _numbers(values),
        len(queries),
        "\n".join(map(str, queries)),
    )


def _range_query_input(values, queries):
    return "{}\n{}\n{}\n{}\n".format(
        len(values),
        _numbers(values),
        len(queries),
        "\n".join("{} {}".format(left, right) for left, right in queries),
    )


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


def _magic_answer(matrix):
    expected = sum(matrix[0])
    for index, row in enumerate(matrix, start=1):
        value = sum(row)
        if value != expected:
            return "NO: row {} (sum {}, expected {})\n".format(
                index, value, expected
            )
    size = len(matrix)
    for column in range(size):
        value = sum(matrix[row][column] for row in range(size))
        if value != expected:
            return "NO: col {} (sum {}, expected {})\n".format(
                column + 1, value, expected
            )
    value = sum(matrix[index][index] for index in range(size))
    if value != expected:
        return "NO: diag 1 (sum {}, expected {})\n".format(value, expected)
    value = sum(matrix[index][size - 1 - index] for index in range(size))
    if value != expected:
        return "NO: diag 2 (sum {}, expected {})\n".format(value, expected)
    return "YES\n"


def _semantic_mismatch_equal(actual, expected):
    """Compare a NO diagnostic semantically where punctuation is unspecified."""

    pattern = re.compile(
        r"^\s*NO\s*:?\s*(row|col|diag)\s+(\d+)\s*"
        r"(?:\(|[,;:]?\s*)sum\s*[:=]?\s*(-?\d+)\s*[,;]?\s*"
        r"expected\s*[:=]?\s*(-?\d+)\s*\)?\s*$",
        flags=re.IGNORECASE,
    )
    actual_match = pattern.match(str(actual).replace("\r", "").strip())
    expected_match = pattern.match(str(expected).replace("\r", "").strip())
    if actual_match is None or expected_match is None:
        return False
    actual_groups = actual_match.groups()
    expected_groups = expected_match.groups()
    return (
        actual_groups[0].casefold() == expected_groups[0].casefold()
        and actual_groups[1:] == expected_groups[1:]
    )


def _matrix_input(matrix):
    return "{}\n{}\n".format(
        len(matrix),
        "\n".join(_numbers(row) for row in matrix),
    )


def _mine_counts(grid):
    rows, columns = len(grid), len(grid[0])
    result = []
    for row in range(rows):
        line = []
        for column in range(columns):
            if grid[row][column] == "*":
                line.append("*")
                continue
            count = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    nr, nc = row + dr, column + dc
                    if (
                        (dr or dc)
                        and 0 <= nr < rows
                        and 0 <= nc < columns
                        and grid[nr][nc] == "*"
                    ):
                        count += 1
            line.append(str(count))
        result.append("".join(line))
    return result


def _caesar(text, shift):
    result = []
    for character in text:
        if "a" <= character <= "z":
            result.append(chr((ord(character) - 97 + shift) % 26 + 97))
        elif "A" <= character <= "Z":
            result.append(chr((ord(character) - 65 + shift) % 26 + 65))
        else:
            result.append(character)
    return "".join(result)


def _vigenere(text, key):
    result = []
    key_index = 0
    for character in text:
        if "a" <= character <= "z":
            shift = ord(key[key_index % len(key)]) - ord("a")
            result.append(chr((ord(character) - 97 + shift) % 26 + 97))
            key_index += 1
        else:
            result.append(character)
    return "".join(result)


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


def _json_export_and_explanations(source_code):
    text = (source_code or "").strip()
    decoder = json.JSONDecoder()
    # The published contract asks for the complete Export JSON first, without
    # a Markdown fence or any other prefix.  Keeping the boundary strict also
    # prevents an arbitrary prose preamble from being silently discarded.
    if not text.startswith("{"):
        return None, ""
    try:
        value, length = decoder.raw_decode(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, ""
    if not isinstance(value, dict):
        return None, ""
    tail = text[length:].strip()
    return value, tail


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


_NAND_EXPLANATION_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(Nand|Invert|And|Or|Xor)\s*[:\-—]\s*(.+?)\s*$",
    flags=re.IGNORECASE,
)
_NAND_SEMANTIC_PATTERNS = {
    "Nand": r"(?:\brelay\w*\b|реле|both\s+inputs|оба\s+вход|конъюнк|not\s+and|не\s+и)",
    "Invert": r"(?:\binvert\w*\b|\binvers\w*\b|инверс|отриц|\bnegat\w*\b|\bnot\b|\bне\b)",
    "And": r"(?:\bconjunction\b|конъюнк|double\s+inver|двойн|\band\b|\bи\b)",
    "Or": r"(?:\bdisjunction\b|дизъюнк|de\s+morgan|морган|\bor\b|\bили\b)",
    "Xor": r"(?:\bexclusive\b|исключ|\bdifferent\b|нерав|\bxor\b)",
}


def _nand_count_from_explanation(text):
    patterns = (
        r"\b(\d{1,6})\s*(?:nand|элемент(?:а|ов)?\s+nand)\b",
        r"\bnand(?:\s+gates?|\s+элемент(?:а|ов)?)?\s*[:=\-—]?\s*(\d{1,6})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group(1))
    return None


def _meaningful_nand_explanations(text, component_costs):
    explanations = {}
    canonical = {level.casefold(): level for level in _NAND_LEVELS}
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    # The task explicitly requires exactly five non-empty labelled lines after
    # the JSON.  Do not ignore a sixth line or an unrecognised attachment.
    if len(lines) != len(_NAND_LEVELS):
        return False
    for line in lines:
        match = _NAND_EXPLANATION_RE.match(line)
        if match is None:
            return False
        level = canonical[match.group(1).casefold()]
        if level in explanations:
            return False
        explanations[level] = match.group(2).strip()
    if set(explanations) != set(_NAND_LEVELS):
        return False
    for level, explanation in explanations.items():
        lowered = " " + explanation.casefold() + " "
        words = re.findall(r"[^\W\d_]+", lowered, flags=re.UNICODE)
        if len(explanation) < 18 or len(words) < 3:
            return False
        if re.search(_NAND_SEMANTIC_PATTERNS[level], lowered, flags=re.IGNORECASE) is None:
            return False
        stated_count = _nand_count_from_explanation(explanation)
        if stated_count != component_costs.get(level):
            return False
    return True


def _nand_handler(_runner, source_code):
    export, explanation_text = _json_export_and_explanations(source_code)
    levels, component_costs = (
        _completed_nand_levels(export) if export is not None else (set(), {})
    )
    explanations_ok = (
        set(_NAND_LEVELS) <= levels
        and _meaningful_nand_explanations(explanation_text, component_costs)
    )
    return finish_criteria(
        2570,
        15,
        [
            ({"Nand", "Invert"} <= levels, "в экспорте пройдены Nand и Invert"),
            ({"And", "Or"} <= levels, "в экспорте пройдены And и Or"),
            (
                {"Xor"} <= levels and explanations_ok,
                "в экспорте пройден Xor и приложены пять объяснений с верным числом NAND",
            ),
        ],
    )


TASKS[2570] = (15, _nand_handler)


# Remaining registrations are grouped by course chapter below.


# Chapter 2: procedural C++ -------------------------------------------------

_add_program(
    2593,
    5,
    [[_case(
        "",
        "A byte, a bit, a line of code,\n"
        "a compiler on a rainy road.\n"
        "It printed nothing at the start,\n"
        "and now it prints this work of art!\n",
    )]],
    comparator=strict_text_equal,
)


def _elapsed(seconds):
    return "{} h {} m {} s\n".format(
        seconds // 3600,
        seconds % 3600 // 60,
        seconds % 60,
    )


_add_program(
    2594,
    5,
    [[
        *[_case("{}\n".format(value), _elapsed(value)) for value in
          (0, 59, 60, 3599, 3600, 86399, 86400, 1000000000)],
    ]],
    comparator=strict_text_equal,
)


def _cpp_division(a, b):
    quotient = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        quotient = -quotient
    remainder = a - quotient * b
    return "{} / {} = {} (rem {})\n".format(a, b, quotient, remainder)


_division_pairs = (
    (7, 2), (-7, 2), (7, -2), (-7, -2), (0, -3),
    (10000, 1), (-10000, 37), (9999, -10000),
)
_add_program(
    2595,
    5,
    [[
        *[
            _case("{} {}\n".format(a, b), _cpp_division(a, b))
            for a, b in _division_pairs
        ],
    ]],
    comparator=strict_text_equal,
)


_add_program(
    2596,
    5,
    [[
        *[
            _case(
                "{} {}\n".format(x, y),
                "{}\n".format("white" if (x + y) % 2 == 0 else "black"),
            )
            for x, y in ((1, 1), (1, 8), (8, 1), (8, 8),
                         (2, 1), (2, 2), (3, 4), (4, 3))
        ],
    ]],
    comparator=strict_text_equal,
)


def _fib(number):
    left = right = 1
    for _ in range(3, number + 1):
        left, right = right, left + right
    return left if number == 1 else right


_add_program(
    2597,
    5,
    [[
        *[
            _case("{}\n".format(number), "{}\n".format(_fib(number)))
            for number in (1, 2, 3, 6, 20, 46, 47, 50, 89, 90)
        ],
    ]],
)


def _dog_field(rows, columns):
    return "\n".join(
        "".join("%" if (row + column) % 2 == 0 else "@"
                for column in range(columns))
        for row in range(rows)
    ) + "\n"


_add_program(
    2598,
    5,
    [[
        *[
            _case("{} {}\n".format(rows, columns), _dog_field(rows, columns))
            for rows, columns in ((1, 1), (1, 8), (2, 2), (3, 4), (4, 5), (100, 100))
        ],
    ]],
    comparator=strict_text_equal,
)


def _emergency(number):
    total = number * (number + 1) // 2
    average = str((number + 1) // 2) if number % 2 else "{}.5".format(number // 2)
    return "Sum: {}\nAverage: {}\n".format(total, average)


_add_program(
    2599,
    10,
    [
        [_case("{}\n".format(number), _emergency(number)) for number in (1, 3, 5, 9999)],
        [_case("{}\n".format(number), _emergency(number)) for number in (2, 4, 9998, 10000)],
    ],
    comparator=strict_text_equal,
)


def _digit_answer(number):
    text = str(number)
    return "{}\n{}\n".format(sum(map(int, text)), len(text))


_add_program(
    2600,
    5,
    [[
        *[
            _case("{}\n".format(number), _digit_answer(number))
            for number in (0, 7, 10, 1005, 999999999, 1000000000)
        ],
    ]],
    comparator=strict_text_equal,
)


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


def _perfect_expected(limit):
    known = (6, 28, 496, 8128)
    return " ".join(str(value) for value in known if value <= limit) + "\n"


_add_program(
    2604,
    10,
    [
        [_case("{}\n".format(limit), _perfect_expected(limit))
         for limit in (1, 5, 6, 27, 28, 495, 496, 8128)],
        [_case("100000\n", _perfect_expected(100000), time_limit=5)],
    ],
)


_add_program(
    2605,
    5,
    [[
        _case(
            _numbers(values) + "\n",
            _numbers(reversed(values)) + "\n",
        )
        for values in (
            list(range(1, 11)),
            [0] * 10,
            [0, 10000, 3, 3, 7, 1, 9, 2, 8, 5],
        )
    ]],
)


def _warming_answer(values):
    answer = []
    for index, value in enumerate(values):
        wait = 0
        for later in range(index + 1, len(values)):
            if values[later] > value:
                wait = later - index
                break
        answer.append(wait)
    return _numbers(answer) + "\n"


def _warming_random_case():
    rng = random.Random(2606)
    values = [rng.randint(-100, 100) for _ in range(700)]
    return _case(_array_input(values), _warming_answer(values), time_limit=2)


_add_program(
    2606,
    5,
    [[
        _case(_array_input([-2, 0, 3, 3, 5, 4, 8]), "1 1 2 1 2 1 0\n"),
        _case(_array_input([5, 5, 5]), "0 0 0\n"),
        _case(_array_input([5, 4, 3, 2, 1]), "0 0 0 0 0\n"),
        _case(_array_input([1, 2, 3, 4, 5]), "1 1 1 1 0\n"),
        _warming_random_case,
    ]],
)


def _rotation_case(values, *, time_limit=1):
    rotated = values[-1:] + values[:-1]
    return _case(_array_input(values), _numbers(rotated) + "\n", time_limit=time_limit)


def _rotation_stress():
    values = list(range(100000))
    return _rotation_case(values, time_limit=3)


_add_program(
    2607,
    5,
    [[
        _rotation_case([5]),
        _rotation_case([1, 2]),
        _rotation_case([3, 7, 1, 9, 4]),
        _rotation_case([-1, -1, 0, 9]),
        _rotation_stress,
    ]],
)


def _above_average_case(values, *, time_limit=1):
    total = sum(values)
    answer = sum(value * len(values) > total for value in values)
    return _case(_array_input(values), "{}\n".format(answer), time_limit=time_limit)


def _above_average_stress():
    values = [-1000000000] * 50000 + [1000000000] * 50000
    values[-1] -= 1
    return _above_average_case(values, time_limit=3)


_add_program(
    2608,
    5,
    [[
        _above_average_case([2, 4, 6, 8]),
        _above_average_case([5, 5, 5]),
        _above_average_case([1, 1, 1, 2]),
        _above_average_case([-10, -1, 0, 11]),
        _above_average_case([-2, -1]),
        _above_average_stress,
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


_add_program(
    2611,
    10,
    [
        [
            _case(_matrix_input([[7]]), "YES\n"),
            _case(_matrix_input([[2, 7, 6], [9, 5, 1], [4, 3, 8]]), "YES\n"),
            _case(_matrix_input([[2, 9, 6], [7, 5, 1], [4, 3, 8]]),
                  "NO: row 2 (sum 13, expected 17)\n"),
            _case(_matrix_input([[1, 2], [0, 3]]),
                  "NO: col 1 (sum 1, expected 3)\n",
                  comparator=_semantic_mismatch_equal),
        ],
        [
            _case(_matrix_input([[1, 2], [2, 1]]),
                  "NO: diag 1 (sum 2, expected 3)\n",
                  comparator=_semantic_mismatch_equal),
            _case(_matrix_input([[0, 0, 1], [0, 1, 0], [1, 0, 0]]),
                  "NO: diag 2 (sum 3, expected 1)\n",
                  comparator=_semantic_mismatch_equal),
        ],
    ],
    comparator=strict_text_equal,
)


def _mine_case(grid, *, time_limit=1):
    output = _mine_counts(grid)
    input_data = "{} {}\n{}\n".format(len(grid), len(grid[0]), "\n".join(grid))
    return _case(input_data, "\n".join(output) + "\n", time_limit=time_limit)


def _mine_random_case():
    rng = random.Random(2612)
    grid = [
        "".join("*" if rng.random() < 0.27 else "." for _ in range(47))
        for _ in range(39)
    ]
    return _mine_case(grid, time_limit=2)


_add_program(
    2612,
    10,
    [
        [
            _mine_case(["*...", "....", ".*.."]),
            _mine_case([".....", "..*..", "....."]),
        ],
        [
            _mine_case(["."]),
            _mine_case(["*"]),
            _mine_case(["*.*", "...", "*.*"]),
            _mine_random_case,
        ],
    ],
    comparator=strict_text_equal,
)


def _caesar_case(text, shift):
    return _case(
        "{}\n{}\n".format(text, shift),
        _caesar(text, shift) + "\n",
    )


_add_program(
    2613,
    10,
    [
        [
            _caesar_case("Attack at dawn!", 3),
            _caesar_case("Az 09!?", 0),
            _caesar_case("Mixed CASE, spaces 123.", 10),
        ],
        [
            _caesar_case("xyz XYZ", 3),
            _caesar_case("zZ aA", 25),
            _caesar_case("  leading and trailing  ", 7),
            _caesar_case("", 13),
        ],
    ],
    comparator=strict_text_equal,
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


def _vigenere_case(text, key):
    return _case(
        "{}\n{}\n".format(text, key),
        _vigenere(text, key) + "\n",
    )


_add_program(
    2619,
    10,
    [
        [
            _vigenere_case("attack", "key"),
            _vigenere_case("abc", "a"),
            _vigenere_case("zzzz", "bz"),
        ],
        [
            _vigenere_case("a b c", "key"),
            _vigenere_case("wait... what?!", "cipher"),
            _vigenere_case("", "key"),
            _vigenere_case("letters-and spaces", "z"),
        ],
    ],
    comparator=strict_text_equal,
)


# Chapter 3: algorithms and linear techniques ------------------------------

def _gcd_batch(pairs, *, time_limit=1):
    input_data = "\n".join("{} {}".format(a, b) for a, b in pairs) + "\n"
    expected = "\n".join(str(math.gcd(a, b)) for a, b in pairs) + "\n"
    return _case(input_data, expected, time_limit=time_limit)


def _gcd_stress():
    rng = random.Random(2620)
    pairs = [
        (9000000000000000000, 1),
        (7540113804746346429, 4660046610375530309),
        (9000000000000000000, 4500000000000000000),
    ]
    for _ in range(9997):
        factor = rng.randint(1, 1000000)
        left = factor * rng.randint(1, 9000000000000)
        right = factor * rng.randint(1, 9000000000000)
        pairs.append((left, right))
    return _gcd_batch(pairs, time_limit=5)


_add_program(
    2620,
    10,
    [
        [
            _gcd_batch([(12, 18), (17, 5), (100, 100), (7, 49), (49, 7)]),
            _gcd_batch([(1, 1), (9999999967, 9999999967), (270, 192)]),
        ],
        [_gcd_stress],
    ],
)


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


def _stairs(number):
    values = [1, 1, 2]
    for index in range(3, number + 1):
        values.append(values[index - 1] + values[index - 2] + values[index - 3])
    return values[number]


_add_program(
    2624,
    10,
    [
        [_case("{}\n".format(number), "{}\n".format(_stairs(number)))
         for number in (1, 2, 3, 4, 10, 20, 35, 36)],
        [_case("{}\n".format(number), "{}\n".format(_stairs(number)), time_limit=3)
         for number in (37, 64, 69, 70)],
    ],
)


def _sweeper_answer(grid, click):
    row, column = click[0] - 1, click[1] - 1
    if grid[row][column] == "*":
        return "BOOM\n"
    counts = _mine_counts(grid)
    rows, columns = len(grid), len(grid[0])
    opened = {(row, column)}
    queue = deque([(row, column)]) if counts[row][column] == "0" else deque()
    while queue:
        current_row, current_column = queue.popleft()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = current_row + dr, current_column + dc
                if not (0 <= nr < rows and 0 <= nc < columns):
                    continue
                if grid[nr][nc] == "*" or (nr, nc) in opened:
                    continue
                opened.add((nr, nc))
                if counts[nr][nc] == "0":
                    queue.append((nr, nc))
    output = []
    for current_row in range(rows):
        output.append("".join(
            counts[current_row][current_column]
            if (current_row, current_column) in opened else "#"
            for current_column in range(columns)
        ))
    return "\n".join(output) + "\n"


def _sweeper_case(grid, click, *, time_limit=1):
    input_data = "{} {}\n{}\n{} {}\n".format(
        len(grid), len(grid[0]), "\n".join(grid), click[0], click[1]
    )
    return _case(input_data, _sweeper_answer(grid, click), time_limit=time_limit)


def _sweeper_stress():
    grid = ["." * 100 for _ in range(100)]
    return _sweeper_case(grid, (1, 1), time_limit=4)


_add_program(
    2625,
    10,
    [
        [
            _sweeper_case([".....", "...*.", ".....", "....."], (1, 1)),
            _sweeper_case(["*." , ".."], (2, 2)),
            _sweeper_case([".*", ".."], (1, 2)),
        ],
        [
            _sweeper_case(["."], (1, 1)),
            _sweeper_case(["*..", "...", "..."], (3, 3)),
            _sweeper_case([".*.", "...", ".*."], (2, 2)),
            _sweeper_stress,
        ],
    ],
    comparator=strict_text_equal,
)


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


def _hanoi_moves(number, source=1, target=3, spare=2):
    result = []

    def solve(size, start, finish, auxiliary):
        if size == 0:
            return
        solve(size - 1, start, auxiliary, finish)
        result.append((start, finish))
        solve(size - 1, auxiliary, finish, start)

    solve(number, source, target, spare)
    return result


def _hanoi_case(number, *, time_limit=1):
    expected = "\n".join("{} {}".format(*move) for move in _hanoi_moves(number)) + "\n"
    return _case("{}\n".format(number), expected, time_limit=time_limit)


def _hanoi_max_case():
    return _hanoi_case(15, time_limit=5)


_add_program(
    2627,
    10,
    [
        [_hanoi_case(number) for number in (1, 2, 3, 5, 10)],
        [_hanoi_case(12, time_limit=3), _hanoi_max_case],
    ],
    comparator=strict_text_equal,
)


def _best_pair_case(values, *, time_limit=1):
    first, second = sorted(values, reverse=True)[:2]
    return _case(_array_input(values), "{}\n".format(first + second), time_limit=time_limit)


def _best_pair_stress():
    rng = random.Random(2629)
    values = [rng.randint(-1000000, 999990) for _ in range(150000)]
    values[-2:] = [1000000, 1000000]
    return _best_pair_case(values, time_limit=4)


_add_program(
    2629,
    5,
    [[
        _best_pair_case([3, 9, 1, 7]),
        _best_pair_case([-5, -8, -2]),
        _best_pair_case([7, 1, 7, -4, 2]),
        _best_pair_case([-1000000, 1000000]),
        _best_pair_stress,
    ]],
)


def _permutation_case(values, *, time_limit=1):
    expected = "YES\n" if sorted(values) == list(range(1, len(values) + 1)) else "NO\n"
    return _case(_array_input(values), expected, time_limit=time_limit)


def _permutation_stress(valid):
    def factory():
        rng = random.Random(2630 + int(valid))
        values = list(range(1, 150001))
        rng.shuffle(values)
        if not valid:
            values[-1] = values[0]
        return _permutation_case(values, time_limit=4)

    return factory


_add_program(
    2630,
    5,
    [[
        _permutation_case([1]),
        _permutation_case([2, 3, 1, 5, 4]),
        _permutation_case([1, 1, 3]),
        _permutation_case([7, 1]),
        _permutation_case([-1, 2, 3]),
        _permutation_stress(True),
        _permutation_stress(False),
    ]],
    comparator=strict_text_equal,
)


def _steps_query_case(values, queries, *, time_limit=1):
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + value)
    output = []
    for left, right in queries:
        total = prefix[right] - prefix[left - 1]
        output.append("{} {}".format(total, total // (right - left + 1)))
    return _case(
        _range_query_input(values, queries),
        "\n".join(output) + "\n",
        time_limit=time_limit,
    )


def _steps_stress():
    rng = random.Random(2631)
    values = [rng.randint(0, 1000) for _ in range(100000)]
    queries = []
    for index in range(25000):
        left = 1 + index % 1000
        right = len(values) - index % 1000
        queries.append((left, right))
    return _steps_query_case(values, queries, time_limit=5)


_add_program(
    2631,
    10,
    [
        [
            _steps_query_case([100, 0, 50, 200, 150], [(1, 5), (2, 3), (4, 4)]),
            _steps_query_case([1, 2, 2], [(1, 3), (1, 1), (2, 3)]),
        ],
        [_steps_stress],
    ],
)


def _frost_query_case(values, queries, *, time_limit=1):
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + (value < 0))
    expected = "\n".join(
        str(prefix[right] - prefix[left - 1]) for left, right in queries
    ) + "\n"
    return _case(_range_query_input(values, queries), expected, time_limit=time_limit)


def _frost_stress():
    values = [(-1 if index % 3 == 0 else 0 if index % 3 == 1 else 60)
              for index in range(180000)]
    queries = [(1 + index % 500, len(values) - index % 500) for index in range(25000)]
    return _frost_query_case(values, queries, time_limit=5)


_add_program(
    2632,
    10,
    [
        [
            _frost_query_case([-5, 3, -1, 0, -8, 2, -3], [(1, 7), (2, 4), (4, 4)]),
            _frost_query_case([0, -1, 1], [(1, 1), (1, 2), (2, 2)]),
            _frost_query_case([-60] * 10, [(1, 10), (5, 5)]),
        ],
        [_frost_stress],
    ],
)


def _ventilation_case(values, window, *, time_limit=1):
    current = sum(values[:window])
    best = current
    best_start = 0
    for index in range(window, len(values)):
        current += values[index] - values[index - window]
        if current > best:
            best = current
            best_start = index - window + 1
    total_minutes = 8 * 60 + best_start
    expected = "{:02d}:{:02d} {}\n".format(
        total_minutes // 60,
        total_minutes % 60,
        best // window,
    )
    input_data = "{} {}\n{}\n".format(len(values), window, _numbers(values))
    return _case(input_data, expected, time_limit=time_limit)


def _ventilation_stress():
    values = [10000] * 100000 + [0] * 100000
    return _ventilation_case(values, 100000, time_limit=5)


_add_program(
    2633,
    10,
    [
        [
            _ventilation_case([400, 400, 1200, 1200, 1200, 400], 3),
            _ventilation_case([5, 5, 1, 5, 5], 2),
            _ventilation_case([1, 9, 9, 2], 1),
        ],
        [
            _ventilation_case([1, 2, 4], 3),
            _ventilation_case([0] * 60 + [1] + [0] * 4, 1),
            _ventilation_stress,
        ],
    ],
    comparator=strict_text_equal,
)


def _series_case(values, limit, *, time_limit=1):
    left = 0
    total = 0
    best_start = -1
    best_length = 0
    for right, value in enumerate(values):
        total += value
        while left <= right and total > limit:
            total -= values[left]
            left += 1
        length = right - left + 1
        if length > best_length:
            best_start = left
            best_length = length
    expected = "0 0\n" if best_length == 0 else "{} {}\n".format(
        best_start + 1, best_length
    )
    input_data = "{} {}\n{}\n".format(len(values), limit, _numbers(values))
    return _case(input_data, expected, time_limit=time_limit)


def _series_stress():
    rng = random.Random(2634)
    values = [rng.randint(1, 10000) for _ in range(220000)]
    return _series_case(values, 250000000, time_limit=5)


_add_program(
    2634,
    10,
    [
        [
            _series_case([20, 25, 15, 40, 10], 60),
            _series_case([20, 30, 40], 10),
            _series_case([6, 5, 7], 5),
        ],
        [
            _series_case([10, 20, 30, 40], 100),
            _series_case([4, 2, 5, 1, 5], 6),
            _series_case([1] * 50, 10000000000),
            _series_stress,
        ],
    ],
)


def _kadane_case(values, *, time_limit=1):
    ending = best = values[0]
    for value in values[1:]:
        ending = max(value, ending + value)
        best = max(best, ending)
    return _case(_array_input(values), "{}\n".format(best), time_limit=time_limit)


def _kadane_stress():
    values = [1000000] * 180000
    return _kadane_case(values, time_limit=4)


_add_program(
    2635,
    5,
    [[
        _kadane_case([3, 9, 1, 7]),
        _kadane_case([2, -8, 3, -1, 4]),
        _kadane_case([-5, -8, -2]),
        _kadane_case([-1000000]),
        _kadane_case([-5, 4, -1, 2, -7, 8]),
        _kadane_stress,
    ]],
)


def _word_count(text):
    inside = False
    result = 0
    for character in text:
        if character != " " and not inside:
            result += 1
            inside = True
        elif character == " ":
            inside = False
    return result


_add_program(
    2636,
    5,
    [[
        *[
            _case(text + "\n", "{}\n".format(_word_count(text)))
            for text in (
                "to be or not to be",
                "   hello   world   ",
                "",
                "          ",
                "a,b  c!",
                "one",
                "a " * 100,
            )
        ],
    ]],
)


_NUMBER_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?\Z")


def _number_batch(lines):
    expected = "\n".join("YES" if _NUMBER_RE.fullmatch(line) else "NO" for line in lines)
    return _case("\n".join(lines) + "\n", expected + "\n")


_add_program(
    2637,
    10,
    [
        [
            _number_batch(["3", "-2.5", "+0.75", "000", "-0", "+12"]),
            _number_batch(["1234567890" * 10, "+" + "0" * 49 + "." + "1" * 49]),
        ],
        [
            _number_batch([".5", "2.", "1.2.3", "+", "4a", "2+3", "--1", "-+1"]),
            _number_batch(["1e3", " 1", "1 ", "NaN", "inf", "++0.1"]),
        ],
    ],
    comparator=strict_text_equal,
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


_EMAIL_ALLOWED_RE = re.compile(r"[A-Za-z0-9._-]+\Z")


def _valid_email(value):
    if value.count("@") != 1:
        return False
    local, domain = value.split("@")
    if not local or not domain:
        return False
    if not _EMAIL_ALLOWED_RE.fullmatch(local) or not _EMAIL_ALLOWED_RE.fullmatch(domain):
        return False
    return "." in domain and not domain.startswith(".") and not domain.endswith(".")


def _email_batch(lines, *, time_limit=1):
    invalid = [line for line in lines if not _valid_email(line)]
    expected = "\n".join(invalid) + ("\n" if invalid else "")
    return _case("\n".join(lines) + "\n", expected, time_limit=time_limit)


def _email_stress():
    lines = []
    for index in range(10000):
        valid = "user_{}@school{}.ru".format(index, index % 100)
        lines.append(valid if index % 2 == 0 else valid.replace("@", "@@"))
    return _email_batch(lines, time_limit=5)


_add_program(
    2640,
    15,
    [
        [
            _email_batch([
                "ivanov@school.ru", "a@@b.ru", "@b.ru",
                "kot_matroskin@mail.ru", "a@b", "a@.ru",
            ]),
        ],
        [
            _email_batch([
                "a@b.ru", "a@b.", "a@.b", "a@b.c", "abc", "abc@",
                "a@b..ru", ".a@b.ru", "a.@b.ru",
            ]),
        ],
        [
            _email_batch([
                "A_1-b@C_d-e.r2", "a+b@c.ru", "а@b.ru", "a b@c.ru",
                "ok@x.y", "x@@y.z",
            ]),
            _email_stress,
        ],
    ],
    comparator=strict_text_equal,
)


# Chapter 4: searching and sorting -----------------------------------------

def _membership_batch(values, queries, *, time_limit=1):
    present = set(values)
    expected = "\n".join("YES" if value in present else "NO" for value in queries) + "\n"
    return _case(_query_input(values, queries), expected, time_limit=time_limit)


def _membership_stress():
    values = list(range(0, 400000, 2))
    queries = [index * 13 % 400000 for index in range(30000)]
    return _membership_batch(values, queries, time_limit=5)


_add_program(
    2641,
    10,
    [
        [
            _membership_batch([10, 20, 30, 40, 50], [30, 10, 35, 50]),
            _membership_batch([5], [0, 4, 5, 6, 1000000000]),
            _membership_batch([10, 100, 200, 999999999], [0, 10, 150, 999999999, 1000000000]),
        ],
        [_membership_stress],
    ],
    comparator=strict_text_equal,
)


def _first_occurrence_batch(values, queries, *, time_limit=1):
    answer = []
    for query in queries:
        index = bisect.bisect_left(values, query)
        answer.append(index + 1 if index < len(values) and values[index] == query else -1)
    return _case(
        _query_input(values, queries),
        "\n".join(map(str, answer)) + "\n",
        time_limit=time_limit,
    )


def _first_occurrence_stress():
    values = [42] * 400000
    queries = [42] * 5000 + [41, 43] * 1000
    return _first_occurrence_batch(values, queries, time_limit=5)


_add_program(
    2642,
    10,
    [
        [
            _first_occurrence_batch([1, 2, 2, 2, 3, 5], [2, 4, 1, 5]),
            _first_occurrence_batch([-10, 0, 0, 20], [-10, 0, 20, -11, 1]),
            _first_occurrence_batch([7] * 5, [7, 6, 8]),
        ],
        [_first_occurrence_stress],
    ],
)


def _insertion_positions_batch(values, queries, *, time_limit=1):
    expected = "\n".join(str(bisect.bisect_left(values, value) + 1) for value in queries) + "\n"
    return _case(_query_input(values, queries), expected, time_limit=time_limit)


def _insertion_positions_stress():
    values = [index // 3 for index in range(250000)]
    queries = [index * 97 % 100000 for index in range(30000)]
    return _insertion_positions_batch(values, queries, time_limit=5)


_add_program(
    2643,
    5,
    [[
        _insertion_positions_batch([150, 160, 160, 170], [160, 175, 140]),
        _insertion_positions_batch([], [155, 180]),
        _insertion_positions_batch([10, 20], [15, 15, 20]),
        _insertion_positions_batch([5, 5, 5, 5], [5, 4, 6]),
        _insertion_positions_stress,
    ]],
)


def _rope_answer(lengths, pieces):
    low, high = 0, max(lengths)
    while low < high:
        middle = (low + high + 1) // 2
        count = sum(length // middle for length in lengths)
        if count >= pieces:
            low = middle
        else:
            high = middle - 1
    return low


def _rope_case(lengths, pieces, *, time_limit=1):
    input_data = "{} {}\n{}\n".format(len(lengths), pieces, _numbers(lengths))
    return _case(input_data, "{}\n".format(_rope_answer(lengths, pieces)), time_limit=time_limit)


def _rope_stress():
    lengths = [1000000000] * 100000
    return _rope_case(lengths, 1000000000, time_limit=5)


_add_program(
    2644,
    10,
    [
        [
            _rope_case([802, 743, 457], 11),
            _rope_case([10], 3),
            _rope_case([2, 2], 5),
            _rope_case([1, 1000000000, 7, 9], 1),
        ],
        [
            _rope_case([1000000000], 1000000000, time_limit=3),
            _rope_stress,
        ],
    ],
)


def _seating_answer(positions, students):
    def possible(distance):
        count = 1
        last = positions[0]
        for position in positions[1:]:
            if position - last >= distance:
                count += 1
                last = position
                if count >= students:
                    return True
        return count >= students

    low, high = 0, positions[-1] - positions[0]
    while low < high:
        middle = (low + high + 1) // 2
        if possible(middle):
            low = middle
        else:
            high = middle - 1
    return low


def _seating_case(positions, students, *, time_limit=1):
    input_data = "{} {}\n{}\n".format(len(positions), students, _numbers(positions))
    return _case(input_data, "{}\n".format(_seating_answer(positions, students)), time_limit=time_limit)


def _seating_stress():
    positions = [index * 10000 for index in range(100000)]
    return _seating_case(positions, 50000, time_limit=5)


_add_program(
    2645,
    10,
    [
        [
            _seating_case([1, 3, 5, 9, 11], 3),
            _seating_case([2, 4, 6], 3),
            _seating_case([1, 2, 3, 100], 2),
            _seating_case([0, 1, 2, 8, 9, 20], 4),
        ],
        [
            _seating_case([0, 1000000000], 2, time_limit=3),
            _seating_stress,
        ],
    ],
)


def _printer_answer(sheets, times):
    low, high = 0, min(times) * sheets
    while low < high:
        middle = (low + high) // 2
        produced = sum(middle // value for value in times)
        if produced >= sheets:
            high = middle
        else:
            low = middle + 1
    return low


def _printer_case(sheets, times, *, time_limit=1):
    input_data = "{} {}\n{}\n".format(sheets, len(times), _numbers(times))
    return _case(input_data, "{}\n".format(_printer_answer(sheets, times)), time_limit=time_limit)


def _printer_stress():
    rng = random.Random(2646)
    times = [rng.randint(1, 10000) for _ in range(100000)]
    return _printer_case(1000000000, times, time_limit=6)


_add_program(
    2646,
    15,
    [
        [
            _printer_case(11, [4, 7]),
            _printer_case(1, [5]),
            _printer_case(1, [5, 2, 9]),
        ],
        [
            _printer_case(5, [3]),
            _printer_case(10, [4, 4, 4]),
            _printer_stress,
        ],
        [
            _printer_case(1000000000, [10000], time_limit=4),
            _printer_case(999999999, [9999, 10000], time_limit=4),
        ],
    ],
)


def _insert_case(values, inserted, *, time_limit=1):
    result = list(values)
    result.insert(bisect.bisect_left(result, inserted), inserted)
    input_data = "{}\n{}\n{}\n".format(len(values), _numbers(values), inserted)
    return _case(input_data, _numbers(result) + "\n", time_limit=time_limit)


def _insert_stress():
    values = list(range(-100000, 100000, 2))
    return _insert_case(values, 99999, time_limit=3)


_add_program(
    2648,
    5,
    [[
        _insert_case([1, 3, 5, 7, 9], 4),
        _insert_case([2, 4, 6], 10),
        _insert_case([2, 4, 6], 1),
        _insert_case([1, 2, 2, 3], 2),
        _insert_case([-1000000000, 1000000000], 0),
        _insert_stress,
    ]],
)


def _selection_trace(values):
    values = list(values)
    swaps = 0
    for index in range(len(values)):
        best = index
        for candidate in range(index + 1, len(values)):
            if values[candidate] > values[best]:
                best = candidate
        if best != index:
            values[index], values[best] = values[best], values[index]
            swaps += 1
    return values, swaps


def _selection_case(values, *, time_limit=1):
    result, swaps = _selection_trace(values)
    expected = "{}\nSwaps: {}\n".format(_numbers(result), swaps)
    return _case(_array_input(values), expected, time_limit=time_limit)


def _selection_random_case():
    rng = random.Random(2649)
    values = list(range(-400, 400))
    rng.shuffle(values)
    return _selection_case(values, time_limit=4)


_add_program(
    2649,
    10,
    [
        [
            _selection_case([7, 3, 9, 3]),
            _selection_case([5]),
            _selection_case([4, 1, 8, -2, 3]),
        ],
        [
            _selection_case([9, 8, 7]),
            _selection_case([1, 2, 3, 4]),
            _selection_random_case,
        ],
    ],
    comparator=strict_text_equal,
)


def _shaker_trace(values):
    values = list(values)
    snapshots = []
    left, right = 0, len(values) - 1
    to_right = True
    if left >= right:
        return [values], 1
    while left < right:
        swapped = False
        if to_right:
            for index in range(left, right):
                if values[index] > values[index + 1]:
                    values[index], values[index + 1] = values[index + 1], values[index]
                    swapped = True
            right -= 1
        else:
            for index in range(right, left, -1):
                if values[index - 1] > values[index]:
                    values[index - 1], values[index] = values[index], values[index - 1]
                    swapped = True
            left += 1
        snapshots.append(list(values))
        if not swapped or left >= right:
            break
        to_right = not to_right
    return snapshots, len(snapshots)


def _shaker_case(values, *, time_limit=1):
    snapshots, passes = _shaker_trace(values)
    expected = "\n".join(_numbers(snapshot) for snapshot in snapshots)
    expected += "\nPasses: {}\n".format(passes)
    return _case(_array_input(values), expected, time_limit=time_limit)


_add_program(
    2651,
    10,
    [
        [
            _shaker_case([2, 3, 4, 5, 1]),
            _shaker_case([1, 2, 3]),
            _shaker_case([5]),
        ],
        [
            _shaker_case([4, 3, 2, 1]),
            _shaker_case([2, 3, 4, 5, 6, 7, 8, 1]),
            _shaker_case([3, 1, 2, 2, 0]),
        ],
    ],
    comparator=strict_text_equal,
)


def _merge_case(first, second, *, time_limit=1):
    merged = []
    left = right = 0
    while left < len(first) or right < len(second):
        if right == len(second) or (left < len(first) and first[left] <= second[right]):
            merged.append(first[left])
            left += 1
        else:
            merged.append(second[right])
            right += 1
    input_data = "{}\n{}\n{}\n{}\n".format(
        len(first), _numbers(first), len(second), _numbers(second)
    )
    return _case(input_data, _numbers(merged) + "\n", time_limit=time_limit)


def _merge_stress():
    first = list(range(0, 500000, 2))
    second = list(range(1, 500000, 2))
    return _merge_case(first, second, time_limit=6)


_add_program(
    2652,
    5,
    [[
        _merge_case([1, 4, 9], [2, 3, 10, 11]),
        _merge_case([], [1, 2, 3]),
        _merge_case([-1, 5], []),
        _merge_case([1, 2, 2, 7], [2, 2, 3, 7, 7]),
        _merge_case([1, 2, 3], [10, 20]),
        _merge_stress,
    ]],
)


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


def _score_names_case(records, *, time_limit=1):
    ordered = sorted(enumerate(records), key=lambda item: (-item[1][1], item[0]))
    expected = _numbers(record[0] for _index, record in ordered) + "\n"
    input_data = "{}\n{}\n".format(
        len(records),
        "\n".join("{} {}".format(name, score) for name, score in records),
    )
    return _case(input_data, expected, time_limit=time_limit)


def _score_names_stress():
    records = [("n{:05d}".format(index), index % 11) for index in range(45000)]
    return _score_names_case(records, time_limit=5)


_add_program(
    2657,
    5,
    [[
        _score_names_case([("ivan", 5), ("petr", 8), ("anna", 5), ("oleg", 3)]),
        _score_names_case([("bob", 7), ("ann", 7), ("zed", 7), ("kim", 7)]),
        _score_names_case([("zero", 0), ("max", 1000000000), ("mid", 1)]),
        _score_names_stress,
    ]],
    comparator=strict_text_equal,
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


_COINS = (100, 50, 25, 10, 5, 1)


def _coin_answer(amount):
    lines = []
    total = 0
    for denomination in _COINS:
        count, amount = divmod(amount, denomination)
        if count:
            lines.append("{} {}".format(denomination, count))
            total += count
    return "\n".join([str(total), *lines]) + "\n"


_add_program(
    2660,
    5,
    [[
        *[
            _case("{}\n".format(amount), _coin_answer(amount))
            for amount in (0, 1, 5, 25, 63, 99, 191, 999999999, 1000000000)
        ],
    ]],
    comparator=strict_text_equal,
)


def _greedy_coin_count(amount, denominations):
    count = 0
    for denomination in sorted(denominations, reverse=True):
        used, amount = divmod(amount, denomination)
        count += used
    return count


def _counterexample_answer(denominations, limit):
    best = [0] + [limit + 1] * limit
    for amount in range(1, limit + 1):
        best[amount] = 1 + min(
            best[amount - denomination]
            for denomination in denominations
            if denomination <= amount
        )
        greedy = _greedy_coin_count(amount, denominations)
        if greedy > best[amount]:
            return "{} {} {}\n".format(amount, greedy, best[amount])
    return "none\n"


def _counterexample_case(denominations, limit, *, time_limit=1):
    input_data = "{}\n{}\n{}\n".format(
        len(denominations), _numbers(denominations), limit
    )
    return _case(
        input_data,
        _counterexample_answer(denominations, limit),
        time_limit=time_limit,
    )


_add_program(
    2662,
    10,
    [
        [
            _counterexample_case([1, 3, 4], 20),
            _counterexample_case([1, 4, 5], 20),
            _counterexample_case([4, 1, 3], 20),
        ],
        [
            _counterexample_case([1, 2, 4], 10000, time_limit=4),
            _counterexample_case([1], 10000, time_limit=4),
            _counterexample_case([1, 7, 13, 29, 57, 100], 10000, time_limit=5),
        ],
    ],
    comparator=strict_text_equal,
)


EXPECTED_TASK_IDS = frozenset({
    2570,
    *range(2593, 2601),
    *range(2602, 2609),
    2610, 2611, 2612, 2613, 2614, 2615, 2616, 2617, 2619,
    2620, 2621, 2624, 2625, 2626, 2627, 2629, 2630, 2631, 2632,
    2633, 2634, 2635, 2636, 2637, 2638, 2640, 2641, 2642, 2643,
    2644, 2645, 2646, 2648, 2649, 2651, 2652, 2656, 2657, 2658,
    2660, 2662,
})

if set(TASKS) != EXPECTED_TASK_IDS:
    missing = sorted(EXPECTED_TASK_IDS - set(TASKS))
    extra = sorted(set(TASKS) - EXPECTED_TASK_IDS)
    raise RuntimeError("grade8 chapter 1-4 registry mismatch: missing={}, extra={}".format(
        missing, extra
    ))
