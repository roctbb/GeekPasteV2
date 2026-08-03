from collections import Counter
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from runner import ExecutionException, SolutionException

from environments import grade8_2026_chapters_7_8 as chapter
from environments.grade8_2026_common import exact_text_equal, float_tokens_equal


EXPECTED_TASKS = {
    2718: 10,
    2720: 15,
    2721: 10,
    2722: 5,
    2723: 10,
    2725: 15,
    2726: 10,
    2727: 5,
    2728: 10,
    2729: 15,
    2730: 10,
    2731: 5,
    2732: 10,
    2733: 10,
    2734: 10,
    2735: 15,
    2736: 15,
    2737: 5,
    2738: 10,
    2739: 20,
    2740: 10,
    2741: 15,
    2742: 5,
    2743: 15,
    2744: 5,
    2745: 15,
    2747: 15,
    2749: 5,
    2750: 5,
    2751: 15,
    2752: 10,
    2753: 20,
}


class ReplayRunner:
    def __init__(self, groups):
        self.answers = {
            case["input"]: case["expected"]
            for group in groups
            for case in group
        }
        self.calls = []

    def __call__(self, input_data, time_limit=1, capture_limit=None):
        self.calls.append((input_data, time_limit, capture_limit))
        return self.answers[input_data]


class WrongRunner:
    def __call__(self, _input_data, time_limit=1, capture_limit=None):
        return "definitely wrong"


class ArchiveRunner:
    def __init__(self, result="OK", error=None):
        self.result = result
        self.error = error
        self.calls = []

    def run_source(self, source_code, input_data="", time_limit=1):
        self.calls.append((source_code, input_data, time_limit))
        if self.error is not None:
            raise self.error
        return self.result


def _compile_cpp(compiler, source, target):
    source_path = target.with_suffix(".cpp")
    source_path.write_text(source, encoding="utf-8")
    completed = subprocess.run(
        [compiler, "-std=c++17", "-O2", str(source_path), "-o", str(target)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"g++ failed for {source_path.name}:\n{completed.stderr}"
        )


def _fixture_archiver_source(payload):
    expected = ",".join(map(str, payload))
    archive = ",".join(map(str, chapter._build_gph1_archive(payload)))
    return r"""
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

bool read_file(const char* path, std::vector<unsigned char>& data) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return false;
    data.assign(std::istreambuf_iterator<char>(input),
                std::istreambuf_iterator<char>());
    return !input.bad();
}

bool write_file(const char* path, const std::vector<unsigned char>& data) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) return false;
    if (!data.empty()) {
        output.write(reinterpret_cast<const char*>(data.data()), data.size());
    }
    return static_cast<bool>(output);
}

int main(int argc, char** argv) {
    if (argc != 4) return 2;
    const std::vector<unsigned char> expected = {__EXPECTED__};
    const std::vector<unsigned char> valid_archive = {__ARCHIVE__};
    std::vector<unsigned char> input;
    if (!read_file(argv[2], input)) return 3;
    const std::string mode = argv[1];
    if (mode == "pack") {
        if (input != expected) return 4;
        return write_file(argv[3], valid_archive) ? 0 : 5;
    }
    if (mode == "unpack") {
        if (input != valid_archive) return 6;
        return write_file(argv[3], expected) ? 0 : 7;
    }
    return 8;
}
""".replace("__EXPECTED__", expected).replace("__ARCHIVE__", archive)


RAW_COPY_ARCHIVER_SOURCE = r"""
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 4) return 2;
    const std::string mode = argv[1];
    if (mode != "pack" && mode != "unpack") return 3;
    std::ifstream input(argv[2], std::ios::binary);
    if (!input) return 4;
    const std::vector<char> data{
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>()
    };
    std::ofstream output(argv[3], std::ios::binary | std::ios::trunc);
    if (!output) return 5;
    if (!data.empty()) output.write(data.data(), data.size());
    return output ? 0 : 6;
}
"""


GPH1_REFERENCE_ARCHIVER_SOURCE = r"""
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iterator>
#include <queue>
#include <string>
#include <vector>

struct HuffmanNode {
    std::uint64_t frequency = 0;
    int symbol = -1;
    int left = -1;
    int right = -1;
    int minimum_symbol = 0;
};

struct QueueItem {
    std::uint64_t frequency = 0;
    int minimum_symbol = 0;
    int node = -1;
};

struct QueueGreater {
    bool operator()(const QueueItem& left, const QueueItem& right) const {
        if (left.frequency != right.frequency) {
            return left.frequency > right.frequency;
        }
        if (left.minimum_symbol != right.minimum_symbol) {
            return left.minimum_symbol > right.minimum_symbol;
        }
        return left.node > right.node;
    }
};

struct Entry {
    unsigned char symbol = 0;
    unsigned char length = 0;
    std::string code;
};

struct TrieNode {
    int child[2] = {-1, -1};
    int symbol = -1;
};

bool read_file(const char* path, std::vector<unsigned char>& data) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return false;
    data.assign(std::istreambuf_iterator<char>(input),
                std::istreambuf_iterator<char>());
    return !input.bad();
}

bool write_file(const char* path, const std::vector<unsigned char>& data) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) return false;
    if (!data.empty()) {
        output.write(reinterpret_cast<const char*>(data.data()),
                     static_cast<std::streamsize>(data.size()));
    }
    return static_cast<bool>(output);
}

void append_u16(std::vector<unsigned char>& data, std::uint16_t value) {
    data.push_back(static_cast<unsigned char>(value));
    data.push_back(static_cast<unsigned char>(value >> 8));
}

void append_u64(std::vector<unsigned char>& data, std::uint64_t value) {
    for (unsigned shift = 0; shift < 64; shift += 8) {
        data.push_back(static_cast<unsigned char>(value >> shift));
    }
}

bool take_u16(const std::vector<unsigned char>& data,
              std::size_t& position, std::uint16_t& value) {
    if (position > data.size() || data.size() - position < 2) return false;
    value = static_cast<std::uint16_t>(data[position])
        | (static_cast<std::uint16_t>(data[position + 1]) << 8);
    position += 2;
    return true;
}

bool take_u64(const std::vector<unsigned char>& data,
              std::size_t& position, std::uint64_t& value) {
    if (position > data.size() || data.size() - position < 8) return false;
    value = 0;
    for (unsigned shift = 0; shift < 64; shift += 8) {
        value |= static_cast<std::uint64_t>(data[position++]) << shift;
    }
    return true;
}

bool increment_binary(std::string& code) {
    for (std::size_t offset = 0; offset < code.size(); ++offset) {
        const std::size_t index = code.size() - 1 - offset;
        if (code[index] == '0') {
            code[index] = '1';
            return true;
        }
        code[index] = '0';
    }
    return false;
}

bool assign_canonical_codes(std::vector<Entry>& entries) {
    if (entries.empty()) return true;
    entries[0].code.assign(entries[0].length, '0');
    for (std::size_t index = 1; index < entries.size(); ++index) {
        entries[index].code = entries[index - 1].code;
        if (!increment_binary(entries[index].code)) return false;
        if (entries[index].length < entries[index].code.size()) return false;
        entries[index].code.append(
            entries[index].length - entries[index].code.size(), '0');
    }
    return true;
}

std::vector<Entry> build_entries(const std::vector<unsigned char>& input) {
    std::array<std::uint64_t, 256> frequencies{};
    for (unsigned char value : input) ++frequencies[value];

    std::vector<HuffmanNode> nodes;
    std::priority_queue<QueueItem, std::vector<QueueItem>, QueueGreater> queue;
    for (int symbol = 0; symbol < 256; ++symbol) {
        if (!frequencies[symbol]) continue;
        const int node = static_cast<int>(nodes.size());
        nodes.push_back({frequencies[symbol], symbol, -1, -1, symbol});
        queue.push({frequencies[symbol], symbol, node});
    }

    std::array<unsigned, 256> lengths{};
    if (queue.size() == 1) {
        lengths[nodes[queue.top().node].symbol] = 1;
    } else if (!queue.empty()) {
        while (queue.size() > 1) {
            const QueueItem left = queue.top();
            queue.pop();
            const QueueItem right = queue.top();
            queue.pop();
            const int node = static_cast<int>(nodes.size());
            nodes.push_back({
                left.frequency + right.frequency,
                -1,
                left.node,
                right.node,
                std::min(left.minimum_symbol, right.minimum_symbol),
            });
            queue.push({nodes.back().frequency, nodes.back().minimum_symbol, node});
        }

        std::function<void(int, unsigned)> visit = [&](int node, unsigned depth) {
            if (nodes[node].symbol >= 0) {
                lengths[nodes[node].symbol] = depth;
                return;
            }
            visit(nodes[node].left, depth + 1);
            visit(nodes[node].right, depth + 1);
        };
        visit(queue.top().node, 0);
    }

    std::vector<Entry> entries;
    for (int symbol = 0; symbol < 256; ++symbol) {
        if (lengths[symbol]) {
            entries.push_back({static_cast<unsigned char>(symbol),
                               static_cast<unsigned char>(lengths[symbol]), {}});
        }
    }
    std::sort(entries.begin(), entries.end(), [](const Entry& left,
                                                  const Entry& right) {
        if (left.length != right.length) return left.length < right.length;
        return left.symbol < right.symbol;
    });
    assign_canonical_codes(entries);
    return entries;
}

bool pack_file(const char* source_path, const char* archive_path) {
    std::vector<unsigned char> input;
    if (!read_file(source_path, input)) return false;
    std::vector<Entry> entries = build_entries(input);
    std::array<std::string, 256> codes;
    for (const Entry& entry : entries) codes[entry.symbol] = entry.code;

    std::uint64_t bit_count = 0;
    for (unsigned char value : input) bit_count += codes[value].size();

    std::vector<unsigned char> archive{'G', 'P', 'H', '1'};
    append_u64(archive, input.size());
    append_u16(archive, static_cast<std::uint16_t>(entries.size()));
    for (const Entry& entry : entries) {
        archive.push_back(entry.symbol);
        archive.push_back(entry.length);
    }
    append_u64(archive, bit_count);

    unsigned char current = 0;
    unsigned used = 0;
    for (unsigned char value : input) {
        for (char character : codes[value]) {
            current = static_cast<unsigned char>(
                (current << 1) | static_cast<unsigned>(character - '0'));
            if (++used == 8) {
                archive.push_back(current);
                current = 0;
                used = 0;
            }
        }
    }
    if (used) archive.push_back(static_cast<unsigned char>(current << (8 - used)));
    return write_file(archive_path, archive);
}

bool unpack_file(const char* archive_path, const char* target_path) {
    std::vector<unsigned char> archive;
    if (!read_file(archive_path, archive) || archive.size() < 22
        || archive[0] != 'G' || archive[1] != 'P'
        || archive[2] != 'H' || archive[3] != '1') return false;

    std::size_t position = 4;
    std::uint64_t original_size = 0;
    std::uint16_t distinct = 0;
    if (!take_u64(archive, position, original_size)
        || !take_u16(archive, position, distinct) || distinct > 256) return false;

    std::array<bool, 256> seen{};
    std::vector<Entry> entries;
    for (std::uint16_t index = 0; index < distinct; ++index) {
        if (position > archive.size() || archive.size() - position < 2) return false;
        Entry entry{archive[position], archive[position + 1], {}};
        position += 2;
        if (entry.length == 0 || seen[entry.symbol]) return false;
        if (!entries.empty()
            && (entry.length < entries.back().length
                || (entry.length == entries.back().length
                    && entry.symbol <= entries.back().symbol))) return false;
        seen[entry.symbol] = true;
        entries.push_back(entry);
    }

    std::uint64_t bit_count = 0;
    if (!take_u64(archive, position, bit_count)) return false;
    const std::uint64_t byte_count = bit_count / 8 + (bit_count % 8 != 0);
    if (byte_count != archive.size() - position) return false;
    if (distinct == 0) {
        if (original_size != 0 || bit_count != 0) return false;
        return write_file(target_path, {});
    }
    if (!assign_canonical_codes(entries)) return false;

    std::vector<TrieNode> trie(1);
    for (const Entry& entry : entries) {
        int node = 0;
        for (char character : entry.code) {
            const int bit = character - '0';
            if (trie[node].symbol != -1) return false;
            if (trie[node].child[bit] == -1) {
                trie[node].child[bit] = static_cast<int>(trie.size());
                trie.emplace_back();
            }
            node = trie[node].child[bit];
        }
        if (trie[node].symbol != -1 || trie[node].child[0] != -1
            || trie[node].child[1] != -1) return false;
        trie[node].symbol = entry.symbol;
    }

    if (bit_count % 8) {
        const unsigned unused = 8 - static_cast<unsigned>(bit_count % 8);
        if ((archive.back() & ((1U << unused) - 1U)) != 0) return false;
    }

    std::vector<unsigned char> output;
    if (original_size > output.max_size()) return false;
    output.reserve(static_cast<std::size_t>(original_size));
    int node = 0;
    for (std::uint64_t bit_index = 0; bit_index < bit_count; ++bit_index) {
        const int bit = (archive[position + static_cast<std::size_t>(bit_index / 8)]
                         >> (7 - bit_index % 8)) & 1;
        node = trie[node].child[bit];
        if (node == -1) return false;
        if (trie[node].symbol != -1) {
            if (output.size() >= original_size) return false;
            output.push_back(static_cast<unsigned char>(trie[node].symbol));
            node = 0;
        }
    }
    if (node != 0 || output.size() != original_size) return false;
    return write_file(target_path, output);
}

int main(int argc, char** argv) {
    if (argc != 4) return 2;
    const std::string mode = argv[1];
    if (mode == "pack") return pack_file(argv[2], argv[3]) ? 0 : 3;
    if (mode == "unpack") return unpack_file(argv[2], argv[3]) ? 0 : 4;
    return 5;
}
"""


class RegistryTests(unittest.TestCase):
    def test_registry_contains_exactly_the_tester_required_tasks(self):
        self.assertEqual(
            {task_id: maximum for task_id, (maximum, _) in chapter.TASKS.items()},
            EXPECTED_TASKS,
        )
        self.assertEqual(
            set(chapter.TASK_CASES),
            set(EXPECTED_TASKS) - {2753},
        )

    def test_each_case_task_has_one_group_per_five_points(self):
        for task_id, maximum in EXPECTED_TASKS.items():
            if task_id == 2753:
                continue
            with self.subTest(task_id=task_id):
                groups = chapter.TASK_CASES[task_id]
                self.assertEqual(len(groups), maximum // 5)
                self.assertTrue(all(groups))
                for group in groups:
                    for case in group:
                        self.assertIn("input", case)
                        self.assertIn("expected", case)
                        self.assertGreater(case["time_limit"], 0)

    def test_reference_outputs_award_full_credit_for_every_case_task(self):
        for task_id, maximum in EXPECTED_TASKS.items():
            if task_id == 2753:
                continue
            with self.subTest(task_id=task_id):
                groups = chapter.TASK_CASES[task_id]
                runner = ReplayRunner(groups)
                points, comment = chapter.TASKS[task_id][1](runner, "")
                self.assertEqual(points, maximum)
                self.assertIn(f"{maximum}/{maximum}", comment)
                self.assertEqual(
                    len(runner.calls),
                    sum(len(group) for group in groups),
                )

    def test_wrong_output_awards_no_credit_for_every_case_task(self):
        for task_id in set(EXPECTED_TASKS) - {2753}:
            with self.subTest(task_id=task_id):
                points, _ = chapter.TASKS[task_id][1](WrongRunner(), "")
                self.assertEqual(points, 0)

    def test_hidden_suite_has_deterministic_random_and_stress_inputs(self):
        cases = [
            case
            for groups in chapter.TASK_CASES.values()
            for group in groups
            for case in group
        ]
        kinds = {case["kind"] for case in cases}
        self.assertEqual(kinds, {"hidden", "random", "stress"})
        self.assertGreaterEqual(
            sum(case["kind"] == "random" for case in cases),
            8,
        )
        for task_id, groups in chapter.TASK_CASES.items():
            with self.subTest(task_id=task_id):
                self.assertTrue(
                    any(
                        case["kind"] == "stress"
                        for group in groups
                        for case in group
                    )
                )

    def test_complexity_cases_are_materially_large(self):
        minimum_input_sizes = {
            2721: 400000,
            2722: 500000,
            2731: 500000,
            2734: 500000,
            2735: 1000000,
            2743: 200000,
            2745: 900000,
            2751: 100000,
        }
        for task_id, minimum in minimum_input_sizes.items():
            stress = [
                case
                for group in chapter.TASK_CASES[task_id]
                for case in group
                if case["kind"] == "stress"
            ]
            with self.subTest(task_id=task_id):
                self.assertTrue(stress)
                self.assertGreaterEqual(max(map(lambda case: len(case["input"]), stress)), minimum)

    def test_log_whitespace_and_pagerank_use_special_comparators(self):
        log_cases = [
            case
            for group in chapter.TASK_CASES[2718]
            for case in group
            if "  " in case["expected"]
        ]
        self.assertTrue(log_cases)
        self.assertTrue(
            all(case.get("comparator") is exact_text_equal for case in log_cases)
        )
        self.assertIs(chapter.TASK_COMPARATORS[2742], float_tokens_equal)
        self.assertIs(chapter.TASK_COMPARATORS[2743], float_tokens_equal)
        self.assertTrue(
            float_tokens_equal("1 0.3333334", "1 0.333333", tolerance=1e-6)
        )

    def test_canonical_code_cases_require_the_bits_confirmation(self):
        for group in chapter.TASK_CASES[2752]:
            for case in group:
                self.assertIn("\nbits ", case["expected"])

    def test_training_stress_uses_the_largest_legal_64_bit_sum(self):
        stress = next(
            case
            for group in chapter.TASK_CASES[2728]
            for case in group
            if case["kind"] == "stress"
        )
        input_lines = stress["input"].splitlines()
        count = int(input_lines[0])
        distances = list(map(int, input_lines[1].split()))
        total = int(stress["expected"].splitlines()[0])

        self.assertEqual(count, 200000)
        self.assertEqual(len(distances), count)
        self.assertTrue(all(value == 100000 for value in distances))
        self.assertEqual(total, 20_000_000_000)
        self.assertGreater(total, 2**31 - 1)
        self.assertEqual(stress["capture_limit"], 2 * 1024 * 1024)

    def test_reducto_stress_respects_the_published_edge_limit(self):
        stress = next(
            case
            for group in chapter.TASK_CASES[2741]
            for case in group
            if case["kind"] == "stress"
        )
        node_count, edge_count = map(int, stress["input"].splitlines()[0].split())

        self.assertEqual((node_count, edge_count), (28, 378))
        self.assertLessEqual(edge_count, 400)
        self.assertEqual(edge_count, node_count * (node_count - 1) // 2)

    def test_metro_cases_require_undirected_reverse_traversal(self):
        reverse_case = next(
            case
            for group in chapter.TASK_CASES[2747]
            for case in group
            if case["input"].endswith("3 1\n")
        )

        self.assertEqual(reverse_case["expected"], "13")
        self.assertIn("1 2 1 4\n2 3 2 4", reverse_case["input"])


class HuffmanValidatorTests(unittest.TestCase):
    ALTERNATIVE_LENGTHS = (
        "a 5 1\n"
        "r 2 2\n"
        "b 2 3\n"
        "c 1 4\n"
        "d 1 4\n"
        "88 23"
    )
    ALTERNATIVE_CANONICAL = (
        "a 0\n"
        "b 100\n"
        "c 101\n"
        "d 110\n"
        "r 111\n"
        "bits 23"
    )

    def test_length_validator_accepts_any_optimal_tie_resolution(self):
        compare = chapter._huffman_report_validator("abracadabra")

        self.assertTrue(compare(self.ALTERNATIVE_LENGTHS, "ignored"))
        self.assertTrue(compare(chapter._huffman_report("abracadabra"), "ignored"))

    def test_length_validator_rejects_bad_or_suboptimal_reports(self):
        compare = chapter._huffman_report_validator("abracadabra")
        bad_reports = (
            self.ALTERNATIVE_LENGTHS.replace("a 5 1", "a 4 1"),
            self.ALTERNATIVE_LENGTHS.replace("88 23", "88 24"),
            "a 5 2\nb 2 2\nr 2 2\nc 1 3\nd 1 3\n88 24",
            "a 5 1\nb 2 3\nc 1 4\nd 1 4\n88 23",
            "a 5 1\nb 2 3\nr 2 2\nc 1 4\nd 1 4\n88 23",
        )
        for report in bad_reports:
            with self.subTest(report=report):
                self.assertFalse(compare(report, "ignored"))

    def test_canonical_validator_accepts_an_alternative_optimal_tree(self):
        compare = chapter._canonical_report_validator("abracadabra")

        self.assertTrue(compare(self.ALTERNATIVE_CANONICAL, "ignored"))
        self.assertTrue(
            compare(
                "a 0\nr 10\nb 110\nc 1110\nd 1111\nbits 23",
                "ignored",
            )
        )

    def test_canonical_validator_rejects_noncanonical_and_suboptimal_codes(self):
        compare = chapter._canonical_report_validator("abracadabra")
        bad_reports = (
            self.ALTERNATIVE_CANONICAL.replace("b 100\nc 101", "b 101\nc 100"),
            self.ALTERNATIVE_CANONICAL.replace("bits 23", "bits 24"),
            self.ALTERNATIVE_CANONICAL.replace("r 111", "r 11x"),
            "a 00\nb 01\nr 10\nc 110\nd 111\nbits 24",
        )
        for report in bad_reports:
            with self.subTest(report=report):
                self.assertFalse(compare(report, "ignored"))

    def test_handlers_award_full_credit_for_alternative_optimal_outputs(self):
        alternatives = {
            2751: self.ALTERNATIVE_LENGTHS,
            2752: self.ALTERNATIVE_CANONICAL,
        }
        for task_id, alternative in alternatives.items():
            with self.subTest(task_id=task_id):
                groups = chapter.TASK_CASES[task_id]
                runner = ReplayRunner(groups)
                runner.answers["abracadabra\n"] = alternative
                points, _ = chapter.TASKS[task_id][1](runner, "")
                self.assertEqual(points, EXPECTED_TASKS[task_id])


class ArchiveHarnessTests(unittest.TestCase):
    def test_archive_handler_round_trips_every_payload_group(self):
        runner = ArchiveRunner()

        points, comment = chapter.TASKS[2753][1](runner, "student source")

        self.assertEqual(points, 20)
        self.assertIn("20/20", comment)
        self.assertEqual(
            len(runner.calls),
            sum(map(len, chapter.ARCHIVE_PAYLOAD_GROUPS)),
        )
        for source, input_data, time_limit in runner.calls:
            self.assertEqual(input_data, "")
            self.assertEqual(time_limit, 8)
            self.assertIn("'/code/program' pack", source)
            self.assertIn("'/code/program' unpack", source)
            self.assertIn("validate_gph1", source)
            self.assertIn("optimal_huffman_cost", source)
            self.assertIn("reference_unpacked", source)
            self.assertIn("corrupt_unpacked", source)
            self.assertIn("restored_bytes == expected", source)
            self.assertIn("bit_count", source)
            self.assertIn("trie", source)
            self.assertIn("std::ios::binary", source)

    def test_archive_suite_covers_empty_single_all_bytes_and_compression(self):
        payloads = [
            payload
            for group in chapter.ARCHIVE_PAYLOAD_GROUPS
            for payload in group
        ]
        self.assertIn(b"", payloads)
        self.assertTrue(any(payload and len(set(payload)) == 1 for payload in payloads))
        self.assertTrue(any(set(payload) == set(range(256)) for payload in payloads))
        compression_harness = chapter._archive_harness(
            chapter.ARCHIVE_PAYLOAD_GROUPS[-1][0],
            40000,
        )
        self.assertIn("archive_bytes.size() < 40000ULL", compression_harness)

        skewed = chapter.ARCHIVE_PAYLOAD_GROUPS[-1][0]
        self.assertEqual(
            Counter(skewed),
            Counter({ord("a"): 70000, ord("b"): 10000,
                     ord("c"): 10000, ord("d"): 10000}),
        )
        transitions = sum(left != right for left, right in zip(skewed, skewed[1:]))
        self.assertGreater(transitions, 10000)
        self.assertLess(len(chapter._build_gph1_archive(skewed)), 40000)

    def test_reference_builder_uses_the_exact_gph1_layout(self):
        payload = bytes(range(256))
        archive = chapter._build_gph1_archive(payload)

        self.assertEqual(archive[:4], b"GPH1")
        original_size, distinct = struct.unpack_from("<QH", archive, 4)
        self.assertEqual(original_size, 256)
        self.assertEqual(distinct, 256)

        table_start = 14
        entries = [
            (archive[table_start + 2 * index], archive[table_start + 2 * index + 1])
            for index in range(distinct)
        ]
        self.assertEqual(entries, sorted(entries, key=lambda item: (item[1], item[0])))
        self.assertEqual({symbol for symbol, _ in entries}, set(range(256)))
        self.assertTrue(all(length == 8 for _, length in entries))

        bit_count_offset = table_start + 2 * distinct
        bit_count = struct.unpack_from("<Q", archive, bit_count_offset)[0]
        packed = archive[bit_count_offset + 8:]
        self.assertEqual(bit_count, 2048)
        self.assertEqual(len(packed), (bit_count + 7) // 8)
        self.assertEqual(packed, payload)

    def test_reference_builder_handles_empty_and_msb_first_padding(self):
        empty = chapter._build_gph1_archive(b"")
        self.assertEqual(len(empty), 22)
        self.assertEqual(struct.unpack_from("<QH", empty, 4), (0, 0))
        self.assertEqual(struct.unpack_from("<Q", empty, 14)[0], 0)

        archive = chapter._build_gph1_archive(b"aba")
        self.assertEqual(struct.unpack_from("<QH", archive, 4), (3, 2))
        self.assertEqual(archive[14:18], bytes((ord("a"), 1, ord("b"), 1)))
        self.assertEqual(struct.unpack_from("<Q", archive, 18)[0], 3)
        self.assertEqual(archive[26:], b"\x40")

    def test_archive_harness_randomizes_all_temporary_paths(self):
        first = chapter._archive_harness(b"paths")
        second = chapter._archive_harness(b"paths")
        first_suffixes = set(re.findall(r"__gp_([0-9a-f]{32})\.", first))
        second_suffixes = set(re.findall(r"__gp_([0-9a-f]{32})\.", second))

        self.assertEqual(len(first_suffixes), 5)
        self.assertEqual(len(second_suffixes), 5)
        self.assertTrue(first_suffixes.isdisjoint(second_suffixes))
        self.assertNotIn("__gp_archive_source.bin", first)

    @unittest.skipUnless(
        shutil.which("g++") and os.name != "nt",
        "requires a POSIX g++ toolchain",
    )
    def test_generated_harness_compiles_accepts_gph1_and_rejects_raw_copy(self):
        compiler = shutil.which("g++")
        payload = b"abracadabra\x00\xffabracadabra"
        with tempfile.TemporaryDirectory(prefix="grade8-gph1-") as raw_directory:
            directory = Path(raw_directory)
            correct_program = directory / "correct-archiver"
            raw_copy_program = directory / "raw-copy-archiver"
            correct_harness = directory / "correct-harness"
            raw_copy_harness = directory / "raw-copy-harness"

            _compile_cpp(
                compiler,
                GPH1_REFERENCE_ARCHIVER_SOURCE,
                correct_program,
            )
            _compile_cpp(compiler, RAW_COPY_ARCHIVER_SOURCE, raw_copy_program)
            _compile_cpp(
                compiler,
                chapter._archive_harness(
                    payload,
                    program_path=str(correct_program),
                    work_directory=str(directory),
                ),
                correct_harness,
            )
            _compile_cpp(
                compiler,
                chapter._archive_harness(
                    payload,
                    program_path=str(raw_copy_program),
                    work_directory=str(directory),
                ),
                raw_copy_harness,
            )

            correct = subprocess.run(
                [str(correct_harness)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            raw_copy = subprocess.run(
                [str(raw_copy_harness)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(correct.returncode, 0, correct.stderr)
            self.assertEqual(correct.stdout.strip(), "OK")
            self.assertEqual(raw_copy.returncode, 0, raw_copy.stderr)
            self.assertEqual(raw_copy.stdout.strip(), "FAIL")

    def test_archive_mismatch_awards_no_credit(self):
        points, _ = chapter.TASKS[2753][1](ArchiveRunner(result="FAIL"), "")
        self.assertEqual(points, 0)

    def test_archive_student_failure_is_a_failed_criterion(self):
        points, _ = chapter.TASKS[2753][1](
            ArchiveRunner(error=SolutionException("student failed")),
            "",
        )
        self.assertEqual(points, 0)

    def test_archive_infrastructure_failure_is_not_hidden(self):
        with self.assertRaises(ExecutionException):
            chapter.TASKS[2753][1](
                ArchiveRunner(error=ExecutionException("docker failed")),
                "",
            )


if __name__ == "__main__":
    unittest.main()
