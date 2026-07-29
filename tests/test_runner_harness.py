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

    def run(self, input_data, time_limit=1):
        self.calls.append(("run", input_data, time_limit))
        return "program output"

    def run_source(
        self,
        source_code,
        input_data="",
        time_limit=1,
        probe_source=None,
    ):
        self.calls.append(
            ("run_source", source_code, input_data, time_limit, probe_source)
        )
        return "harness output"


class TestRunnerTests(unittest.TestCase):
    def test_facade_preserves_the_existing_callable_api(self):
        container = FakeContainer()
        runner = RunnerFacade(container)

        self.assertEqual(runner("input\n", 3), "program output")
        self.assertEqual(container.calls, [("run", "input\n", 3)])

    def test_facade_exposes_isolated_source_execution(self):
        container = FakeContainer()
        runner = RunnerFacade(container)

        self.assertEqual(
            runner.run_source("print('test')", "stdin\n", 4),
            "harness output",
        )
        self.assertEqual(
            container.calls,
            [("run_source", "print('test')", "stdin\n", 4, None)],
        )


class ExecutionContainerHarnessTests(unittest.TestCase):
    def _container(self, directory, transfer_mode):
        container = object.__new__(ExecutionContainer)
        container.language = "python"
        container.path = directory
        container.container_id = "container-id"
        container._docker_transfer_mode = transfer_mode
        container._run_command = mock.Mock(return_value="ok")
        return container

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

    @mock.patch("runner._run_process_bounded")
    def test_execution_container_reports_output_limit_as_solution_error(
        self,
        bounded_run,
    ):
        bounded_run.return_value = (0, b"x" * 10, b"", True)
        container = object.__new__(ExecutionContainer)
        container.container_id = "container-id"
        container.path = None

        with self.assertRaisesRegex(SolutionException, "Output limit"):
            container._run_command("python3 script.py", "", 1)
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

    @mock.patch("runner._run_process_bounded")
    def test_execution_timeout_remains_a_solution_error(self, bounded_run):
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
        container.container_id = None


if __name__ == "__main__":
    unittest.main()
