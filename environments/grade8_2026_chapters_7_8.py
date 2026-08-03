"""Hidden checks for the 2026 grade-8 STL and graph chapters.

The large inputs below are deterministic.  They are intentionally generated at
module import instead of being checked in as megabytes of opaque literals.
"""

from collections import Counter, deque
import heapq
import itertools
import json
import random
import re
import struct
import uuid

from runner import SolutionException

from .grade8_2026_common import (
    exact_text_equal,
    finish_criteria,
    finish_groups,
    float_tokens_equal,
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


def _todo_random_case():
    rng = random.Random(2720)
    todos = []
    commands = []
    output = []
    next_name = 0
    for _ in range(1200):
        action = rng.randrange(6)
        if action == 0 or not todos:
            name = f"job{next_name % 97}"
            next_name += 1
            todos.append(name)
            commands.append(f"add {name}")
        elif action == 1:
            position = rng.randint(1, len(todos) + 1)
            name = f"urgent{next_name}"
            next_name += 1
            todos.insert(position - 1, name)
            commands.append(f"insert {position} {name}")
        elif action == 2:
            position = rng.randint(1, len(todos))
            output.append(todos.pop(position - 1))
            commands.append(f"done {position}")
        elif action == 3:
            position = rng.randint(2, len(todos)) if len(todos) > 1 else 1
            commands.append(f"up {position}")
            if position == 1:
                output.append("error")
            else:
                todos[position - 2], todos[position - 1] = (
                    todos[position - 1],
                    todos[position - 2],
                )
        elif action == 4:
            position = rng.randint(1, len(todos))
            commands.append(f"later {position}")
            todos.append(todos.pop(position - 1))
        else:
            name = rng.choice(todos + ["absent"])
            commands.append(f"find {name}")
            output.append(
                str(todos.index(name) + 1) if name in todos else "not found"
            )
    commands.extend(["list", "exit"])
    output.append(" ".join(todos))
    return _case(
        _lines(commands) + "\n",
        _lines(output),
        time_limit=3,
        kind="random",
    )


def _todo_stress_case():
    commands = [f"add job{index}" for index in range(30000)]
    commands.extend(
        [
            "find job29999",
            "later 1",
            "find job0",
            "done 30000",
            "exit",
        ]
    )
    return _case(
        _lines(commands) + "\n",
        "30000\n30000\njob0",
        time_limit=4,
        kind="stress",
    )


def _lock_answer(start, shifts):
    start = tuple(start)
    target = (3,) * len(start)
    if start == target:
        return "0"
    queue = deque([start])
    parent = {start: None}
    parent_move = {}
    while queue:
        state = queue.popleft()
        for plate in range(len(start)):
            for direction, label in ((-1, "L"), (1, "R")):
                candidate = tuple(
                    state[index] + direction * shifts[plate][index]
                    for index in range(len(start))
                )
                if not all(1 <= value <= 7 for value in candidate):
                    continue
                if candidate in parent:
                    continue
                parent[candidate] = state
                parent_move[candidate] = (plate + 1, label)
                if candidate == target:
                    moves = []
                    current = candidate
                    while parent[current] is not None:
                        moves.append(parent_move[current])
                        current = parent[current]
                    moves.reverse()
                    return _lines(
                        [len(moves), *(f"{plate} {way}" for plate, way in moves)]
                    )
                queue.append(candidate)
    return "-1"


def _lock_case(start, shifts, *, kind="hidden", time_limit=3):
    data = [str(len(start)), " ".join(map(str, start))]
    data.extend(" ".join(map(str, row)) for row in shifts)
    return _case(
        _lines(data) + "\n",
        _lock_answer(start, shifts),
        time_limit=time_limit,
        kind=kind,
    )


def _grid_route_answer(grid, start, finish, *, include_areas=False):
    rows = len(grid)
    columns = len(grid[0])
    directions = ((-1, 0), (1, 0), (0, -1), (0, 1))

    areas = 0
    if include_areas:
        seen = set()
        for row in range(rows):
            for column in range(columns):
                if grid[row][column] == "#" or (row, column) in seen:
                    continue
                areas += 1
                seen.add((row, column))
                queue = deque([(row, column)])
                while queue:
                    current_row, current_column = queue.popleft()
                    for delta_row, delta_column in directions:
                        neighbour = (
                            current_row + delta_row,
                            current_column + delta_column,
                        )
                        if (
                            0 <= neighbour[0] < rows
                            and 0 <= neighbour[1] < columns
                            and grid[neighbour[0]][neighbour[1]] != "#"
                            and neighbour not in seen
                        ):
                            seen.add(neighbour)
                            queue.append(neighbour)

    distance = {start: 0}
    queue = deque([start])
    while queue:
        row, column = queue.popleft()
        for delta_row, delta_column in directions:
            neighbour = (row + delta_row, column + delta_column)
            if (
                0 <= neighbour[0] < rows
                and 0 <= neighbour[1] < columns
                and grid[neighbour[0]][neighbour[1]] != "#"
                and neighbour not in distance
            ):
                distance[neighbour] = distance[(row, column)] + 1
                queue.append(neighbour)

    prefix = [f"Areas: {areas}"] if include_areas else []
    if finish not in distance:
        if include_areas:
            return _lines([*prefix, "Route: none"])
        return "-1"

    length = distance[finish]
    result = [list(row) for row in grid]
    current = finish
    while current != start:
        for delta_row, delta_column in directions:
            previous = (current[0] + delta_row, current[1] + delta_column)
            if distance.get(previous) == distance[current] - 1:
                if previous != start:
                    result[previous[0]][previous[1]] = "*"
                current = previous
                break

    if include_areas:
        result[start[0]][start[1]] = "A"
        if finish != start:
            result[finish[0]][finish[1]] = "B"
        return _lines(
            [*prefix, f"Route: {length}", *("".join(row) for row in result)]
        )
    return _lines([length, *("".join(row) for row in result)])


def _maze_case(grid, *, kind="hidden", time_limit=3):
    start = finish = None
    for row, line in enumerate(grid):
        for column, value in enumerate(line):
            if value == "S":
                start = (row, column)
            elif value == "F":
                finish = (row, column)
    data = _lines([f"{len(grid)} {len(grid[0])}", *grid]) + "\n"
    return _case(
        data,
        _grid_route_answer(grid, start, finish),
        time_limit=time_limit,
        kind=kind,
    )


def _marauder_case(grid, start, finish, *, kind="hidden", time_limit=3):
    data = [f"{len(grid)} {len(grid[0])}", *grid]
    data.append(f"{start[0] + 1} {start[1] + 1} {finish[0] + 1} {finish[1] + 1}")
    return _case(
        _lines(data) + "\n",
        _grid_route_answer(grid, start, finish, include_areas=True),
        time_limit=time_limit,
        kind=kind,
    )


def _pagerank_expected(node_count, edges, iterations, *, sorted_result):
    outgoing = [[] for _ in range(node_count)]
    for source, target in edges:
        outgoing[source - 1].append(target - 1)
    weights = [1.0 / node_count] * node_count
    damping = 0.85
    for _ in range(iterations):
        dangling = sum(
            weights[node] for node in range(node_count) if not outgoing[node]
        )
        updated = [
            (1.0 - damping) / node_count + damping * dangling / node_count
            for _ in range(node_count)
        ]
        for source, targets in enumerate(outgoing):
            if not targets:
                continue
            share = damping * weights[source] / len(targets)
            for target in targets:
                updated[target] += share
        weights = updated
    order = list(range(node_count))
    if sorted_result:
        order.sort(key=lambda node: (-weights[node], node))
    return _lines(f"{node + 1} {weights[node]:.6f}" for node in order)


def _pagerank_case(
    node_count,
    edges,
    iterations,
    *,
    sorted_result,
    kind="hidden",
    time_limit=3,
):
    data = [f"{node_count} {len(edges)}"]
    data.extend(f"{source} {target}" for source, target in edges)
    return _case(
        _lines(data) + "\n",
        _pagerank_expected(
            node_count,
            edges,
            iterations,
            sorted_result=sorted_result,
        ),
        time_limit=time_limit,
        comparator=float_tokens_equal,
        kind=kind,
    )


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


def _log_stress_case():
    records = []
    counts = Counter()
    first_error = None
    longest = ""
    for index in range(10000):
        level = ("INFO", "WARN", "INFO", "ERROR")[index % 4]
        hour = index // 3600
        minute = (index // 60) % 60
        second = index % 60
        timestamp = f"{hour:02d}:{minute:02d}:{second:02d}"
        message = f"event-{index}"
        if index == 8765:
            message = "the  deliberately  longest  preserved  message"
        records.append(f"{timestamp} {level} {message}")
        counts[level] += 1
        if level == "ERROR" and first_error is None:
            first_error = timestamp
        if len(message) > len(longest):
            longest = message
    return _case(
        _lines([len(records), *records]) + "\n",
        _lines(
            [
                f"INFO {counts['INFO']} WARN {counts['WARN']} ERROR {counts['ERROR']}",
                first_error,
                longest,
            ]
        ),
        time_limit=3,
        comparator=exact_text_equal,
        kind="stress",
    )


_register(
    2718,
    10,
    (
        (
            _case(
                "3\n00:00:00 INFO up\n00:00:01 WARN warm\n00:00:02 INFO ok\n",
                "INFO 2 WARN 1 ERROR 0\nnone\nwarm",
            ),
            _case(
                "4\n10:00:00 ERROR first\n10:00:01 ERROR second error\n"
                "10:00:02 WARN warning\n10:00:03 INFO done\n",
                "INFO 1 WARN 1 ERROR 2\n10:00:00\nsecond error",
            ),
        ),
        (
            _case(
                "3\n01:02:03 INFO one  two\n01:02:04 WARN abcdefgh\n"
                "01:02:05 INFO tie  tie\n",
                "INFO 2 WARN 1 ERROR 0\nnone\none  two",
                comparator=exact_text_equal,
            ),
            _log_stress_case(),
        ),
    ),
)


_register(
    2720,
    15,
    (
        (
            _case(
                "add a\ninsert 1 b\ninsert 3 c\ninsert 5 x\nlist\n"
                "done 2\ndone 9\ndone 1\ndone 1\ndone 1\nexit\n",
                "error\nb a c\na\nerror\nb\nc\nerror",
            ),
        ),
        (
            _case(
                "add a\nadd b\nadd c\nup 1\nup 2\nlater 3\nlater 1\n"
                "list\nexit\n",
                "error\nb c a",
            ),
            _todo_random_case(),
        ),
        (
            _case(
                "list\nfind a\nadd same\nadd x\nadd same\nfind same\n"
                "later 1\nfind same\nlist\nexit\n",
                "\nnot found\n1\n2\nx same same",
                comparator=exact_text_equal,
            ),
            _todo_stress_case(),
        ),
    ),
)


def _editor_stress_case():
    commands = ["type ab"] * 40000
    commands.extend(["undo"] * 20000)
    commands.extend(["type z", "redo", "del 100000", "show", "exit"])
    return _case(
        _lines(commands) + "\n",
        "nothing to redo\n<empty>",
        time_limit=4,
        kind="stress",
    )


_register(
    2721,
    10,
    (
        (
            _case(
                "type cat\ntype dog\nshow\nundo\nshow\nredo\nshow\n"
                "undo\ntype fish\nredo\nshow\nexit\n",
                "catdog\ncat\ncatdog\nnothing to redo\ncatfish",
            ),
            _case(
                "undo\nredo\ntype abc\ndel 10\nshow\nundo\nshow\nredo\n"
                "show\nexit\n",
                "nothing to undo\nnothing to redo\n<empty>\nabc\n<empty>",
            ),
        ),
        (_editor_stress_case(),),
    ),
)


def _frequency_stress_case():
    words = ["alpha"] * 80000
    words.extend(["beta"] * 60000)
    words.extend(["gamma"] * 30000)
    words.extend(["delta"] * 30000)
    random.Random(2722).shuffle(words)
    return _case(
        " ".join(words) + "\n",
        "alpha 80000\nbeta 60000\ndelta 30000",
        time_limit=4,
        kind="stress",
    )


_register(
    2722,
    5,
    (
        (
            _case("cat dog cat fish dog cat\n", "cat 3\ndog 2\nfish 1"),
            _case("z a z b a b\n", "a 2\nb 2\nz 2"),
            _case("solo\n", "solo 1"),
            _frequency_stress_case(),
        ),
    ),
)


def _concert_stress_case():
    first = [f"p{index:05d}" for index in range(7000)]
    second = [f"p{index:05d}" for index in range(3500, 10500)]
    common = first[3500:]
    only_first = first[:3500]
    return _case(
        _lines([len(first), " ".join(first), len(second), " ".join(second)])
        + "\n",
        _lines([" ".join(common), " ".join(only_first), 10500]),
        time_limit=3,
        kind="stress",
    )


_register(
    2723,
    10,
    (
        (
            _case(
                "4\nanna boris clara dima\n3\nboris egor clara\n",
                "boris clara\nanna dima\n5",
            ),
            _case("2\na b\n2\nc d\n", "none\na b\n4"),
            _case("2\na b\n2\na b\n", "a b\nnone\n2"),
        ),
        (_concert_stress_case(),),
    ),
)


def _canteen_stress_case():
    records = [
        f"student{index % 500} dish{index % 37} {(index % 1000) + 1}"
        for index in range(20000)
    ]
    queries = ["spent ghost"] * 5000 + ["unique"]
    return _case(
        _lines([len(records), *records, len(queries), *queries]) + "\n",
        _lines([*("0" for _ in range(5000)), "500"]),
        time_limit=4,
        kind="stress",
    )


_register(
    2725,
    15,
    (
        (
            _case(
                "3\nanna soup 50\nanna tea 20\nboris bun 10\n"
                "3\nspent anna\nspent ghost\nunique\n",
                "70\n0\n2",
            ),
        ),
        (
            _case(
                "4\nzara tea 10\nanna soup 10\nzara soup 10\nanna tea 10\n"
                "2\ntop\npopular\n",
                "anna\nsoup",
            ),
        ),
        (
            _case(
                "4\na z 1\nb x 1\nc z 1\nd y 1\n1\nmenu\n",
                "x y z",
            ),
            _canteen_stress_case(),
        ),
    ),
)


def _anagram_stress_case():
    permutations = ["".join(value) for value in itertools.permutations("abcde")]
    words = [permutations[index % len(permutations)] for index in range(10000)]
    random.Random(2726).shuffle(words)
    return _case(
        _lines([len(words), *words]) + "\n",
        " ".join(sorted(words)),
        time_limit=4,
        kind="stress",
    )


_register(
    2726,
    10,
    (
        (
            _case(
                "8\nlisten\ncat\nsilent\nact\ndog\ntac\ncat\ngod\n",
                "act cat cat tac\ndog god\nlisten silent",
            ),
            _case("3\nz\na\nm\n", "a\nm\nz"),
        ),
        (_anagram_stress_case(),),
    ),
)


def _movies_stress_case():
    movies = [
        (f"m{index:04d}", (index * 37) % 101, (index * 7919) % 1000000 + 1)
        for index in range(4000)
    ]
    ordered = sorted(movies, key=lambda item: (-item[1], -item[2], item[0]))
    expected = _lines(
        f"{place} {name} {rating} {votes}"
        for place, (name, rating, votes) in enumerate(ordered, 1)
    )
    return _case(
        _lines([len(movies), *(" ".join(map(str, item)) for item in movies)])
        + "\n",
        expected,
        time_limit=3,
        kind="stress",
    )


_register(
    2727,
    5,
    (
        (
            _case(
                "5\nalien 90 300\nbrazil 100 500\ncoco 90 700\n"
                "dune 100 500\narrival 100 500\n",
                "1 arrival 100 500\n2 brazil 100 500\n3 dune 100 500\n"
                "4 coco 90 700\n5 alien 90 300",
            ),
            _movies_stress_case(),
        ),
    ),
)


def _training_case(
    values,
    *,
    kind="hidden",
    time_limit=2,
    capture_limit=None,
):
    total = sum(values)
    best = max(range(len(values)), key=lambda index: values[index])
    expected = _lines(
        [
            total,
            f"{best + 1} {values[best]}",
            values.count(0),
            " ".join(map(str, sorted(values, reverse=True))),
            " ".join(map(str, sorted(set(values)))),
        ]
    )
    return _case(
        _lines([len(values), " ".join(map(str, values))]) + "\n",
        expected,
        time_limit=time_limit,
        kind=kind,
        capture_limit=capture_limit,
    )


_training_stress_values = [
    0 if index % 17 == 0 else (index * 7919) % 100001
    for index in range(7500)
]


_register(
    2728,
    10,
    (
        (
            _training_case([3000, 0, 5000, 3000, 0, 4200]),
            _training_case(
                [100000] * 200000,
                kind="stress",
                time_limit=5,
                capture_limit=2 * 1024 * 1024,
            ),
        ),
        (
            _training_case([9, 1, 9, 0, 1, 5]),
            _training_case(
                _training_stress_values,
                kind="random",
                time_limit=3,
            ),
        ),
    ),
)


def _library_stress_case():
    books = [f"book{index:05d} author{index:05d} {1900 + index % 125}" for index in range(10000)]
    queries = [f"by author{index % 10000:05d}" for index in range(4000)]
    expected = _lines(f"book{index % 10000:05d}" for index in range(4000))
    return _case(
        _lines([len(books), *books, len(queries), *queries]) + "\n",
        expected,
        time_limit=4,
        kind="stress",
    )


_register(
    2729,
    15,
    (
        (
            _case(
                "2\nhobbit tolkien 1937\ndune herbert 1965\n9\n"
                "take hobbit anna\ntake hobbit boris\nwho hobbit\nback hobbit\n"
                "back hobbit\nwho hobbit\ntake missing a\nback missing\nwho missing\n",
                "ok\ntaken by anna\nanna\nok\nwas free\nfree\nno book\n"
                "no book\nno book",
            ),
        ),
        (
            _case(
                "4\nzeta auth 1900\nalpha auth 1900\nbeta other 2000\n"
                "gamma auth 1950\n6\nby auth\nby nobody\noldest\nbusy\n"
                "take beta u\nbusy\n",
                "alpha gamma zeta\nnone\nalpha 1900\n0\nok\n1",
            ),
        ),
        (_library_stress_case(),),
    ),
)


def _karting_stress_case():
    races = []
    for index in range(30000):
        track = index % 1000 + 1
        slot = index // 1000
        start = slot * 40
        races.append((track, start, start + 20))
    random.Random(2730).shuffle(races)
    return _case(
        _lines([len(races), *(" ".join(map(str, race)) for race in races)])
        + "\n",
        "ok",
        time_limit=4,
        kind="stress",
    )


_register(
    2730,
    10,
    (
        (
            _case("3\n1 600 660\n1 660 720\n2 600 700\n", "ok"),
            _case(
                "5\n1 100 300\n2 101 102\n1 200 250\n1 260 290\n"
                "2 500 600\n",
                "clash 1 200 250",
            ),
        ),
        (_karting_stress_case(),),
    ),
)


def _neighbours_stress_case():
    node_count = 100000
    edges = [(node, node + 1) for node in range(1, node_count)]
    target = 50000
    data = [f"{node_count} {len(edges)}"]
    data.extend(f"{left} {right}" for left, right in edges)
    data.append(str(target))
    return _case(
        _lines(data) + "\n",
        f"{target - 1} {target + 1}",
        time_limit=4,
        kind="stress",
    )


_register(
    2731,
    5,
    (
        (
            _case(
                "5 5\n1 2\n1 3\n2 3\n3 4\n4 5\n3\n",
                "1 2 4",
            ),
            _case("4 1\n2 3\n1\n", "none"),
            _neighbours_stress_case(),
        ),
    ),
)


def _recommendations_stress_case():
    friends = list(range(2, 1002))
    candidates = list(range(1002, 1052))
    edges = [(1, friend) for friend in friends]
    edges.extend((friend, candidate) for friend in friends for candidate in candidates)
    data = [f"1051 {len(edges)}"]
    data.extend(f"{left} {right}" for left, right in edges)
    data.append("1")
    expected = _lines(f"{candidate} 1000" for candidate in candidates)
    return _case(
        _lines(data) + "\n",
        expected,
        time_limit=4,
        kind="stress",
    )


_register(
    2732,
    10,
    (
        (
            _case(
                "6 6\n1 2\n1 3\n2 4\n3 4\n4 5\n5 6\n1\n",
                "4 2",
            ),
            _case(
                "5 4\n1 2\n2 3\n2 4\n1 5\n3\n",
                "1 1\n4 1",
            ),
            _case("4 2\n1 2\n3 4\n1\n", "none"),
        ),
        (_recommendations_stress_case(),),
    ),
)


def _triangle_stress_case():
    edges = [(left, right) for left in range(1, 51) for right in range(51, 150)]
    edges.extend([(998, 999), (999, 1000), (998, 1000)])
    data = [f"1000 {len(edges)}"]
    data.extend(f"{left} {right}" for left, right in edges)
    return _case(
        _lines(data) + "\n",
        "YES\n998 999 1000",
        time_limit=4,
        kind="stress",
    )


_register(
    2733,
    10,
    (
        (
            _case(
                "5 7\n1 2\n2 3\n3 1\n1 4\n3 4\n4 5\n3 5\n",
                "YES\n1 2 3",
            ),
            _case("4 4\n1 2\n2 3\n3 4\n4 1\n", "NO"),
        ),
        (_triangle_stress_case(),),
    ),
)


def _handshakes_stress_case():
    edges = [(1, node) for node in range(2, 100001)]
    data = [f"100000 {len(edges)}"]
    data.extend(f"{left} {right}" for left, right in edges)
    data.append("2 3")
    return _case(
        _lines(data) + "\n",
        "2\n2 1 3",
        time_limit=4,
        kind="stress",
    )


_register(
    2734,
    10,
    (
        (
            _case(
                "5 4\n1 2\n2 3\n3 4\n4 5\n1 5\n",
                "4\n1 2 3 4 5",
            ),
            _case("4 2\n1 2\n3 4\n1 3\n", "-1"),
            _case("3 1\n1 2\n2 2\n", "0\n2"),
        ),
        (_handshakes_stress_case(),),
    ),
)


_maze_example = [
    "S.#.....",
    ".##.##.#",
    "...#...#",
    ".#...#.#",
    "...#...F",
]
_maze_open = ["S..", "...", "..F"]
_maze_blocked_stress = []
for _row in range(1000):
    _line = ["."] * 1000
    _line[500] = "#"
    _maze_blocked_stress.append("".join(_line))
_maze_blocked_stress[0] = "S" + _maze_blocked_stress[0][1:]
_maze_blocked_stress[-1] = _maze_blocked_stress[-1][:-1] + "F"


_register(
    2735,
    15,
    (
        (
            _maze_case(["S#F", ".#."]),
            _maze_case(["SF"]),
        ),
        (
            _maze_case(_maze_example),
            _maze_case(_maze_open, kind="random"),
        ),
        (
            _maze_case(_maze_blocked_stress, kind="stress", time_limit=5),
        ),
    ),
)


_lock_example_shifts = [[1, 1, 0], [0, 1, -1], [0, 0, 1]]
_lock_identity_five = [
    [1 if row == column else 0 for column in range(5)]
    for row in range(5)
]


_register(
    2736,
    15,
    (
        (
            _lock_case([2, 2, 5], _lock_example_shifts),
            _lock_case([3, 3], [[1, 0], [0, 1]]),
        ),
        (
            _lock_case([5, 1, 4], _lock_example_shifts, kind="random"),
        ),
        (
            _lock_case([2, 4], [[1, 1], [1, 1]]),
            _lock_case(
                [1, 7, 1, 7, 1],
                _lock_identity_five,
                kind="stress",
                time_limit=4,
            ),
        ),
    ),
)


def _dfs_stress_case():
    node_count = 10000
    edges = [(node, node + 1) for node in range(1, node_count)]
    data = [f"{node_count} {len(edges)}"]
    data.extend(f"{left} {right}" for left, right in reversed(edges))
    return _case(
        _lines(data) + "\n",
        " ".join(map(str, range(1, node_count + 1))),
        time_limit=3,
        kind="stress",
    )


_register(
    2737,
    5,
    (
        (
            _case("5 4\n1 3\n1 2\n3 5\n2 4\n", "1 2 4 3 5"),
            _case("4 1\n2 3\n", "1"),
            _dfs_stress_case(),
        ),
    ),
)


_all_land = ["#" * 200 for _ in range(200)]
_checkerboard = [
    "".join("#" if (row + column) % 2 == 0 else "." for column in range(200))
    for row in range(200)
]


_register(
    2738,
    10,
    (
        (
            _case(
                "5 8\n##..#...\n#...##..\n....##..\n.#......\n.#...###\n",
                "4",
            ),
            _case("3 3\n#.#\n.#.\n#.#\n", "5"),
            _case("2 3\n...\n...\n", "0"),
        ),
        (
            _case(
                _lines(["200 200", *_all_land]) + "\n",
                "1",
                time_limit=3,
                kind="stress",
            ),
            _case(
                _lines(["200 200", *_checkerboard]) + "\n",
                "20000",
                time_limit=3,
                kind="stress",
            ),
        ),
    ),
)


_marauder_grid = [
    "..##..",
    ".##...",
    "..#.##",
    "..#..#",
    "..#...",
]
_marauder_open_stress = ["." * 200 for _ in range(200)]


_register(
    2739,
    20,
    (
        (
            _marauder_case(_marauder_grid, (0, 4), (4, 5)),
        ),
        (
            _marauder_case(_marauder_grid, (0, 0), (4, 5)),
        ),
        (
            _marauder_case(["...", ".#.", "..."], (0, 0), (0, 0)),
            _marauder_case(["....", "...."], (0, 0), (1, 3), kind="random"),
        ),
        (
            _marauder_case(
                _marauder_open_stress,
                (0, 0),
                (199, 199),
                kind="stress",
                time_limit=4,
            ),
        ),
    ),
)


def _articulation_stress_case():
    edges = {(node, node % 2000 + 1) for node in range(1, 2001)}
    step = 2
    while len(edges) < 5000:
        for node in range(1, 2001):
            target = (node - 1 + step) % 2000 + 1
            edge = tuple(sorted((node, target)))
            if edge[0] != edge[1]:
                edges.add(edge)
            if len(edges) == 5000:
                break
        step += 1
    ordered = sorted(edges)
    return _case(
        _lines([f"2000 {len(ordered)}", *(f"{a} {b}" for a, b in ordered)])
        + "\n",
        "none",
        time_limit=5,
        kind="stress",
    )


_register(
    2740,
    10,
    (
        (
            _case("5 4\n1 2\n2 3\n3 4\n4 5\n", "2 3 4"),
            _case("4 4\n1 2\n2 3\n3 4\n4 1\n", "none"),
            _case("6 5\n1 2\n2 3\n3 1\n4 5\n5 6\n", "5"),
        ),
        (_articulation_stress_case(),),
    ),
)


def _reducto_three_cut_case():
    left = range(1, 6)
    cut = (6, 7, 8)
    right = range(9, 14)
    edges = set()
    for group in (left, cut, right):
        edges.update(itertools.combinations(group, 2))
    for connector in cut:
        edges.update((min(connector, node), max(connector, node)) for node in left)
        edges.update((min(connector, node), max(connector, node)) for node in right)
    ordered = sorted(edges)
    return _case(
        _lines([f"13 {len(ordered)}", *(f"{a} {b}" for a, b in ordered)])
        + "\n",
        "3\n6 7 8",
        time_limit=4,
        kind="random",
    )


def _reducto_complete_case():
    # K28 has 378 edges, so the hidden input stays inside the published m <= 400.
    edges = list(itertools.combinations(range(1, 29), 2))
    return _case(
        _lines([f"28 {len(edges)}", *(f"{a} {b}" for a, b in edges)]) + "\n",
        "impossible",
        time_limit=5,
        kind="stress",
    )


_register(
    2741,
    15,
    (
        (
            _case("3 2\n1 2\n2 3\n", "1\n2"),
            _case("4 2\n1 2\n3 4\n", "0"),
        ),
        (
            _case("4 4\n1 2\n2 3\n3 4\n4 1\n", "2\n1 3"),
            _reducto_three_cut_case(),
        ),
        (
            _case(
                "4 6\n1 2\n1 3\n1 4\n2 3\n2 4\n3 4\n",
                "impossible",
            ),
            _reducto_complete_case(),
        ),
    ),
)


def _pagerank_edges(node_count, degree):
    return [
        (source, (source - 1 + offset * 137) % node_count + 1)
        for source in range(1, node_count + 1)
        for offset in range(1, degree + 1)
    ]


_register(
    2742,
    5,
    (
        (
            _pagerank_case(
                3,
                [(1, 2), (2, 3), (3, 1)],
                1,
                sorted_result=False,
            ),
            _pagerank_case(
                3,
                [(1, 3), (2, 3)],
                1,
                sorted_result=False,
            ),
            _pagerank_case(
                8,
                [(1, 2), (1, 3), (2, 4), (4, 2), (5, 4), (7, 8)],
                1,
                sorted_result=False,
                kind="random",
            ),
            _pagerank_case(
                1000,
                _pagerank_edges(1000, 5),
                1,
                sorted_result=False,
                kind="stress",
                time_limit=3,
            ),
        ),
    ),
    float_tokens_equal,
)


_register(
    2743,
    15,
    (
        (
            _pagerank_case(
                3,
                [(1, 3), (2, 3)],
                60,
                sorted_result=True,
            ),
        ),
        (
            _pagerank_case(
                6,
                [(4, 3), (5, 3), (6, 3), (1, 2), (2, 1)],
                60,
                sorted_result=True,
            ),
            _pagerank_case(
                4,
                [(1, 2), (2, 1), (3, 4), (4, 3)],
                60,
                sorted_result=True,
                kind="random",
            ),
        ),
        (
            _pagerank_case(
                3000,
                _pagerank_edges(3000, 10),
                60,
                sorted_result=True,
                kind="stress",
                time_limit=5,
            ),
        ),
    ),
    float_tokens_equal,
)


def _route_check_stress_case():
    edges = {(node, node + 1, 1000) for node in range(1, 1000)}
    offset = 2
    while len(edges) < 10000:
        for node in range(1, 1001):
            target = (node - 1 + offset) % 1000 + 1
            if node == target:
                continue
            left, right = sorted((node, target))
            edges.add((left, right, (left * 31 + right * 17) % 1000 + 1))
            if len(edges) == 10000:
                break
        offset += 1
    route = list(range(1, 1001))
    data = [f"1000 {len(edges)}"]
    data.extend(f"{left} {right} {weight}" for left, right, weight in sorted(edges))
    data.extend([str(len(route)), " ".join(map(str, route))])
    return _case(
        _lines(data) + "\n",
        "999000",
        time_limit=3,
        kind="stress",
    )


_register(
    2744,
    5,
    (
        (
            _case(
                "4 4\n1 2 7\n2 3 5\n3 4 2\n1 4 20\n3\n1 2 3\n",
                "12",
            ),
            _case(
                "4 4\n1 2 7\n2 3 5\n3 4 2\n1 4 20\n3\n1 3 4\n",
                "no road",
            ),
            _case("2 1\n1 2 10\n1\n2\n", "0"),
            _route_check_stress_case(),
        ),
    ),
)


def _delivery_stress_case():
    edges = [(1, node, 1) for node in range(2, 100001)]
    data = [f"100000 {len(edges)}"]
    data.extend(f"{left} {right} {weight}" for left, right, weight in edges)
    data.append("2 3")
    return _case(
        _lines(data) + "\n",
        "2\n2 1 3",
        time_limit=5,
        kind="stress",
    )


_register(
    2745,
    15,
    (
        (
            _case(
                "3 3\n1 2 4\n2 3 5\n1 3 20\n1 3\n",
                "9\n1 2 3",
            ),
            _case("3 1\n1 2 5\n1 3\n", "no route"),
            _case("2 1\n1 2 7\n2 2\n", "0\n2"),
        ),
        (
            _case(
                "6 7\n1 2 7\n1 3 9\n1 6 14\n2 4 15\n3 4 11\n"
                "3 6 2\n5 6 9\n1 5\n",
                "20\n1 3 6 5",
            ),
        ),
        (_delivery_stress_case(),),
    ),
)


def _metro_stress_case():
    station_count = 20000
    transfer = 7
    edges = [
        (station, station + 1, station % 30 + 1, 1)
        for station in range(1, station_count)
    ]
    travel = station_count - 1
    transfers = station_count - 2
    data = [f"{station_count} {len(edges)} {transfer}"]
    data.extend(" ".join(map(str, edge)) for edge in edges)
    data.append(f"1 {station_count}")
    return _case(
        _lines(data) + "\n",
        str(travel + transfer * transfers),
        time_limit=5,
        kind="stress",
    )


_register(
    2747,
    15,
    (
        (
            _case(
                "4 4 5\n1 2 1 10\n2 3 1 10\n1 4 2 3\n4 3 2 3\n1 3\n",
                "6",
            ),
            _case("4 2 5\n1 2 1 7\n3 4 2 7\n1 4\n", "no route"),
            _case("2 1 9\n1 2 1 3\n1 1\n", "0"),
        ),
        (
            _case(
                "4 3 5\n1 2 1 4\n2 3 2 4\n3 4 2 4\n1 4\n",
                "17",
            ),
            _case(
                "3 2 5\n1 2 1 4\n2 3 2 4\n3 1\n",
                "13",
            ),
            _case(
                "5 6 10\n1 2 1 2\n2 5 2 2\n1 3 3 4\n3 4 3 4\n"
                "4 5 3 4\n2 3 1 100\n1 5\n",
                "12",
                kind="random",
            ),
        ),
        (_metro_stress_case(),),
    ),
)


def _file_tree_stress_case():
    objects = ["root 0 -"]
    objects.extend(f"file{index:05d} 1000000000 root" for index in range(10000))
    return _case(
        _lines([len(objects), *objects]) + "\n",
        "root 10000000000000",
        time_limit=3,
        kind="stress",
    )


_register(
    2749,
    5,
    (
        (
            _case(
                "6\nroot 0 -\ndocs 0 root\nreport 500 docs\nnotes 300 docs\n"
                "photo 1200 root\nempty 0 docs\n",
                "docs 800\nroot 2000",
            ),
            _case(
                "5\nr 0 -\na 0 r\nb 0 a\nc 7 b\nzero 0 b\n",
                "a 7\nb 7\nr 7",
            ),
            _file_tree_stress_case(),
        ),
    ),
)


def _prefix_stress_case():
    text = "a" * 70000 + "b" * 20000 + "c" * 10000
    return _case(
        f"3\na 0\nb 10\nc 11\n{text}\n",
        f"yes\n{len(text) * 8}\n{70000 + 40000 + 20000}",
        time_limit=3,
        kind="stress",
    )


_register(
    2750,
    5,
    (
        (
            _case(
                "4\na 0\nb 10\nc 110\nd 111\naaabbcd\n",
                "yes\n56\n13",
            ),
            _case("3\na 0\nb 01\nc 10\nabca\n", "no\n32\n6"),
            _case("2\na 101\nb 1011\nab\n", "no\n16\n7"),
            _prefix_stress_case(),
        ),
    ),
)


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
