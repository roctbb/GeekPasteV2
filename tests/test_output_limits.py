from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from io_tests import draft_test_config_from_form, validate_form_draft, validate_test_config
from runner import ExecutionContainer


def test_default_output_limit_matches_the_editor_and_runtime():
    config = validate_test_config({'tests': [{'input': '', 'output': 'x' * 200000, 'is_public': False}]})
    assert config['output_limit'] == 8 * 1024 * 1024
    form = MultiDict({'test_input': '', 'test_output': 'x', 'test_visibility': 'private'})
    draft, error = draft_test_config_from_form(form, MultiDict())
    assert error is None
    assert draft['output_limit'] == '8192'
    assert validate_form_draft(draft, 10)['output_limit'] == config['output_limit']


def test_explicit_task_and_case_output_limits_are_preserved():
    config = validate_test_config({'output_limit': 32768, 'tests': [
        {'input': '', 'output': '', 'is_public': False, 'output_limit': 1024},
        {'input': '', 'output': '', 'is_public': False},
    ]})
    assert config['output_limit'] == 32768
    assert config['tests'][0]['output_limit'] == 1024
    assert 'output_limit' not in config['tests'][1]


def test_direct_program_output_uses_eight_megabytes_by_default():
    container = object.__new__(ExecutionContainer)
    container.container_id, container.path = 'runtime', None
    container.compiled_program = None
    with patch('runner._run_process_bounded', return_value=(0, b'x' * 200000, b'', False)) as process:
        assert len(container._run_command('program', '', 2)) == 200000
        assert process.call_args.args[3] == 8 * 1024 * 1024
    container.container_id = None


def test_compiler_diagnostics_keep_their_separate_limit():
    container = object.__new__(ExecutionContainer)
    container.container_id, container.path = 'compiler', None
    with patch('runner._run_process_bounded', return_value=(0, b'', b'', False)) as process:
        container._compile_cpp_harness('/code/script.cpp', '/code/program')
        assert process.call_args.args[3] == 100 * 1024
    container.container_id = None
