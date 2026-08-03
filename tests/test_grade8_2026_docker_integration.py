import os
import subprocess
import unittest

from environments.grade8_2026_common import perform_task
from runner import ExecutionContainer, ExecutionException, SolutionException, TestRunner
from tests.test_grade8_2026_chapters_5_6 import CPP_REFERENCE_SOURCES
from tests.test_grade8_2026_chapters_7_8 import (
    GPH1_REFERENCE_ARCHIVER_SOURCE,
    RAW_COPY_ARCHIVER_SOURCE,
)


RUN_DOCKER_INTEGRATION = os.getenv("RUN_GRADE8_DOCKER_INTEGRATION") == "1"


ROTATION_SOURCE = r"""
#include <iostream>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    int n = 0;
    if (!(std::cin >> n)) return 0;
    std::vector<long long> values(n);
    for (long long& value : values) std::cin >> value;
    if (n > 0) {
        std::cout << values.back();
        for (int index = 0; index + 1 < n; ++index) {
            std::cout << ' ' << values[index];
        }
    }
    std::cout << '\n';
}
"""


MERGE_SOURCE = r"""
#include <iostream>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    int n = 0, m = 0;
    std::cin >> n;
    std::vector<long long> first(n);
    for (long long& value : first) std::cin >> value;
    std::cin >> m;
    std::vector<long long> second(m);
    for (long long& value : second) std::cin >> value;
    int left = 0, right = 0;
    bool printed = false;
    while (left < n || right < m) {
        long long value;
        if (right == m || (left < n && first[left] <= second[right])) {
            value = first[left++];
        } else {
            value = second[right++];
        }
        if (printed) std::cout << ' ';
        std::cout << value;
        printed = true;
    }
    std::cout << '\n';
}
"""


@unittest.skipUnless(
    RUN_DOCKER_INTEGRATION,
    "set RUN_GRADE8_DOCKER_INTEGRATION=1 inside the GeekPaste runtime",
)
class Grade8DockerIntegrationTests(unittest.TestCase):
    def test_transfer_failure_removes_the_started_container(self):
        class ForcedTransferFailureContainer(ExecutionContainer):
            started_container_id = None

            def _stream_path_into_container(
                self, container_id, local_path, container_path
            ):
                type(self).started_container_id = container_id
                raise ExecutionException("forced transfer failure")

        with self.assertRaises(ExecutionException):
            ForcedTransferFailureContainer("cpp", "", "int main() { return 0; }")

        container_id = ForcedTransferFailureContainer.started_container_id
        self.assertIsNotNone(container_id)
        result = subprocess.run(
            ["docker", "inspect", container_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertNotEqual(result.returncode, 0)

    def score(self, task_id, source_code, language="cpp"):
        with ExecutionContainer(
            language,
            f"environments/task_{task_id}",
            source_code,
        ) as container:
            return perform_task(
                task_id,
                TestRunner(container),
                source_code,
            )

    def test_large_correct_output_uses_the_per_case_capture_limit(self):
        points, _ = self.score(2607, ROTATION_SOURCE)
        self.assertEqual(points, 5)

        wrong_points, _ = self.score(2607, "int main() { return 0; }")
        self.assertEqual(wrong_points, 0)

    def test_maximum_multi_megabyte_output_is_bounded_but_accepted(self):
        points, _ = self.score(2652, MERGE_SOURCE)
        self.assertEqual(points, 5)

    def test_structured_text_answer_runs_through_the_real_python_container(self):
        points, _ = self.score(2621, "n n2 logn 1 nlogn", "python")
        self.assertEqual(points, 5)

        wrong_points, _ = self.score(2621, "n n logn 1 nlogn", "python")
        self.assertEqual(wrong_points, 0)

    def test_memory_heavy_string_contract_passes_sanitized_harnesses(self):
        source = CPP_REFERENCE_SOURCES[2703]
        points, _ = self.score(2703, source)
        self.assertEqual(points, 20)

    def test_exact_gph1_archiver_passes_and_raw_copy_is_rejected(self):
        points, _ = self.score(2753, GPH1_REFERENCE_ARCHIVER_SOURCE)
        self.assertEqual(points, 20)

        wrong_points, _ = self.score(2753, RAW_COPY_ARCHIVER_SOURCE)
        self.assertEqual(wrong_points, 0)

    def test_syntax_error_is_a_solution_error(self):
        with self.assertRaises(SolutionException):
            ExecutionContainer("cpp", "", "this is not valid C++")

    def test_runtime_timeout_stops_the_execution_container(self):
        source = "int main() { for (;;) {} }"
        with ExecutionContainer("cpp", "", source) as container:
            with self.assertRaises(SolutionException):
                container.run("", time_limit=1)
            self.assertTrue(container._unusable)
            with self.assertRaises(SolutionException):
                container.run("", time_limit=1)


if __name__ == "__main__":
    unittest.main()
