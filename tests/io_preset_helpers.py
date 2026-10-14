"""Exercise migrated task contracts with the real IO scorer and a fake sandbox."""
from types import SimpleNamespace
from unittest.mock import patch

from io_test_import import import_environment_tests
from io_tests import IOTestExecutor


def preset(task_id):
    maximum = 10 if task_id == 2599 else 5
    return maximum, import_environment_tests(task_id, 'cpp', maximum)


def program_groups(task_id):
    _, config = preset(task_id)
    keys = [group['id'] for group in config['groups']] or [None]
    return [[{'input': row['input'], 'expected': row['output'],
              'time_limit': row['time_limit']} for row in config['tests']
             if row.get('group') == key] for key in keys]


def perform_io_preset(task_id, runner):
    maximum, config = preset(task_id)
    code = SimpleNamespace(lang='cpp', code='', task=SimpleNamespace(points=maximum, test_config=config))
    with patch('io_tests.ExecutionContainer') as factory:
        factory.return_value.__enter__.return_value.run.side_effect = (
            lambda data, time_limit, capture_limit: runner(data, time_limit))
        points, feedback = IOTestExecutor(code).perform()
    return maximum, points, feedback
