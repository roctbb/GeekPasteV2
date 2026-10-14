"""Hidden checks for the 2026 grade-8 STL and graph chapters.

The large inputs below are deterministic.  They are intentionally generated at
module import instead of being checked in as megabytes of opaque literals.
"""

from collections import Counter
import heapq
import itertools
import json
import random
import re
import struct
import uuid

from runner import SolutionException

from .grade8_2026_common import (
    finish_criteria,
    finish_groups,
    tokens_equal,
)


def _case(
    input_data,
    expected,
    *,
    time_limit=2,
    comparator=None,
    kind="hidden",
    capture_limit=None,
):
    case = {
        "input": input_data,
        "expected": expected,
        "time_limit": time_limit,
        "kind": kind,
    }
    if comparator is not None:
        case["comparator"] = comparator
    if capture_limit is not None:
        case["capture_limit"] = capture_limit
    return case


TASKS = {}
TASK_CASES = {}
TASK_COMPARATORS = {}


def _register(task_id, maximum, groups, comparator=tokens_equal):
    if len(groups) != maximum // 5:
        raise AssertionError(f"invalid criterion count for task {task_id}")
    TASK_CASES[task_id] = groups
    TASK_COMPARATORS[task_id] = comparator

    def handler(runner, _source_code):
        return finish_groups(task_id, maximum, runner, groups, comparator)

    TASKS[task_id] = (maximum, handler)


def _lines(items):
    return "\n".join(str(item) for item in items)


def _huffman_lengths_for_frequencies(frequencies):
    if not frequencies:
        return {}
    if len(frequencies) == 1:
        return {next(iter(frequencies)): 1}
    heap = []
    serial = itertools.count()
    for symbol, frequency in sorted(frequencies.items()):
        heapq.heappush(heap, (frequency, next(serial), symbol))
    while len(heap) > 1:
        left_frequency, _, left = heapq.heappop(heap)
        right_frequency, _, right = heapq.heappop(heap)
        heapq.heappush(
            heap,
            (left_frequency + right_frequency, next(serial), (left, right)),
        )
    lengths = {}

    def visit(node, depth):
        if not isinstance(node, tuple):
            lengths[node] = max(depth, 1)
            return
        visit(node[0], depth + 1)
        visit(node[1], depth + 1)

    visit(heap[0][2], 0)
    return lengths


def _huffman_lengths(text):
    return _huffman_lengths_for_frequencies(Counter(text))


def _optimal_huffman_cost(frequencies):
    weights = list(frequencies.values())
    if not weights:
        return 0
    if len(weights) == 1:
        return weights[0]
    heapq.heapify(weights)
    total = 0
    while len(weights) > 1:
        merged = heapq.heappop(weights) + heapq.heappop(weights)
        total += merged
        heapq.heappush(weights, merged)
    return total


def _lengths_form_complete_prefix_code(lengths):
    if not lengths:
        return True
    if len(lengths) == 1:
        return next(iter(lengths.values())) == 1
    maximum = max(lengths.values())
    if maximum <= 0 or maximum > len(lengths) - 1:
        return False
    return sum(1 << (maximum - length) for length in lengths.values()) == (
        1 << maximum
    )


def _parse_decimal(token):
    if not re.fullmatch(r"[0-9]+", token):
        raise ValueError("not a decimal integer")
    return int(token)


def _parse_symbol(label):
    if label == "space":
        return " "
    if re.fullmatch(r"[a-z]", label):
        return label
    raise ValueError("invalid symbol label")


def _output_lines(actual):
    value = str(actual)
    if len(value) > 8192:
        raise ValueError("output is too large")
    value = value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    if not value:
        return []
    lines = value.split("\n")
    if any(not line.strip() for line in lines):
        raise ValueError("blank output line")
    return lines


def _validate_optimal_lengths(frequencies, lengths):
    if set(lengths) != set(frequencies):
        return False
    if any(not isinstance(length, int) or length <= 0 for length in lengths.values()):
        return False
    if not _lengths_form_complete_prefix_code(lengths):
        return False
    weighted = sum(frequencies[symbol] * lengths[symbol] for symbol in frequencies)
    return weighted == _optimal_huffman_cost(frequencies)


def _huffman_report_validator(text):
    frequencies = Counter(text)

    def compare(actual, _expected):
        try:
            lines = _output_lines(actual)
            if len(lines) != len(frequencies) + 1:
                return False
            lengths = {}
            rows = []
            for line in lines[:-1]:
                parts = line.split()
                if len(parts) != 3:
                    return False
                symbol = _parse_symbol(parts[0])
                frequency = _parse_decimal(parts[1])
                length = _parse_decimal(parts[2])
                if symbol in lengths or frequencies.get(symbol) != frequency:
                    return False
                lengths[symbol] = length
                rows.append((symbol, frequency, length))
            if not _validate_optimal_lengths(frequencies, lengths):
                return False
            if rows != sorted(
                rows,
                key=lambda row: (row[2], -row[1], row[0]),
            ):
                return False
            totals = lines[-1].split()
            if len(totals) != 2:
                return False
            plain_bits, compressed_bits = map(_parse_decimal, totals)
            weighted = sum(
                frequencies[symbol] * lengths[symbol] for symbol in frequencies
            )
            return plain_bits == len(text) * 8 and compressed_bits == weighted
        except (TypeError, ValueError):
            return False

    return compare


def _canonical_report_validator(text):
    frequencies = Counter(text)

    def compare(actual, _expected):
        try:
            lines = _output_lines(actual)
            if len(lines) != len(frequencies) + 1:
                return False
            footer = lines[-1].split()
            if len(footer) != 2 or footer[0] != "bits":
                return False
            reported_bits = _parse_decimal(footer[1])
            rows = []
            lengths = {}
            submitted_codes = {}
            for line in lines[:-1]:
                parts = line.split()
                if len(parts) != 2 or not re.fullmatch(r"[01]+", parts[1]):
                    return False
                symbol = _parse_symbol(parts[0])
                if symbol in lengths:
                    return False
                code = parts[1]
                lengths[symbol] = len(code)
                submitted_codes[symbol] = code
                rows.append((symbol, len(code)))
            if not _validate_optimal_lengths(frequencies, lengths):
                return False
            if rows != sorted(rows, key=lambda row: (row[1], row[0])):
                return False

            code_value = 0
            previous_length = rows[0][1] if rows else 0
            for index, (symbol, length) in enumerate(rows):
                if index:
                    code_value = (code_value + 1) << (length - previous_length)
                if code_value >= (1 << length):
                    return False
                if submitted_codes[symbol] != f"{code_value:0{length}b}":
                    return False
                previous_length = length

            weighted = sum(
                frequencies[symbol] * lengths[symbol] for symbol in frequencies
            )
            return reported_bits == weighted
        except (TypeError, ValueError):
            return False

    return compare


def _huffman_report(text):
    frequencies = Counter(text)
    lengths = _huffman_lengths(text)
    order = sorted(
        frequencies,
        key=lambda symbol: (lengths[symbol], -frequencies[symbol], symbol),
    )
    rows = [
        f"{'space' if symbol == ' ' else symbol} "
        f"{frequencies[symbol]} {lengths[symbol]}"
        for symbol in order
    ]
    compressed = sum(frequencies[symbol] * lengths[symbol] for symbol in order)
    rows.append(f"{len(text) * 8} {compressed}")
    return _lines(rows)


def _canonical_report(text):
    frequencies = Counter(text)
    lengths = _huffman_lengths(text)
    order = sorted(frequencies, key=lambda symbol: (lengths[symbol], symbol))
    if not order:
        return "bits 0"
    rows = []
    code = 0
    previous_length = lengths[order[0]]
    compressed = 0
    for index, symbol in enumerate(order):
        length = lengths[symbol]
        if index:
            code = (code + 1) << (length - previous_length)
        rows.append(
            f"{'space' if symbol == ' ' else symbol} {code:0{length}b}"
        )
        compressed += frequencies[symbol] * length
        previous_length = length
    rows.append(f"bits {compressed}")
    return _lines(rows)


def _canonical_codes_from_lengths(lengths):
    order = sorted(lengths, key=lambda symbol: (lengths[symbol], symbol))
    if not order:
        return {}
    codes = {}
    code = 0
    previous_length = lengths[order[0]]
    for index, symbol in enumerate(order):
        length = lengths[symbol]
        if index:
            code = (code + 1) << (length - previous_length)
        if code >= 1 << length:
            raise ValueError("invalid canonical lengths")
        codes[symbol] = (code, length)
        previous_length = length
    return codes


def _build_gph1_archive(payload):
    frequencies = Counter(payload)
    lengths = _huffman_lengths_for_frequencies(frequencies)
    entries = sorted(lengths.items(), key=lambda item: (item[1], item[0]))
    codes = _canonical_codes_from_lengths(lengths)
    bit_count = sum(frequencies[symbol] * length for symbol, length in entries)

    archive = bytearray(b"GPH1")
    archive.extend(struct.pack("<QH", len(payload), len(entries)))
    for symbol, length in entries:
        archive.extend((symbol, length))
    archive.extend(struct.pack("<Q", bit_count))

    current = 0
    used = 0
    for symbol in payload:
        code, length = codes[symbol]
        for shift in range(length - 1, -1, -1):
            current = (current << 1) | ((code >> shift) & 1)
            used += 1
            if used == 8:
                archive.append(current)
                current = 0
                used = 0
    if used:
        archive.append(current << (8 - used))
    return bytes(archive)


def _shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _archive_harness(
    payload,
    maximum_archive_size=None,
    *,
    program_path="/code/program",
    work_directory="/code",
):
    directory = work_directory.rstrip("/\\").replace("\\", "/")
    program = program_path.replace("\\", "/")

    def temporary(extension):
        return f"{directory}/__gp_{uuid.uuid4().hex}{extension}"

    paths = {
        "source": temporary(".bin"),
        "archive": temporary(".gph"),
        "reference": temporary(".gph"),
        "corrupt": temporary(".gph"),
        "restored": temporary(".bin"),
    }

    def command(mode, source, target):
        return (
            f"{_shell_quote(program)} {mode} {_shell_quote(source)} "
            f"{_shell_quote(target)} >/dev/null 2>&1"
        )

    replacements = {
        "__SOURCE_PATH__": json.dumps(paths["source"]),
        "__ARCHIVE_PATH__": json.dumps(paths["archive"]),
        "__REFERENCE_PATH__": json.dumps(paths["reference"]),
        "__CORRUPT_PATH__": json.dumps(paths["corrupt"]),
        "__RESTORED_PATH__": json.dumps(paths["restored"]),
        "__REFERENCE_UNPACK_COMMAND__": json.dumps(
            command("unpack", paths["reference"], paths["restored"])
        ),
        "__CORRUPT_UNPACK_COMMAND__": json.dumps(
            command("unpack", paths["corrupt"], paths["restored"])
        ),
        "__PACK_COMMAND__": json.dumps(
            command("pack", paths["source"], paths["archive"])
        ),
        "__PACKED_UNPACK_COMMAND__": json.dumps(
            command("unpack", paths["archive"], paths["restored"])
        ),
        "__EXPECTED_VALUES__": ",".join(str(value) for value in payload),
        "__REFERENCE_VALUES__": ",".join(
            str(value) for value in _build_gph1_archive(payload)
        ),
        "__SIZE_CHECK__": (
            "true"
            if maximum_archive_size is None
            else f"archive_bytes.size() < {maximum_archive_size}ULL"
        ),
    }

    source = r"""
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <limits>
#include <queue>
#include <string>
#include <vector>

struct Entry {
    unsigned char symbol = 0;
    unsigned char length = 0;
    std::string code;
};

struct TrieNode {
    int child[2] = {-1, -1};
    int symbol = -1;
};

bool write_file(const char* path, const std::vector<unsigned char>& data) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) {
        return false;
    }
    if (!data.empty()) {
        output.write(
            reinterpret_cast<const char*>(data.data()),
            static_cast<std::streamsize>(data.size())
        );
    }
    return static_cast<bool>(output);
}

bool read_file(const char* path, std::vector<unsigned char>& data) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return false;
    }
    data.assign(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>()
    );
    return !input.bad();
}

bool take_u16(
    const std::vector<unsigned char>& data,
    std::size_t& position,
    std::uint16_t& value
) {
    if (position > data.size() || data.size() - position < 2) {
        return false;
    }
    value = static_cast<std::uint16_t>(data[position])
        | (static_cast<std::uint16_t>(data[position + 1]) << 8);
    position += 2;
    return true;
}

bool take_u64(
    const std::vector<unsigned char>& data,
    std::size_t& position,
    std::uint64_t& value
) {
    if (position > data.size() || data.size() - position < 8) {
        return false;
    }
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

std::uint64_t optimal_huffman_cost(
    const std::array<std::uint64_t, 256>& frequencies,
    std::size_t distinct
) {
    std::priority_queue<
        std::uint64_t,
        std::vector<std::uint64_t>,
        std::greater<std::uint64_t>
    > queue;
    for (std::uint64_t frequency : frequencies) {
        if (frequency) {
            queue.push(frequency);
        }
    }
    if (distinct == 0) {
        return 0;
    }
    if (distinct == 1) {
        return queue.top();
    }
    std::uint64_t total = 0;
    while (queue.size() > 1) {
        const std::uint64_t left = queue.top();
        queue.pop();
        const std::uint64_t right = queue.top();
        queue.pop();
        const std::uint64_t merged = left + right;
        total += merged;
        queue.push(merged);
    }
    return total;
}

bool validate_gph1(
    const std::vector<unsigned char>& archive,
    const std::vector<unsigned char>& expected
) {
    if (archive.size() < 22 || archive[0] != 'G' || archive[1] != 'P'
        || archive[2] != 'H' || archive[3] != '1') {
        return false;
    }
    std::size_t position = 4;
    std::uint64_t original_size = 0;
    std::uint16_t distinct = 0;
    if (!take_u64(archive, position, original_size)
        || !take_u16(archive, position, distinct)
        || distinct > 256
        || original_size != expected.size()) {
        return false;
    }

    std::array<std::uint64_t, 256> frequencies{};
    for (unsigned char value : expected) {
        ++frequencies[value];
    }
    std::size_t expected_distinct = 0;
    for (std::uint64_t frequency : frequencies) {
        expected_distinct += frequency != 0;
    }
    if (distinct != expected_distinct) {
        return false;
    }

    std::array<bool, 256> seen{};
    std::array<std::uint16_t, 256> length_counts{};
    std::vector<Entry> entries;
    entries.reserve(distinct);
    unsigned maximum_length = 0;
    for (std::uint16_t index = 0; index < distinct; ++index) {
        if (position > archive.size() || archive.size() - position < 2) {
            return false;
        }
        Entry entry;
        entry.symbol = archive[position++];
        entry.length = archive[position++];
        if (entry.length == 0 || seen[entry.symbol] || !frequencies[entry.symbol]) {
            return false;
        }
        if (!entries.empty()) {
            const Entry& previous = entries.back();
            if (entry.length < previous.length
                || (entry.length == previous.length
                    && entry.symbol <= previous.symbol)) {
                return false;
            }
        }
        seen[entry.symbol] = true;
        ++length_counts[entry.length];
        maximum_length = std::max(maximum_length, static_cast<unsigned>(entry.length));
        entries.push_back(entry);
    }

    std::uint64_t bit_count = 0;
    if (!take_u64(archive, position, bit_count)) {
        return false;
    }
    const std::uint64_t payload_size = bit_count / 8 + (bit_count % 8 != 0);
    if (payload_size != archive.size() - position) {
        return false;
    }
    if (distinct == 0) {
        return original_size == 0 && bit_count == 0 && position == archive.size();
    }
    if (distinct == 1) {
        if (entries[0].length != 1) {
            return false;
        }
    } else {
        std::uint64_t slots = 1;
        std::size_t remaining = distinct;
        for (unsigned depth = 1; depth <= maximum_length; ++depth) {
            if (slots > 256) {
                return false;
            }
            slots *= 2;
            if (length_counts[depth] > slots) {
                return false;
            }
            slots -= length_counts[depth];
            remaining -= length_counts[depth];
            if (slots > remaining) {
                return false;
            }
        }
        if (slots != 0 || remaining != 0) {
            return false;
        }
    }

    std::uint64_t weighted = 0;
    for (const Entry& entry : entries) {
        weighted += frequencies[entry.symbol] * entry.length;
    }
    if (weighted != bit_count
        || weighted != optimal_huffman_cost(frequencies, distinct)) {
        return false;
    }

    if (!entries.empty()) {
        entries[0].code.assign(entries[0].length, '0');
        for (std::size_t index = 1; index < entries.size(); ++index) {
            entries[index].code = entries[index - 1].code;
            if (!increment_binary(entries[index].code)) {
                return false;
            }
            if (entries[index].length < entries[index].code.size()) {
                return false;
            }
            entries[index].code.append(
                entries[index].length - entries[index].code.size(),
                '0'
            );
        }
    }

    std::vector<TrieNode> trie(1);
    for (const Entry& entry : entries) {
        int node = 0;
        for (char character : entry.code) {
            if (trie[node].symbol != -1) {
                return false;
            }
            const int bit = character - '0';
            if (trie[node].child[bit] == -1) {
                trie[node].child[bit] = static_cast<int>(trie.size());
                trie.emplace_back();
            }
            node = trie[node].child[bit];
        }
        if (trie[node].symbol != -1 || trie[node].child[0] != -1
            || trie[node].child[1] != -1) {
            return false;
        }
        trie[node].symbol = entry.symbol;
    }

    if (bit_count % 8) {
        const unsigned unused = 8 - static_cast<unsigned>(bit_count % 8);
        const unsigned mask = (1U << unused) - 1U;
        if ((archive.back() & mask) != 0) {
            return false;
        }
    }

    std::size_t produced = 0;
    int node = 0;
    for (std::uint64_t bit_index = 0; bit_index < bit_count; ++bit_index) {
        const unsigned char byte = archive[
            position + static_cast<std::size_t>(bit_index / 8)
        ];
        const int bit = (byte >> (7 - bit_index % 8)) & 1;
        node = trie[node].child[bit];
        if (node == -1) {
            return false;
        }
        if (trie[node].symbol != -1) {
            if (produced >= expected.size()
                || expected[produced] != trie[node].symbol) {
                return false;
            }
            ++produced;
            node = 0;
        }
    }
    return node == 0 && produced == expected.size();
}

int main() {
    const char* source_path = __SOURCE_PATH__;
    const char* archive_path = __ARCHIVE_PATH__;
    const char* reference_path = __REFERENCE_PATH__;
    const char* corrupt_path = __CORRUPT_PATH__;
    const char* restored_path = __RESTORED_PATH__;
    const std::vector<unsigned char> expected = {__EXPECTED_VALUES__};
    const std::vector<unsigned char> reference_archive = {__REFERENCE_VALUES__};
    bool ok = true;

    // Verify unpack independently before the student's pack process can leave sidecars.
    ok = write_file(reference_path, reference_archive) && ok;
    std::remove(restored_path);
    const int reference_unpacked = std::system(__REFERENCE_UNPACK_COMMAND__);
    std::vector<unsigned char> restored_bytes;
    ok = reference_unpacked == 0
        && read_file(restored_path, restored_bytes)
        && restored_bytes == expected
        && ok;

    // A bad magic must be rejected with a non-zero exit status.
    std::vector<unsigned char> corrupt_archive = reference_archive;
    if (!corrupt_archive.empty()) {
        corrupt_archive[0] ^= 0x01;
    }
    ok = write_file(corrupt_path, corrupt_archive) && ok;
    std::remove(restored_path);
    const int corrupt_unpacked = std::system(__CORRUPT_UNPACK_COMMAND__);
    ok = corrupt_unpacked != 0 && ok;

    ok = write_file(source_path, expected) && ok;
    const int packed = std::system(__PACK_COMMAND__);
    std::vector<unsigned char> archive_bytes;
    ok = packed == 0
        && read_file(archive_path, archive_bytes)
        && validate_gph1(archive_bytes, expected)
        && (__SIZE_CHECK__)
        && ok;

    // The packed archive must also be consumable by the student's own unpacker.
    std::remove(source_path);
    std::remove(restored_path);
    const int unpacked = std::system(__PACKED_UNPACK_COMMAND__);
    restored_bytes.clear();
    ok = unpacked == 0
        && read_file(restored_path, restored_bytes)
        && restored_bytes == expected
        && ok;

    std::remove(source_path);
    std::remove(archive_path);
    std::remove(reference_path);
    std::remove(corrupt_path);
    std::remove(restored_path);
    std::cout << (ok ? "OK" : "FAIL");
}
"""
    for marker, value in replacements.items():
        source = source.replace(marker, value)
    return source


def _shuffled_archive_payload():
    values = list(b"a" * 70000 + b"b" * 10000 + b"c" * 10000 + b"d" * 10000)
    random.Random(2753).shuffle(values)
    return bytes(values)


ARCHIVE_PAYLOAD_GROUPS = (
    (b"abracadabra", b"the quick brown fox jumps over the lazy dog\n"),
    (b"", b"x" * 4096),
    (bytes(range(256)), bytes((index * 73 + 19) % 256 for index in range(8192))),
    (_shuffled_archive_payload(),),
)


def _check_archive_group(runner, payloads, maximum_archive_size=None):
    for payload in payloads:
        try:
            output = runner.run_source(
                _archive_harness(payload, maximum_archive_size),
                "",
                8,
            )
        except SolutionException:
            return False
        if not tokens_equal(output, "OK"):
            return False
    return True


def _check_2753(runner, _source_code):
    criteria = []
    for index, payloads in enumerate(ARCHIVE_PAYLOAD_GROUPS):
        maximum_size = 40000 if index == 3 else None
        criteria.append(
            (
                _check_archive_group(runner, payloads, maximum_size),
                f"группа проверок архива {index + 1}",
            )
        )
    return finish_criteria(2753, 20, criteria)


_maze_blocked_stress = []
for _row in range(1000):
    _line = ["."] * 1000
    _line[500] = "#"
    _maze_blocked_stress.append("".join(_line))
_maze_blocked_stress[0] = "S" + _maze_blocked_stress[0][1:]
_maze_blocked_stress[-1] = _maze_blocked_stress[-1][:-1] + "F"


_huffman_stress_text = (
    "a" * 51000
    + "b" * 25000
    + "c" * 13000
    + "d" * 7000
    + "e" * 4000
)


_register(
    2751,
    15,
    (
        (
            _case(
                "aaaaabbcd\n",
                _huffman_report("aaaaabbcd"),
                comparator=_huffman_report_validator("aaaaabbcd"),
            ),
            _case(
                "abracadabra\n",
                _huffman_report("abracadabra"),
                comparator=_huffman_report_validator("abracadabra"),
            ),
        ),
        (
            _case(
                "abc abc\n",
                _huffman_report("abc abc"),
                comparator=_huffman_report_validator("abc abc"),
            ),
            _case(
                "aaaa\n",
                _huffman_report("aaaa"),
                comparator=_huffman_report_validator("aaaa"),
            ),
        ),
        (
            _case(
                _huffman_stress_text + "\n",
                _huffman_report(_huffman_stress_text),
                time_limit=4,
                comparator=_huffman_report_validator(_huffman_stress_text),
                kind="stress",
            ),
        ),
    ),
)


_register(
    2752,
    10,
    (
        (
            _case(
                "aaaaabbcd\n",
                _canonical_report("aaaaabbcd"),
                comparator=_canonical_report_validator("aaaaabbcd"),
            ),
            _case(
                "abc abc\n",
                _canonical_report("abc abc"),
                comparator=_canonical_report_validator("abc abc"),
            ),
            _case(
                "abracadabra\n",
                "a 0\nr 10\nb 110\nc 1110\nd 1111\nbits 23",
                comparator=_canonical_report_validator("abracadabra"),
            ),
        ),
        (
            _case(
                "xxxx\n",
                _canonical_report("xxxx"),
                comparator=_canonical_report_validator("xxxx"),
            ),
            _case(
                _huffman_stress_text + "\n",
                _canonical_report(_huffman_stress_text),
                time_limit=4,
                comparator=_canonical_report_validator(_huffman_stress_text),
                kind="stress",
            ),
        ),
    ),
)


TASKS[2753] = (20, _check_2753)
