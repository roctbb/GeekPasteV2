"""Exercise migrated task contracts with the real IO scorer and a fake sandbox."""
from types import SimpleNamespace
from unittest.mock import patch

from io_test_import import import_environment_tests, preset_metadata
from io_tests import IOTestExecutor, outputs_equal


def preset(task_id):
    maximum = preset_metadata(task_id)['points']
    return maximum, import_environment_tests(task_id, 'cpp', maximum)


def program_groups(task_id):
    from environments.grade8_2026_common import tokens_equal, exact_text_equal, float_tokens_equal
    from environments.grade8_2026_chapters_1_4 import strict_text_equal
    _, config = preset(task_id)
    metadata = preset_metadata(task_id)
    comparisons = {'tokens_ignore_cr': tokens_equal, 'exact': strict_text_equal,
                   'exact_crlf': exact_text_equal, 'float_binary64': float_tokens_equal,
                   'magic_mismatch': lambda actual, expected: outputs_equal(actual, expected, 'magic_mismatch')}
    keys = [group['id'] for group in config['groups']] or [None]
    groups = {key: [] for key in keys}
    for index, row in enumerate(config['tests']):
        case = {'input': row['input'], 'expected': row['output'],
                'time_limit': row.get('time_limit', config['time_limit']),
                'comparator': comparisons[row.get('comparison', config['comparison'])],
                'kind': metadata.get('kinds', ['hidden'] * len(config['tests']))[index]}
        capture = row.get('output_limit', config['output_limit'])
        if capture != 102400:
            case['capture_limit'] = capture
        groups[row.get('group')].append(case)
    return list(groups.values())


def perform_io_preset(task_id, runner):
    maximum, config = preset(task_id)
    code = SimpleNamespace(lang='cpp', code='', task=SimpleNamespace(points=maximum, test_config=config))
    with patch('io_tests.ExecutionContainer') as factory:
        factory.return_value.__enter__.return_value.run.side_effect = (
            lambda data, time_limit, capture_limit: runner(data, time_limit)
            if capture_limit == 102400 else runner(data, time_limit, capture_limit))
        points, feedback = IOTestExecutor(code).perform()
    return maximum, points, feedback


def preset_entry(task_id):
    maximum, _ = preset(task_id)
    def handler(runner, source_code=''):
        return perform_io_preset(task_id, runner)[1:]
    return maximum, handler
