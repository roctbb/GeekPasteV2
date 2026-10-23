import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from runner import CPP_PROGRAM_LIMIT, ExecutionContainer, ExecutionException


PROGRAM = b'\x7fELFcompiled program'


@pytest.mark.parametrize('transfer_mode', ['bind', 'cp'])
def test_precompiled_sandbox_skips_compiler_and_restricts_binary(tmp_path, monkeypatch, transfer_mode):
    monkeypatch.setenv('DOCKER_TRANSFER_MODE', transfer_mode)
    monkeypatch.setattr('runner.EXECUTIONS_ROOT', str(tmp_path))
    commands = []

    def docker(command, **kwargs):
        commands.append(command)
        return Mock(stdout=b'test-container\n')

    with patch.object(ExecutionContainer, 'check'), patch('runner.subprocess.run', side_effect=docker), \
            patch.object(ExecutionContainer, '_compile_cpp_harness') as compile_cpp:
        with ExecutionContainer('cpp', '', '', isolated=True, compiled_program=PROGRAM) as container:
            path = os.path.join(container.path, 'program')
            assert Path(path).read_bytes() == PROGRAM
            assert os.stat(path).st_mode & 0o777 == 0o555
            assert not os.path.exists(os.path.join(container.path, 'script.cpp'))
            container._run_command = Mock(return_value='ok')
            assert container.run('input', 0.5) == 'ok'
            container._run_command.assert_called_once_with(
                'cd /tmp && /code/program', 'input', 0.5, capture_limit=102400)
        compile_cpp.assert_not_called()

    command = commands[0]
    assert '--read-only' in command
    assert command[command.index('--cap-drop') + 1] == 'ALL'
    assert command[command.index('--security-opt') + 1] == 'no-new-privileges'
    if transfer_mode == 'bind':
        assert any(arg.endswith(':/code:ro') for arg in command)
    else:
        assert ['docker', 'exec', 'test-container', 'chmod', '0555', '/code'] in commands
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('result', [
    (0, PROGRAM, b'', False),
    (1, b'', b'cat failed', False),
    (0, PROGRAM, b'', True),
    (0, b'invalid program', b'', False),
])
def test_compile_exports_bounded_bytes_and_always_cleans_builder(tmp_path, monkeypatch, result):
    monkeypatch.setattr('runner.EXECUTIONS_ROOT', str(tmp_path))
    with patch.object(ExecutionContainer, 'check'), \
            patch.object(ExecutionContainer, 'prepare', return_value='builder'), \
            patch.object(ExecutionContainer, '_compile_cpp_harness') as compile_cpp, \
            patch('runner.subprocess.run') as docker, \
            patch('runner._run_process_bounded', return_value=result) as export:
        if result == (0, PROGRAM, b'', False):
            assert ExecutionContainer.compile_cpp('source') == PROGRAM
        else:
            with pytest.raises(ExecutionException):
                ExecutionContainer.compile_cpp('source')
        compile_cpp.assert_called_once_with('/code/script.cpp', '/code/program')
        export.assert_called_once_with(
            ['docker', 'exec', 'builder', 'cat', '/code/program'], b'', 10, CPP_PROGRAM_LIMIT)
        assert ['docker', 'rm', 'builder'] in [call.args[0] for call in docker.call_args_list]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('error', [OSError('Docker missing'), subprocess.TimeoutExpired('cat', 10)])
def test_export_failure_cleans_builder(tmp_path, monkeypatch, error):
    monkeypatch.setattr('runner.EXECUTIONS_ROOT', str(tmp_path))
    with patch.object(ExecutionContainer, 'check'), \
            patch.object(ExecutionContainer, 'prepare', return_value='builder'), \
            patch.object(ExecutionContainer, '_compile_cpp_harness'), \
            patch('runner.subprocess.run') as docker, \
            patch('runner._run_process_bounded', side_effect=error), pytest.raises(ExecutionException):
        ExecutionContainer.compile_cpp('source')
    assert ['docker', 'rm', 'builder'] in [call.args[0] for call in docker.call_args_list]
    assert not list(tmp_path.iterdir())


def test_precompiled_program_executes_as_unprivileged_user():
    container = object.__new__(ExecutionContainer)
    container.container_id, container.path = 'runtime', None
    container.compiled_program = PROGRAM
    with patch('runner._run_process_bounded', return_value=(0, b'ok', b'', False)) as process:
        assert container._run_command('cd /tmp && /code/program', 'input', 3) == 'ok'
    assert process.call_args.args[0] == [
        'docker', 'exec', '-i', '--user', '65534:65534', 'runtime', 'bash', '-c', 'cd /tmp && /code/program']
    container.container_id = None


@pytest.mark.parametrize('language, isolated, program', [
    ('python', True, PROGRAM), ('cpp', False, PROGRAM), ('cpp', True, b'not ELF'),
])
def test_invalid_precompiled_program_never_starts_docker(language, isolated, program):
    with patch.object(ExecutionContainer, 'check') as check, pytest.raises(ExecutionException):
        ExecutionContainer(language, '', '', isolated=isolated, compiled_program=program)
    check.assert_not_called()
