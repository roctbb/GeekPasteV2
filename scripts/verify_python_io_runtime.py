"""Run exported reference algorithms through the real isolated IO executor."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from io_test_import import PYTHON_TASK_IDS, import_environment_tests, preset_metadata
from io_tests import IOTestExecutor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('references', type=Path)
    parser.add_argument('--task', type=int, action='append')
    parser.add_argument('--boundary-cases', action='store_true',
                        help='For large all-or-nothing suites, run first/last and largest input/output cases.')
    args = parser.parse_args()
    programs = json.loads(args.references.read_text())
    failures = []
    for task_id in args.task or sorted(PYTHON_TASK_IDS):
        maximum = preset_metadata(task_id)['points']
        config = import_environment_tests(task_id, 'python', maximum)
        total = len(config['tests'])
        if args.boundary_cases and total > 10 and config['scoring'] == 'all_or_nothing':
            rows = config['tests']
            selected = {0, total - 1, max(range(total), key=lambda i: len(rows[i]['input'])),
                        max(range(total), key=lambda i: len(rows[i]['output']))}
            config = dict(config, tests=[rows[i] for i in sorted(selected)])
        code = SimpleNamespace(lang='python', code=programs[str(task_id)],
                               task=SimpleNamespace(points=maximum, test_config=config))
        executor = IOTestExecutor(code)
        points, report = executor.perform()
        print(json.dumps(dict(task=task_id, executed_tests=len(config['tests']), total_tests=total, points=points,
                              maximum=maximum, all_passed=executor.all_passed)), flush=True)
        if points != maximum or not executor.all_passed:
            print(report, flush=True)
            failures.append(task_id)
    if failures:
        raise SystemExit(f'Failed reference solutions: {failures}')


if __name__ == '__main__':
    main()
