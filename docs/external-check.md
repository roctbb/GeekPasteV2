# External test checking

`POST /api/external/check` with `check_type: "tests"` reports its result to the authenticated callback. The callback retains `points`, `max_points`, `comment` and `details`, and also includes:

- `verdict`: `accepted`, `wrong_answer`, `compilation_error`, `runtime_error`, `time_limit_exceeded`, `output_limit_exceeded` or `internal_error`.
- `error_type`: the error category above, or `null` for accepted solutions and wrong answers. The first execution error determines the category; an infrastructure error takes precedence.
- `tests_passed`, `tests_total`: exact counts of every configured test, including those marked `hidden: true`.
- `visible_tests_passed`, `visible_tests_total`, `hidden_tests_passed`, `hidden_tests_total`: counts split by visibility.

For this mode, `points == tests_passed` and `max_points == tests_total`. A compilation failure reports `0` out of the full configured total, without retrying an invalid solution. `status: "success"` means the checker completed, including when the solution failed compilation or execution; infrastructure failures use `status: "error"`. Partial counts on infrastructure failure describe tests passed before checking stopped.

Each test runs in a fresh isolated sandbox. A timeout cannot invalidate later tests, and files from a hidden test cannot be read by a later public test.

C++ is compiled once per external job in a separate build sandbox that never receives test input. The bounded ELF binary is exported to immutable worker memory, and each test receives its own copy. Runtime containers do not compile again: they run as an unprivileged user, with the program and `/code` protected from writes and a fresh writable `/tmp`. Both `DOCKER_TRANSFER_MODE=cp` and `bind` are supported. Build and runtime containers are removed on success and failure. Existing native task harnesses keep their compilation behavior.

Time limits accept `time_limit_ms` (milliseconds, including fractional seconds after conversion) and legacy `time_limit` (seconds). Per-test settings override job settings; within either level `time_limit_ms` takes precedence. Missing limits default to 5 seconds. Limits must be positive finite numbers and cover execution, independently of the compiler timeout.

The Compose checker worker defaults to two concurrent jobs, with tests sequential inside each job. Set `CELERY_CHECK_CONCURRENCY` in the Compose environment to tune the shared checker load. This setting takes effect when the worker is recreated; changing source or pushing a commit does not update running containers.

The calling application must budget for queue wait, one compilation, and all test sandbox startups and executions. A fixed 180-second response deadline can expire before legitimate checks finish. GeekCodeBattle now defaults to 600 seconds and can accept a matching job's late result after its own technical timeout; it preserves results for closed rounds without automatically changing their scoring.

Run the focused unit tests with `python -m pytest -q tests/test_external_tests.py tests/test_compiled_program.py tests/test_runner_harness.py tests/test_api_grading.py`. Real Docker checks use `RUN_EXTERNAL_DOCKER_INTEGRATION=1 python -m unittest discover -s tests -p test_external_docker_integration.py -v`. They cover one compilation for 52 cases, hidden-to-public file isolation, binary write protection, timeout recovery, and cleanup. Optionally set `EXTERNAL_TEST_BENCHMARK_CONFIG` to a JSON check configuration with 52 tests to benchmark an actual task.

`details` is trusted-server data and may contain private inputs, expected/actual outputs, and stderr. A student-facing application must expose only the allowlisted category and aggregate counts for hidden tests. It must never forward raw callback diagnostics for these tests. These fields are not test counts for `check_type: "gpt"`.
