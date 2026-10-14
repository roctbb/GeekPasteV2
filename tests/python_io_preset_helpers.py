"""Run the original grade-7 regression cases against migrated web test presets."""
from types import SimpleNamespace
from unittest.mock import patch

from environments.grade7_chapter0_io import (
    TASK_SPECS as ENVIRONMENT_SPECS, TaskSpec, OutputCase, Criterion,
    perform_task as perform_environment_task,
)
from io_test_import import PYTHON_PRESETS, import_environment_tests
from io_tests import IOTestExecutor
from runner import ExecutionException, SolutionException


MIGRATED_GRADE7_IDS = frozenset(int(key) for key, meta in PYTHON_PRESETS.items()
                               if meta['source'] == 'grade7' and int(key) == meta['source_task'])
TASK_SPECS = dict(ENVIRONMENT_SPECS)
MATCHERS = dict(normalized_suffix='suffix', exact_suffix='exact_suffix', last_time='clock', last_integer='final_integer')
for task_id in MIGRATED_GRADE7_IDS:
    meta = PYTHON_PRESETS[str(task_id)]
    config = import_environment_tests(task_id, 'python', meta['points'])
    cases = tuple(OutputCase(key, label, row['input'], ((row['output'],),),
                             MATCHERS[row.get('comparison', config['comparison'])])
                  for key, label, row in zip(meta['case_keys'], meta['case_labels'], config['tests']))
    criteria = tuple(Criterion(group['name'], (tuple(case.key for case, row in zip(cases, config['tests'])
                                                    if row['group'] == group['id']),))
                     for group in config['groups'])
    TASK_SPECS[task_id] = TaskSpec(task_id, f'Frozen task {task_id}', meta['points'], cases, criteria)


def perform_task(task_id, runner, source_code=None):
    if task_id not in MIGRATED_GRADE7_IDS:
        return perform_environment_task(task_id, runner, source_code)
    spec = TASK_SPECS[task_id]
    config = import_environment_tests(task_id, 'python', spec.max_points)
    def run(data, time_limit, capture_limit):
        try:
            output = runner(data)
        except ExecutionException:
            raise
        except Exception as error:
            raise SolutionException(f'{type(error).__name__}: {error}') from error
        output = output.decode('utf-8', errors='replace') if isinstance(output, bytes) else str(output)
        if len(output.encode('utf-8')) > capture_limit:
            raise SolutionException('Output limit exceeded')
        return output
    code = SimpleNamespace(lang='python', code=source_code or '',
                           task=SimpleNamespace(points=spec.max_points, test_config=config))
    with patch('io_tests.ExecutionContainer') as factory:
        factory.return_value.__enter__.return_value.run.side_effect = run
        return IOTestExecutor(code).perform()
