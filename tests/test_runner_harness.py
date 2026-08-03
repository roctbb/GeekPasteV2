import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from runner import (
    ExecutionContainer,
    ExecutionException,
    SolutionException,
    TestRunner as RunnerFacade,
    _run_process_bounded,
)


class FakeContainer:
    def __init__(self):
        self.calls = []

    def run(self, input_data, time_limit=1, capture_limit=102400):
        self.calls.append(("run", input_data, time_limit, capture_limit))
        return "program output"

    def run_source(
        self,
        source_code,
        input_data="",
        time_limit=1,
        probe_source=None,
        compile_options=None,
    ):
        self.calls.append(
            (
                "run_source",
                source_code,
                input_data,
                time_limit,
                probe_source,
                compile_options,
            )
        )
        return "harness output"


class TestRunnerTests(unittest.TestCase):
    def test_facade_preserves_the_existing_callable_api(self):
        container = FakeContainer()
        runner = RunnerFacade(container)

        self.assertEqual(runner("input\n", 3), "program output")
        self.assertEqual(container.calls, [("run", "input\n", 3, 102400)])

    def test_facade_allows_a_trusted_per_case_output_limit(self):
        container = FakeContainer()
        runner = RunnerFacade(container)

        self.assertEqual(runner("input\n", 3, 500000), "program output")
        self.assertEqual(container.calls, [("run", "input\n", 3, 500000)])

    def test_facade_exposes_isolated_source_execution(self):
        container = FakeContainer()
        runner = RunnerFacade(container)

        self.assertEqual(
            runner.run_source("print('test')", "stdin\n", 4),
            "harness output",
        )
        self.assertEqual(
            container.calls,
            [("run_source", "print('test')", "stdin\n", 4, None, None)],
        )

    def test_facade_passes_trusted_cpp_compile_options(self):
        container = FakeContainer()
        runner = RunnerFacade(container)

        runner.run_source(
            "int main() {}",
            compile_options=("-O1", "-fsanitize=address,undefined"),
        )

        self.assertEqual(
            container.calls,
            [
                (
                    "run_source",
                    "int main() {}",
                    "",
                    1,
                    None,
                    ("-O1", "-fsanitize=address,undefined"),
                )
            ],
        )


class ExecutionContainerHarnessTests(unittest.TestCase):
    def _container(self, directory, transfer_mode, language="python"):
        container = object.__new__(ExecutionContainer)
        container.language = language
        container.path = directory
        container.container_id = "container-id"
        container._docker_transfer_mode = transfer_mode
        container._harness_compile_timeout = 7
        container._run_command = mock.Mock(return_value="ok")
        container.cleanup = mock.Mock()
        return container

    @mock.patch("runner.subprocess.run")
    def test_cpp_prepare_applies_runtime_resource_boundaries(self, subprocess_run):
        subprocess_run.return_value = mock.Mock(stdout=b"container-id\n")
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "cp", language="cpp")
            container._pip_cache_volume = "unused"

            self.assertEqual(container.prepare(), "container-id")

        command = subprocess_run.call_args_list[0].args[0]
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("--memory", command)
        self.assertIn("--pids-limit", command)
        self.assertIn("--read-only", command)
        self.assertIn("/code:rw,exec,nosuid,nodev,size=128m", command)

    def test_initial_cpp_compile_uses_the_bounded_compiler(self):
        container = object.__new__(ExecutionContainer)
        container.container_id = None
        container.path = None
        container.language = "cpp"
        container._compile_cpp_harness = mock.Mock()

        container.setup()

        container._compile_cpp_harness.assert_called_once_with(
            "/code/script.cpp",
            "/code/program",
        )

    def test_initial_cpp_solution_error_is_not_reclassified(self):
        container = object.__new__(ExecutionContainer)
        container.container_id = None
        container.path = None
        container.language = "cpp"
        container._compile_cpp_harness = mock.Mock(
            side_effect=SolutionException("bad student source")
        )

        with self.assertRaisesRegex(SolutionException, "bad student source"):
            container.setup()

    def test_bind_harness_is_removed_after_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "bind")
            observed_source = {}

            def run_command(command, input_data, time_limit):
                filename = command.rsplit(" ", 1)[-1]
                with open(os.path.join(directory, filename), encoding="utf-8") as source:
                    observed_source["value"] = source.read()
                return "ok"

            source = "print(42)"
            container._run_command.side_effect = run_command
            result = container.run_source(source, "input\n", 2)

            self.assertEqual(result, "ok")
            command = container._run_command.call_args.args[0]
            filename = command.rsplit(" ", 1)[-1]
            self.assertFalse(os.path.exists(os.path.join(directory, filename)))
            self.assertEqual(observed_source["value"], source)
            container._run_command.assert_called_once_with(command, "input\n", 2)
            container.container_id = None
            container.path = None

    @mock.patch("runner.subprocess.run")
    def test_cp_harness_is_copied_and_removed(self, subprocess_run):
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "cp")

            result = container.run_source("print(42)")

            self.assertEqual(result, "ok")
            copy_call = subprocess_run.call_args_list[0].args[0]
            remove_call = subprocess_run.call_args_list[-1].args[0]
            self.assertEqual(copy_call[:2], ["docker", "cp"])
            self.assertEqual(copy_call[-1].split(":", 1)[0], "container-id")
            self.assertEqual(remove_call[:4], ["docker", "exec", "container-id", "rm"])
            self.assertEqual(
                subprocess_run.call_args_list[0].kwargs["timeout"],
                container._harness_docker_timeout,
            )
            container.container_id = None
            container.path = None

    @mock.patch("runner.subprocess.run")
    def test_cp_harness_is_removed_when_student_execution_fails(self, subprocess_run):
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "cp")
            container._run_command.side_effect = SolutionException("student failed")

            with self.assertRaisesRegex(SolutionException, "student failed"):
                container.run_source("raise RuntimeError")

            local_path = subprocess_run.call_args_list[0].args[0][2]
            self.assertFalse(os.path.exists(local_path))
            remove_call = subprocess_run.call_args_list[-1].args[0]
            self.assertEqual(remove_call[:4], ["docker", "exec", "container-id", "rm"])
            container.container_id = None
            container.path = None

    @mock.patch("runner.subprocess.run")
    def test_cp_failure_still_attempts_container_cleanup(self, subprocess_run):
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "cp")
            subprocess_run.side_effect = [
                subprocess.TimeoutExpired(["docker", "cp"], 10),
                mock.DEFAULT,
            ]

            with self.assertRaises(ExecutionException):
                container.run_source("print(42)")

            self.assertEqual(len(subprocess_run.call_args_list), 2)
            local_path = subprocess_run.call_args_list[0].args[0][2]
            self.assertFalse(os.path.exists(local_path))
            remove_call = subprocess_run.call_args_list[-1].args[0]
            self.assertEqual(remove_call[:4], ["docker", "exec", "container-id", "rm"])
            container.container_id = None
            container.path = None

    @mock.patch("runner._run_process_bounded")
    def test_cpp_bind_harness_compiles_to_a_separate_binary_and_cleans_up(
        self,
        bounded_run,
    ):
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "bind", language="cpp")
            source = "int main() { return 0; }"

            def compile_harness(command, input_bytes, timeout, capture_limit):
                local_source = os.path.join(directory, os.path.basename(command[5]))
                local_binary = os.path.join(directory, os.path.basename(command[7]))
                with open(local_source, encoding="utf-8") as harness:
                    self.assertEqual(harness.read(), source)
                with open(local_binary, "wb") as binary:
                    binary.write(b"compiled")
                self.assertEqual(input_bytes, b"")
                self.assertEqual(timeout, 7)
                self.assertGreater(capture_limit, 0)
                return 0, b"", b"", False

            bounded_run.side_effect = compile_harness

            result = container.run_source(source, "stdin\n", 3)

            self.assertEqual(result, "ok")
            compile_command = bounded_run.call_args.args[0]
            self.assertEqual(
                compile_command[:5],
                ["docker", "exec", "container-id", "g++", "-std=c++17"],
            )
            source_path = compile_command[5]
            binary_path = compile_command[7]
            self.assertEqual(compile_command[6], "-o")
            self.assertNotEqual(source_path, binary_path)
            self.assertNotEqual(binary_path, "/code/program")
            self.assertTrue(source_path.endswith(".cpp"))
            container._run_command.assert_called_once_with(
                f"cd /code && ./{os.path.basename(binary_path)}",
                "stdin\n",
                3,
            )
            self.assertFalse(
                os.path.exists(os.path.join(directory, os.path.basename(source_path)))
            )
            self.assertFalse(
                os.path.exists(os.path.join(directory, os.path.basename(binary_path)))
            )
            container.container_id = None
            container.path = None

    @mock.patch("runner.subprocess.run")
    @mock.patch("runner._run_process_bounded")
    def test_cpp_cp_harness_is_copied_compiled_and_removed(
        self,
        bounded_run,
        subprocess_run,
    ):
        bounded_run.return_value = (0, b"", b"", False)
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "cp", language="cpp")

            result = container.run_source("int main() { return 0; }")

            self.assertEqual(result, "ok")
            compile_command = bounded_run.call_args.args[0]
            source_path = compile_command[5]
            binary_path = compile_command[7]
            copy_call = subprocess_run.call_args_list[0]
            remove_call = subprocess_run.call_args_list[-1]
            self.assertEqual(copy_call.args[0][:2], ["docker", "cp"])
            self.assertEqual(
                copy_call.args[0][-1],
                f"container-id:{source_path}",
            )
            self.assertEqual(
                copy_call.kwargs["timeout"],
                container._harness_docker_timeout,
            )
            self.assertFalse(os.path.exists(copy_call.args[0][2]))
            self.assertEqual(
                remove_call.args[0],
                [
                    "docker",
                    "exec",
                    "container-id",
                    "rm",
                    "-f",
                    source_path,
                    binary_path,
                ],
            )
            container._run_command.assert_called_once_with(
                f"cd /code && ./{os.path.basename(binary_path)}",
                "",
                1,
            )
            container.container_id = None
            container.path = None

    @mock.patch("runner._run_process_bounded")
    def test_cpp_compile_error_is_a_solution_error_and_cleans_up(
        self,
        bounded_run,
    ):
        bounded_run.return_value = (1, b"", b"expected ';'", False)
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "bind", language="cpp")

            with self.assertRaisesRegex(
                SolutionException,
                "Compilation failed: expected ';'",
            ):
                container.run_source("this is not C++")

            source_path = bounded_run.call_args.args[0][5]
            self.assertFalse(
                os.path.exists(os.path.join(directory, os.path.basename(source_path)))
            )
            container._run_command.assert_not_called()
            container.container_id = None
            container.path = None

    @mock.patch("runner._run_process_bounded")
    def test_cpp_compile_timeout_is_a_solution_error(self, bounded_run):
        bounded_run.side_effect = subprocess.TimeoutExpired(
            ["docker", "exec", "container-id", "g++"],
            7,
        )
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "bind", language="cpp")

            with self.assertRaisesRegex(
                SolutionException,
                "Compilation timed out after 7 seconds",
            ):
                container.run_source("int main() {}")

            source_path = bounded_run.call_args.args[0][5]
            self.assertFalse(
                os.path.exists(os.path.join(directory, os.path.basename(source_path)))
            )
            container._run_command.assert_not_called()
            container.container_id = None
            container.path = None

    @mock.patch("runner._run_process_bounded")
    def test_cpp_compiler_launch_failure_is_an_execution_error(self, bounded_run):
        bounded_run.side_effect = OSError("docker is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "bind", language="cpp")

            with self.assertRaisesRegex(
                ExecutionException,
                "Error starting the C\\+\\+ test harness compiler",
            ):
                container.run_source("int main() {}")

            container._run_command.assert_not_called()
            container.container_id = None
            container.path = None

    @mock.patch("runner._run_process_bounded")
    def test_cpp_missing_compiler_is_an_execution_error(self, bounded_run):
        bounded_run.return_value = (127, b"", b"g++: not found", False)
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "bind", language="cpp")

            with self.assertRaisesRegex(
                ExecutionException,
                "g\\+\\+: not found",
            ):
                container.run_source("int main() {}")

            container._run_command.assert_not_called()
            container.container_id = None
            container.path = None

    @mock.patch("runner._run_process_bounded")
    def test_cpp_runtime_failure_remains_a_solution_error_and_cleans_up(
        self,
        bounded_run,
    ):
        with tempfile.TemporaryDirectory() as directory:
            container = self._container(directory, "bind", language="cpp")

            def compile_harness(command, *_args):
                local_binary = os.path.join(directory, os.path.basename(command[7]))
                with open(local_binary, "wb") as binary:
                    binary.write(b"compiled")
                return 0, b"", b"", False

            bounded_run.side_effect = compile_harness
            container._run_command.side_effect = SolutionException("student failed")

            with self.assertRaisesRegex(SolutionException, "student failed"):
                container.run_source("int main() { return 1; }")

            compile_command = bounded_run.call_args.args[0]
            for path in (compile_command[5], compile_command[7]):
                self.assertFalse(
                    os.path.exists(os.path.join(directory, os.path.basename(path)))
                )
            container.container_id = None
            container.path = None


class BoundedProcessTests(unittest.TestCase):
    def test_stdout_is_killed_and_capped(self):
        limit = 4096
        _, stdout, stderr, overflow = _run_process_bounded(
            [
                sys.executable,
                "-B",
                "-c",
                "import sys; sys.stdout.write('x' * 200000)",
            ],
            b"",
            3,
            limit,
        )

        self.assertTrue(overflow)
        self.assertEqual(len(stdout), limit)
        self.assertLessEqual(len(stderr), limit)

    def test_stderr_is_killed_and_capped(self):
        limit = 4096
        _, stdout, stderr, overflow = _run_process_bounded(
            [
                sys.executable,
                "-B",
                "-c",
                "import sys; sys.stderr.write('x' * 200000)",
            ],
            b"",
            3,
            limit,
        )

        self.assertTrue(overflow)
        self.assertEqual(len(stderr), limit)
        self.assertLessEqual(len(stdout), limit)

    def test_timeout_keeps_subprocess_semantics(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            _run_process_bounded(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    "import time; time.sleep(10)",
                ],
                b"",
                0.05,
                4096,
            )

    @mock.patch("runner.subprocess.run")
    @mock.patch("runner._run_process_bounded")
    def test_execution_container_reports_output_limit_as_solution_error(
        self,
        bounded_run,
        subprocess_run,
    ):
        bounded_run.return_value = (0, b"x" * 10, b"", True)
        container = object.__new__(ExecutionContainer)
        container.container_id = "container-id"
        container.path = None

        with self.assertRaisesRegex(SolutionException, "Output limit"):
            container._run_command("python3 script.py", "", 1)
        self.assertTrue(container._unusable)
        subprocess_run.assert_called_once()
        container.container_id = None

    @mock.patch("runner._run_process_bounded")
    def test_controller_nonzero_is_an_execution_error(self, bounded_run):
        bounded_run.return_value = (1, b"", b"controller failed", False)
        container = object.__new__(ExecutionContainer)
        container.container_id = "container-id"
        container.path = None

        with self.assertRaisesRegex(ExecutionException, "controller failed"):
            container._run_command(
                "python3 controller.py",
                "",
                1,
                system_on_nonzero=True,
            )
        container.container_id = None

    @mock.patch("runner.subprocess.run")
    @mock.patch("runner._run_process_bounded")
    def test_execution_timeout_remains_a_solution_error(
        self,
        bounded_run,
        subprocess_run,
    ):
        bounded_run.side_effect = subprocess.TimeoutExpired(
            ["docker", "exec"],
            2,
        )
        container = object.__new__(ExecutionContainer)
        container.container_id = "container-id"
        container.path = None

        with self.assertRaisesRegex(
            SolutionException,
            "timed out after 2 seconds",
        ):
            container._run_command("python3 script.py", "", 2)
        self.assertTrue(container._unusable)
        subprocess_run.assert_called_once()
        self.assertEqual(
            subprocess_run.call_args.args[0],
            ["docker", "kill", "container-id"],
        )
        container.container_id = None


if __name__ == "__main__":
    unittest.main()
