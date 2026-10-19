# External test checking

`POST /api/external/check` with `check_type: "tests"` reports its result to the authenticated callback. The callback retains `points`, `max_points`, `comment` and `details`, and also includes:

- `verdict`: `accepted`, `wrong_answer`, `compilation_error`, `runtime_error`, `time_limit_exceeded`, `output_limit_exceeded` or `internal_error`.
- `error_type`: the error category above, or `null` for accepted solutions and wrong answers. The first execution error determines the category; an infrastructure error takes precedence.
- `tests_passed`, `tests_total`: exact counts of every configured test, including those marked `hidden: true`.
- `visible_tests_passed`, `visible_tests_total`, `hidden_tests_passed`, `hidden_tests_total`: counts split by visibility.

For this mode, `points == tests_passed` and `max_points == tests_total`. A compilation failure reports `0` out of the full configured total, without retrying an invalid solution. `status: "success"` means the checker completed, including when the solution failed compilation or execution; infrastructure failures use `status: "error"`. Partial counts on infrastructure failure describe tests passed before checking stopped.

Each test runs in a fresh isolated sandbox. A timeout cannot invalidate later tests, and files from a hidden test cannot be read by a later public test.

`details` is trusted-server data and may contain private inputs, expected/actual outputs, and stderr. A student-facing application must expose only the allowlisted category and aggregate counts for hidden tests. It must never forward raw callback diagnostics for these tests. These fields are not test counts for `check_type: "gpt"`.
