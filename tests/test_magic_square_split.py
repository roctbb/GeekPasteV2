import unittest

from environments import grade8_2026_chapters_1_4 as chapter


def reference(input_data, diagnostic=False, omit_diagonal=None):
    values = list(map(int, input_data.split()))
    n, cells = values[0], values[1:]
    rows = [cells[i * n:(i + 1) * n] for i in range(n)]
    target = sum(rows[0])
    lines = [("row", i + 1, row) for i, row in enumerate(rows)]
    lines += [("col", i + 1, col) for i, col in enumerate(zip(*rows))]
    if omit_diagonal != 1:
        lines.append(("diag", 1, [rows[i][i] for i in range(n)]))
    if omit_diagonal != 2:
        lines.append(("diag", 2, [rows[i][n - i - 1] for i in range(n)]))
    for kind, number, line in lines:
        if sum(line) != target:
            return (f"NO: {kind} {number} (sum {sum(line)}, expected {target})"
                    if diagnostic else "NO")
    return "YES"


class MagicSquareSplitTests(unittest.TestCase):
    def score(self, task_id, answer):
        return chapter.TASKS[task_id][1](lambda data, limit: answer(data), "")[0]

    def test_verdict_only_gets_all_base_points_and_no_bonus(self):
        self.assertEqual(self.score(2611, reference), 5)
        self.assertEqual(self.score(2915, reference), 0)

    def test_complete_diagnostics_get_all_bonus_points(self):
        self.assertEqual(self.score(2915, lambda data: reference(data, True)), 5)

    def test_both_diagonals_are_required_even_in_base_task(self):
        for diagonal in (1, 2):
            self.assertEqual(self.score(2611, lambda data: reference(data, omit_diagonal=diagonal)), 0)

    def test_wrong_verdict_never_gets_points(self):
        for task in (2611, 2915):
            for word in ("YES", "NO", ""):
                self.assertEqual(self.score(task, lambda data: word), 0)

    def test_bonus_rejects_wrong_location_number_and_sum(self):
        for old, new in (("row 2", "row 1"), ("col 2", "col 1"),
                         ("sum 13", "sum 14"), ("expected 17", "expected 15"),
                         ("diag 2", "diag 1")):
            with self.subTest(old=old):
                self.assertEqual(self.score(2915, lambda data: reference(data, True).replace(old, new)), 0)

    def test_published_diagnostics_and_priority(self):
        examples = [
            ([[2, 9, 6], [7, 5, 1], [4, 3, 8]], "NO: row 2 (sum 13, expected 17)"),
            ([[1, 2], [0, 3]], "NO: col 1 (sum 1, expected 3)"),
            ([[1, 2], [2, 1]], "NO: diag 1 (sum 2, expected 3)"),
            ([[0, 0, 1], [0, 1, 0], [1, 0, 0]], "NO: diag 2 (sum 3, expected 1)"),
            ([[1, 2, 0]] * 3, "NO: col 2 (sum 6, expected 3)"),
            ([[0]], "YES"),
        ]
        for matrix, answer in examples:
            self.assertEqual(chapter._magic_answer(matrix).strip(), answer)

    def test_debug_output_is_not_accepted(self):
        for task, diagnostic in ((2611, False), (2915, True)):
            self.assertEqual(self.score(task, lambda data: reference(data, diagnostic) + " debug"), 0)


if __name__ == "__main__":
    unittest.main()
