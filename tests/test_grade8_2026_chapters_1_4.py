import bisect
import json
import re
import unittest

from environments import grade8_2026_chapters_1_4 as chapter
from runner import SolutionException


BUFFER_OVERFLOW_COMMENT = (
    "// BUFFER_OVERFLOW: destination capacity is unknown; "
    "writing past it is undefined behavior."
)
TRANSITIONS_COMMENT = """/*
TRANSITIONS
state;letter;semicolon;quote;end
outside;append;emit_field;enter_quotes;emit_record
inside;append;append;leave_quotes;invalid
*/"""
BENCHMARK_COMMENTS = """// BENCHMARK n=1000000 counting_ms=12 quicksort_ms=41
// VERIFIED_EQUAL: yes"""


def valid_source_for(task_id):
    if task_id == 2614:
        return """
int string_len(const char str[]) {
    int result = 0;
    while (str[result] != '\\0') ++result;
    return result;
}
int main() { return 0; }
"""
    if task_id == 2615:
        return """
void string_copy(char destination[], const char source[]) {
    int i = 0;
    do { destination[i] = source[i]; } while (source[i++] != '\\0');
}
void string_concat(char destination[], const char source[]) {
    int i = 0, j = 0;
    while (destination[i] != '\\0') ++i;
    do { destination[i + j] = source[j]; } while (source[j++] != '\\0');
}
%s
int main() { return 0; }
""" % BUFFER_OVERFLOW_COMMENT
    if task_id == 2638:
        return TRANSITIONS_COMMENT + "\nint main() { return 0; }\n"
    if task_id == 2656:
        return BENCHMARK_COMMENTS + "\nint main() { return 0; }\n"
    if task_id == 2658:
        return """
bool comes_before(long long number_a, long long score_a,
                  long long number_b, long long score_b) {
    if (score_a != score_b) return score_a > score_b;
    return number_a < number_b;
}
int main() { return comes_before(1, 2, 3, 4) ? 0 : 0; }
"""
    return "int main() { return 17; }"


def logic_diagram(component_types, connections):
    nodes = [
        {"type": kind, "x": index * 40, "y": 20, "id": str(index)}
        for index, kind in enumerate(component_types)
    ]
    persisted = []
    for source_node, source_connector, target_node, target_connector in connections:
        persisted.append({
            "source": {"nodeId": str(source_node), "connectorId": str(source_connector)},
            "target": {"nodeId": str(target_node), "connectorId": str(target_connector)},
        })
    return {"nodes": nodes, "connections": persisted}


def real_nand_export(*, include_xor=True):
    missions = ["RELAY_NAND", "INV", "AND", "OR"]
    if include_xor:
        missions.append("XOR")
    result = {
        "NandGame:Levels": missions,
        # The first level uses relays; the checker verifies its official schema
        # and the following unlocked level, while subsequent logic diagrams are
        # independently evaluated against their truth tables.
        "NandGame:Levels:RELAY_NAND": logic_diagram(
            ["RELAY-ON", "RELAY-OFF"],
            [
                ("input", 0, 0, 0), ("input", 2, 0, 1),
                ("input", 1, 1, 0), (0, 0, 1, 1), (1, 0, "output", 0),
            ],
        ),
        # INV(a) = NAND(a, a)
        "NandGame:Levels:INV": logic_diagram(
            ["NAND"],
            [("input", 0, 0, 0), ("input", 0, 0, 1), (0, 0, "output", 0)],
        ),
        # AND(a,b) = INV(NAND(a,b))
        "NandGame:Levels:AND": logic_diagram(
            ["NAND", "INV"],
            [
                ("input", 0, 0, 0), ("input", 1, 0, 1),
                (0, 0, 1, 0), (1, 0, "output", 0),
            ],
        ),
        # OR(a,b) = NAND(INV(a), INV(b))
        "NandGame:Levels:OR": logic_diagram(
            ["INV", "INV", "NAND"],
            [
                ("input", 0, 0, 0), ("input", 1, 1, 0),
                (0, 0, 2, 0), (1, 0, 2, 1), (2, 0, "output", 0),
            ],
        ),
    }
    if include_xor:
        # Four-NAND XOR: d=NAND(a,b), NAND(NAND(a,d), NAND(b,d)).
        result["NandGame:Levels:XOR"] = logic_diagram(
            ["NAND"] * 4,
            [
                ("input", 0, 0, 0), ("input", 1, 0, 1),
                ("input", 0, 1, 0), (0, 0, 1, 1),
                ("input", 1, 2, 0), (0, 0, 2, 1),
                (1, 0, 3, 0), (2, 0, 3, 1), (3, 0, "output", 0),
            ],
        )
    return result


NAND_EXPLANATIONS = """
Nand: Two relay switches negate conjunction of both inputs; the circuit uses 0 NAND gates.
Invert: The input signal is inverted by the single stage; the circuit uses 1 NAND gate.
And: A double inversion restores the AND conjunction; the circuit uses 2 NAND gates.
Or: De Morgan transforms the inputs into an OR disjunction; the circuit uses 3 NAND gates.
Xor: Exclusive OR is true only for different input signals; the circuit uses 4 NAND gates.
""".strip()


class ReferenceRunner:
    """Return each hidden case's own oracle output without invoking Docker."""

    def __init__(self, task_id, *, program_override=None, failed_harness_keys=()):
        self.task_id = task_id
        self.groups = chapter.materialize_task_groups(task_id)
        self.expected_by_input = {}
        for group in self.groups:
            for case in group:
                self.expected_by_input[case.get("input", "")] = case["expected"]
        for group in chapter._materialize(chapter.HARNESS_PROGRAM_CASES.get(task_id, [])):
            for case in group:
                # Program cases with line-selecting comparators store only the
                # selected line.  Supply a complete valid two-line answer.
                if task_id == 2615:
                    first, second = case["input"].splitlines()
                    self.expected_by_input[case["input"]] = first + "\n" + first + second + "\n"
                else:
                    self.expected_by_input[case.get("input", "")] = case["expected"]
        self.program_override = program_override
        self.failed_harness_keys = set(failed_harness_keys)
        self.calls = []
        self.run_source_calls = []

    def __call__(self, input_data, time_limit=1, capture_limit=None):
        self.calls.append((input_data, time_limit, capture_limit))
        if self.program_override is not None:
            result = self.program_override(input_data, time_limit)
            if result is not None:
                return result
        return self.expected_by_input[input_data]

    def run_source(self, source_code, input_data="", time_limit=1, probe_source=None):
        self.run_source_calls.append((source_code, input_data, time_limit, probe_source))
        match = re.search(r"GP_CASE\s+(\d+):([A-Za-z0-9_]+)", source_code)
        if not match:
            raise AssertionError("C++ harness has no GP_CASE marker")
        task_id, key = int(match.group(1)), match.group(2)
        self.assert_task(task_id)
        if key in self.failed_harness_keys:
            return "wrong answer\n"
        return chapter.HARNESS_CASES[(task_id, key)]["expected"]

    def assert_task(self, task_id):
        if task_id != self.task_id:
            raise AssertionError("harness for unexpected task")


def perform(task_id, runner, source_code="int main() { return 0; }"):
    maximum, handler = chapter.TASKS[task_id]
    points, feedback = handler(runner, source_code)
    return maximum, points, feedback


class RegistryTests(unittest.TestCase):
    def test_registry_has_exactly_the_57_test_tasks(self):
        self.assertEqual(set(chapter.TASKS), set(chapter.EXPECTED_TASK_IDS))
        self.assertEqual(len(chapter.TASKS), 57)
        self.assertNotIn(2622, chapter.TASKS)  # Секундомер is a GPT report task.

    def test_group_count_matches_five_point_scoring(self):
        for task_id, (maximum, _handler) in chapter.TASKS.items():
            if task_id == 2570:
                continue
            with self.subTest(task_id=task_id):
                self.assertIn(task_id, chapter.TASK_CASES)
                self.assertEqual(len(chapter.TASK_CASES[task_id]), maximum // 5)

    def test_known_maximums_and_range(self):
        expected = {
            2570: 15,
            2593: 5,
            2599: 10,
            2611: 10,
            2638: 15,
            2646: 15,
            2662: 10,
        }
        for task_id, maximum in expected.items():
            self.assertEqual(chapter.TASKS[task_id][0], maximum)

    def test_large_cases_are_lazy_at_import_time(self):
        for task_id in (2607, 2620, 2631, 2641, 2652, 2656):
            with self.subTest(task_id=task_id):
                self.assertTrue(
                    any(callable(case) for group in chapter.TASK_CASES[task_id] for case in group)
                )


class ComparatorAndNandTests(unittest.TestCase):
    def test_strict_comparator_preserves_spaces_but_allows_final_newlines(self):
        self.assertTrue(chapter.strict_text_equal("abc\r\n", "abc\n"))
        self.assertTrue(chapter.strict_text_equal("abc\n\n", "abc\n"))
        self.assertFalse(chapter.strict_text_equal("abc \n", "abc\n"))
        self.assertFalse(chapter.strict_text_equal("a  b\n", "a b\n"))

    def test_nand_accepts_real_flat_export_and_five_explanations(self):
        source = "{}\n{}".format(json.dumps(real_nand_export()), NAND_EXPLANATIONS)
        maximum, points, feedback = perform(2570, None, source)
        self.assertEqual((maximum, points), (15, 15), feedback)

    def test_nand_rejects_markdown_fence_and_extra_explanation_line(self):
        payload = json.dumps(real_nand_export())
        fenced = "```json\n{}\n```\n{}".format(payload, NAND_EXPLANATIONS)
        _maximum, points, _feedback = perform(2570, None, fenced)
        self.assertEqual(points, 0)

        extra = payload + "\n" + NAND_EXPLANATIONS + "\nAttachment: screenshot"
        _maximum, points, _feedback = perform(2570, None, extra)
        self.assertEqual(points, 10)

    def test_nand_scores_completed_level_groups(self):
        payload = real_nand_export(include_xor=False)
        maximum, points, feedback = perform(
            2570, None, json.dumps(payload) + "\n" + NAND_EXPLANATIONS
        )
        self.assertEqual(maximum, 15)
        self.assertEqual(points, 10, feedback)

    def test_nand_requires_all_five_substantive_explanations_and_correct_counts(self):
        payload = json.dumps(real_nand_export())
        generic = "\n".join(
            "{}: This circuit is completed correctly and uses {} NAND gates.".format(level, count)
            for level, count in zip(("Nand", "Invert", "And", "Or", "Xor"), range(5))
        )
        _maximum, points, _feedback = perform(2570, None, payload + "\n" + generic)
        self.assertEqual(points, 10)

        wrong_count = NAND_EXPLANATIONS.replace("uses 4 NAND", "uses 5 NAND")
        _maximum, points, _feedback = perform(2570, None, payload + "\n" + wrong_count)
        self.assertEqual(points, 10)

        missing = "\n".join(NAND_EXPLANATIONS.splitlines()[:-1])
        _maximum, points, _feedback = perform(2570, None, payload + "\n" + missing)
        self.assertEqual(points, 10)

    def test_nand_rejects_nested_fake_export_and_invalid_diagram_schema(self):
        nested = {"snapshot": {"data": real_nand_export()}}
        _maximum, points, _feedback = perform(
            2570, None, json.dumps(nested) + "\n" + NAND_EXPLANATIONS
        )
        self.assertEqual(points, 0)

        malformed = real_nand_export()
        malformed["NandGame:Levels:OR"] = {"nodes": [{"anything": 1}], "connections": [1]}
        _maximum, points, _feedback = perform(
            2570, None, json.dumps(malformed) + "\n" + NAND_EXPLANATIONS
        )
        self.assertEqual(points, 5)

    def test_nand_rejects_malformed_or_plain_prose(self):
        for source in ("Nand Invert And Or Xor", "{not json", "[]"):
            with self.subTest(source=source):
                _maximum, points, _feedback = perform(2570, None, source)
                self.assertEqual(points, 0)


class HandlerScoringTests(unittest.TestCase):
    def test_reference_outputs_receive_full_points_for_representative_programs(self):
        # These cover exact text, numeric, matrix, parser, trace and greedy handlers.
        for task_id in (
            2593, 2594, 2595, 2599, 2606, 2611, 2613,
            2636, 2637, 2649, 2651, 2660,
        ):
            with self.subTest(task_id=task_id):
                runner = ReferenceRunner(task_id)
                maximum, points, feedback = perform(
                    task_id, runner, source_code=valid_source_for(task_id)
                )
                self.assertEqual(points, maximum, feedback)

    def test_all_function_tasks_use_cpp_run_source_harnesses(self):
        for task_id in (2602, 2603, 2610, 2614, 2615, 2616, 2617, 2626):
            with self.subTest(task_id=task_id):
                runner = ReferenceRunner(task_id)
                source_code = valid_source_for(task_id)
                maximum, points, feedback = perform(
                    task_id,
                    runner,
                    source_code=source_code,
                )
                self.assertEqual(points, maximum, feedback)
                self.assertTrue(runner.run_source_calls)
                self.assertTrue(runner.calls)
                for source, _input, _limit, probe in runner.run_source_calls:
                    self.assertIn("#define main __geekpaste_student_main", source)
                    self.assertIn(source_code.strip(), source)
                    self.assertIsNone(probe)

    def test_one_failed_harness_criterion_loses_its_five_points(self):
        runner = ReferenceRunner(2615, failed_harness_keys={"concat_normal"})
        maximum, points, feedback = perform(
            2615, runner, source_code=valid_source_for(2615)
        )
        self.assertEqual(maximum, 10)
        self.assertEqual(points, 5, feedback)

    def test_correct_function_does_not_hide_broken_student_main(self):
        runner = ReferenceRunner(
            2602,
            program_override=lambda _input, _limit: "definitely wrong\n",
        )
        maximum, points, feedback = perform(2602, runner)
        self.assertEqual(maximum, 5)
        self.assertEqual(points, 0, feedback)
        self.assertTrue(runner.calls)

    def test_timeout_in_stress_group_does_not_erase_correctness_group(self):
        holder = {}

        def timeout_stress(input_data, time_limit):
            del input_data
            if time_limit >= 5:
                raise SolutionException("timeout")
            return None

        runner = ReferenceRunner(2620, program_override=timeout_stress)
        holder["runner"] = runner
        maximum, points, feedback = perform(2620, runner)
        self.assertEqual(maximum, 10)
        self.assertEqual(points, 5, feedback)


class StructuredSubmissionTests(unittest.TestCase):
    def test_complexity_answer_is_checked_as_text_without_running_code(self):
        for source in (
            "n n2 logn 1 nlogn",
            "```text\nn n2 logn 1 nlogn\n```",
        ):
            with self.subTest(source=source):
                maximum, points, feedback = perform(2621, None, source)
                self.assertEqual((maximum, points), (5, 5), feedback)

        for source in (
            'int main() { std::cout << "n n2 logn 1 nlogn"; }',
            "n n2 logn nlogn 1",
            "Answer: n n2 logn 1 nlogn",
            "n n2 logn 1 nlogn\nextra",
        ):
            with self.subTest(source=source):
                _maximum, points, _feedback = perform(2621, None, source)
                self.assertEqual(points, 0)

    def test_string_len_rejects_strlen_and_requires_exact_signature(self):
        strlen_source = """
#include <cstring>
int string_len(const char str[]) { return strlen(str); }
int main() { return 0; }
"""
        maximum, points, feedback = perform(2614, ReferenceRunner(2614), strlen_source)
        self.assertEqual((maximum, points), (5, 0), feedback)

        wrong_signature = """
int string_len(char str[]) { int n = 0; while (str[n]) ++n; return n; }
int main() { return 0; }
"""
        _maximum, points, _feedback = perform(2614, ReferenceRunner(2614), wrong_signature)
        self.assertEqual(points, 0)

    def test_copy_concat_reject_library_calls_and_require_exact_overflow_comment(self):
        library_source = """
#include <cstring>
void string_copy(char destination[], const char source[]) { strcpy(destination, source); }
void string_concat(char destination[], const char source[]) { strcat(destination, source); }
%s
int main() { return 0; }
""" % BUFFER_OVERFLOW_COMMENT
        maximum, points, feedback = perform(2615, ReferenceRunner(2615), library_source)
        self.assertEqual((maximum, points), (10, 0), feedback)

        without_comment = valid_source_for(2615).replace(BUFFER_OVERFLOW_COMMENT, "")
        _maximum, points, _feedback = perform(2615, ReferenceRunner(2615), without_comment)
        self.assertEqual(points, 5)

    def test_copy_concat_extra_output_mutant_is_rejected(self):
        def debug_output(input_data, _time_limit):
            first, second = input_data.splitlines()
            return first + "\n" + first + second + "\nDEBUG\n"

        runner = ReferenceRunner(2615, program_override=debug_output)
        maximum, points, feedback = perform(
            2615, runner, source_code=valid_source_for(2615)
        )
        self.assertEqual((maximum, points), (10, 0), feedback)

    def test_journal_requires_exact_transition_table_artifact(self):
        maximum, points, feedback = perform(
            2638, ReferenceRunner(2638), source_code=valid_source_for(2638)
        )
        self.assertEqual((maximum, points), (15, 15), feedback)

        missing_cell = valid_source_for(2638).replace(
            "inside;append;append;leave_quotes;invalid",
            "inside;append;append;leave_quotes",
        )
        _maximum, points, _feedback = perform(2638, ReferenceRunner(2638), missing_cell)
        self.assertEqual(points, 10)

    def test_census_requires_verified_faster_benchmark(self):
        maximum, points, feedback = perform(
            2656, ReferenceRunner(2656), source_code=valid_source_for(2656)
        )
        self.assertEqual((maximum, points), (10, 10), feedback)

        for mutation in (
            BENCHMARK_COMMENTS.replace("// VERIFIED_EQUAL: yes", ""),
            BENCHMARK_COMMENTS.replace("counting_ms=12 quicksort_ms=41", "counting_ms=41 quicksort_ms=12"),
            BENCHMARK_COMMENTS.replace("counting_ms=12", "counting_ms=0"),
        ):
            with self.subTest(mutation=mutation):
                source = mutation + "\nint main() { return 0; }"
                _maximum, points, _feedback = perform(2656, ReferenceRunner(2656), source)
                self.assertEqual(points, 5)

    def test_protocol_requires_exact_comparator_and_a_real_main_call(self):
        maximum, points, feedback = perform(
            2658, ReferenceRunner(2658), source_code=valid_source_for(2658)
        )
        self.assertEqual((maximum, points), (10, 10), feedback)

        not_called = valid_source_for(2658).replace(
            "int main() { return comes_before(1, 2, 3, 4) ? 0 : 0; }",
            "int main() { return 0; }",
        )
        _maximum, points, _feedback = perform(2658, ReferenceRunner(2658), not_called)
        self.assertEqual(points, 5)

        two_argument_mutant = """
bool comes_before(long long number_a, long long number_b) { return number_a < number_b; }
int main() { return comes_before(1, 2); }
"""
        _maximum, points, _feedback = perform(2658, ReferenceRunner(2658), two_argument_mutant)
        self.assertEqual(points, 5)


class MutantRejectionTests(unittest.TestCase):
    def assert_not_max(self, task_id, override):
        runner = ReferenceRunner(task_id, program_override=override)
        maximum, points, feedback = perform(task_id, runner)
        self.assertLess(points, maximum, feedback)

    def test_python_floor_division_mutant_is_rejected(self):
        def floor_division(input_data, _time_limit):
            values = input_data.split()
            if len(values) != 2:
                return None
            a, b = map(int, values)
            quotient, remainder = divmod(a, b)
            return "{} / {} = {} (rem {})\n".format(a, b, quotient, remainder)

        self.assert_not_max(2595, floor_division)

    def test_warming_that_treats_equal_as_warmer_is_rejected(self):
        def non_strict(input_data, _time_limit):
            values = list(map(int, input_data.split()))
            size, temperatures = values[0], values[1:]
            if size != len(temperatures):
                return None
            answer = []
            for index, value in enumerate(temperatures):
                wait = 0
                for later in range(index + 1, size):
                    if temperatures[later] >= value:
                        wait = later - index
                        break
                answer.append(wait)
            return " ".join(map(str, answer)) + "\n"

        self.assert_not_max(2606, non_strict)

    def test_vigenere_that_spends_key_on_spaces_is_rejected(self):
        def advances_every_character(input_data, _time_limit):
            lines = input_data.rstrip("\n").split("\n")
            if len(lines) != 2:
                return None
            text, key = lines
            output = []
            for index, character in enumerate(text):
                if "a" <= character <= "z":
                    shift = ord(key[index % len(key)]) - 97
                    output.append(chr((ord(character) - 97 + shift) % 26 + 97))
                else:
                    output.append(character)
            return "".join(output) + "\n"

        self.assert_not_max(2619, advances_every_character)

    def test_first_occurrence_that_returns_last_duplicate_is_rejected(self):
        def last_occurrence(input_data, _time_limit):
            values = list(map(int, input_data.split()))
            size = values[0]
            array = values[1:1 + size]
            query_count = values[1 + size]
            queries = values[2 + size:]
            if len(queries) != query_count:
                return None
            result = []
            for query in queries:
                index = bisect.bisect_right(array, query) - 1
                result.append(index + 1 if index >= 0 and array[index] == query else -1)
            return "\n".join(map(str, result)) + "\n"

        self.assert_not_max(2642, last_occurrence)

    def test_selection_sort_that_counts_self_swaps_is_rejected(self):
        def counts_every_iteration(input_data, _time_limit):
            values = list(map(int, input_data.split()))
            size, array = values[0], values[1:]
            if len(array) != size:
                return None
            array.sort(reverse=True)
            return "{}\nSwaps: {}\n".format(" ".join(map(str, array)), size)

        self.assert_not_max(2649, counts_every_iteration)

    def test_unstable_score_sort_is_rejected(self):
        def unstable(input_data, _time_limit):
            lines = input_data.strip().splitlines()
            if not lines:
                return None
            records = []
            for line in lines[1:]:
                name, score = line.split()
                records.append((name, int(score)))
            records.sort(key=lambda item: (-item[1], item[0]))
            return " ".join(name for name, _score in records) + "\n"

        self.assert_not_max(2657, unstable)


class AmbiguityAndCaptureTests(unittest.TestCase):
    def test_magic_non_sample_diagnostics_are_semantic_and_nonnegative(self):
        cases = [case for group in chapter.materialize_task_groups(2611) for case in group]
        non_row = [case for case in cases if "NO: col" in case["expected"] or "NO: diag" in case["expected"]]
        self.assertTrue(non_row)
        self.assertTrue(all("-" not in case["input"] for case in cases))
        for case in non_row:
            alternative = (
                case["expected"]
                .replace("NO:", "NO")
                .replace(" (sum ", " sum=")
                .replace(", expected ", "; expected=")
                .replace(")", "")
            )
            self.assertTrue(case["comparator"](alternative, case["expected"]))

    def test_selection_hidden_duplicates_do_not_add_an_unpublished_tie_policy(self):
        cases = [case for group in chapter.materialize_task_groups(2649) for case in group]
        duplicate_inputs = []
        for case in cases:
            values = list(map(int, case["input"].split()))[1:]
            if len(values) != len(set(values)):
                duplicate_inputs.append(values)
        # The only duplicate case is the task's published sample; the disabled
        # hidden [2,2,1] tie-policy case must not be resurrected.
        self.assertEqual(duplicate_inputs, [[7, 3, 9, 3]])

    def test_all_thirteen_large_oracles_have_a_finite_trusted_capture_limit(self):
        expected_sizes = {
            2607: 588890,
            2627: 131068,
            2631: 325000,
            2632: 150000,
            2638: 159269,
            2640: 113945,
            2641: 105000,
            2643: 198780,
            2648: 638901,
            2652: 3388890,
            2656: 1081894,
            2657: 315000,
            2658: 393439,
        }
        found = {}
        for task_id in sorted(chapter.TASK_CASES):
            for group in chapter.materialize_task_groups(task_id):
                for case in group:
                    size = len(case["expected"].encode("utf-8"))
                    if size > 100 * 1024:
                        self.assertIn("capture_limit", case)
                        self.assertGreaterEqual(case["capture_limit"], size)
                        self.assertGreaterEqual(
                            case["capture_limit"],
                            size + case["expected"].count("\n"),
                        )
                        self.assertLessEqual(case["capture_limit"], 4 * 1024 * 1024)
                        found[task_id] = size
        self.assertEqual(found, expected_sizes)


class StressShapeTests(unittest.TestCase):
    def test_stress_cases_have_relaxed_but_finite_limits(self):
        for task_id in (2604, 2620, 2631, 2641, 2644, 2645, 2652, 2656):
            with self.subTest(task_id=task_id):
                cases = [case for group in chapter.materialize_task_groups(task_id) for case in group]
                limits = [case["time_limit"] for case in cases]
                self.assertTrue(any(limit >= 3 for limit in limits))
                self.assertTrue(all(1 <= limit <= 6 for limit in limits))

    def test_algorithmic_stress_inputs_are_materially_large(self):
        thresholds = {
            2620: 100000,
            2631: 500000,
            2641: 500000,
            2644: 500000,
            2652: 1000000,
            2656: 500000,
        }
        for task_id, minimum_bytes in thresholds.items():
            with self.subTest(task_id=task_id):
                cases = [case for group in chapter.materialize_task_groups(task_id) for case in group]
                self.assertGreaterEqual(max(len(case["input"]) for case in cases), minimum_bytes)


if __name__ == "__main__":
    unittest.main()
