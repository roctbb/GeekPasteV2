from unittest.mock import Mock, patch

import pytest

from external_tests import check_external_tests
from runner import ExecutionContainer, ExecutionException, SolutionException


TESTS = [
    {'input': 'PUBLIC', 'expected': '3'},
    {'input': 'SECRET_INPUT', 'expected': 'SECRET_EXPECTED', 'hidden': True},
    {'input': 'PUBLIC_AFTER_SECRET', 'expected': '5'},
]


def sandbox(output):
    container = Mock()
    if isinstance(output, Exception):
        container.run.side_effect = output
    else:
        container.run.return_value = output
    return container


@pytest.mark.parametrize('error_type, message', [
    ('runtime_error', 'Runtime error: SECRET_STDERR'),
    ('time_limit_exceeded', 'Test failed: Execution timed out after 2 seconds.'),
    ('output_limit_exceeded', 'Output limit exceeded (102400 bytes).'),
])
def test_error_category_and_counts_include_hidden_cases_and_later_tests(error_type, message):
    containers = [sandbox('3'), sandbox(SolutionException(message, error_type)), sandbox('5')]
    with patch('external_tests.ExecutionContainer', side_effect=containers) as factory:
        result = check_external_tests('code', 'cpp', {'tests': TESTS, 'time_limit': 2})
    assert result['verdict'] == result['error_type'] == error_type
    assert result['status'] == 'success'
    assert (result['points'], result['max_points']) == (2, 3)
    assert (result['tests_passed'], result['tests_total']) == (2, 3)
    assert (result['visible_tests_passed'], result['visible_tests_total']) == (2, 2)
    assert (result['hidden_tests_passed'], result['hidden_tests_total']) == (0, 1)
    assert result['details'][1]['error'] == message
    assert result['details'][1]['error_type'] == error_type
    assert result['comment'] == '2 из 3 тестов пройдено'
    assert len(factory.call_args_list) == 3
    assert all(call.kwargs == {'isolated': True} for call in factory.call_args_list)
    for container in containers:
        container.cleanup.assert_called_once()


@pytest.mark.parametrize('outputs, verdict, passed', [
    (['3', 'SECRET_EXPECTED', '5'], 'accepted', 3),
    (['3', 'wrong', '5'], 'wrong_answer', 2),
    (['wrong', 'wrong', 'wrong'], 'wrong_answer', 0),
])
def test_exact_counts_for_accepted_and_wrong_answers(outputs, verdict, passed):
    with patch('external_tests.ExecutionContainer', side_effect=[sandbox(output) for output in outputs]):
        result = check_external_tests('code', 'python', {'tests': TESTS})
    assert result['verdict'] == verdict
    assert result['error_type'] is None
    assert (result['tests_passed'], result['tests_total']) == (passed, 3)


def test_compilation_failure_preserves_full_denominator_and_never_retries_tests():
    with patch('external_tests.ExecutionContainer', side_effect=SolutionException(
            "Compilation failed: expected ';'", 'compilation_error')) as factory:
        result = check_external_tests('broken C++', 'cpp', {'tests': TESTS})
    assert result['verdict'] == 'compilation_error'
    assert (result['points'], result['max_points']) == (0, 3)
    assert (result['tests_passed'], result['tests_total']) == (0, 3)
    assert result['status'] == 'success'
    factory.assert_called_once()


def test_python_syntax_is_a_compilation_error_before_program_execution(tmp_path):
    container = object.__new__(ExecutionContainer)
    container.language = 'python'
    container.path = str(tmp_path)
    container.container_id = None
    container._run_command = Mock(side_effect=SolutionException('Runtime error: SyntaxError: invalid syntax'))
    with pytest.raises(SolutionException) as caught:
        container.setup()
    assert caught.value.error_type == 'compilation_error'
    assert 'SyntaxError' in str(caught.value)
    assert 'py_compile' in container._run_command.call_args.args[0]
    container.path = None


def test_sandbox_failure_is_technical_and_keeps_actual_counts():
    with patch('external_tests.ExecutionContainer', side_effect=[sandbox('3'), ExecutionException('Docker failed')]):
        result = check_external_tests('code', 'python', {'tests': TESTS})
    assert result['verdict'] == 'internal_error'
    assert result['status'] == 'error'
    assert (result['tests_passed'], result['tests_total']) == (1, 3)


def test_fresh_sandboxes_do_not_transfer_hidden_state_to_public_output():
    class StatefulSandbox:
        def __init__(self, *args, **kwargs):
            self.previous_input = ''

        def run(self, input_data, **kwargs):
            previous = self.previous_input
            self.previous_input = input_data
            return previous

        def cleanup(self):
            pass

    with patch('external_tests.ExecutionContainer', StatefulSandbox):
        result = check_external_tests('code', 'python', {'tests': TESTS})
    assert result['details'][2]['got'] == ''


@pytest.mark.parametrize('tests', [[], None, 'invalid', [None]])
def test_invalid_test_config_is_rejected(tests):
    with pytest.raises(ExecutionException):
        check_external_tests('code', 'python', {'tests': tests})
