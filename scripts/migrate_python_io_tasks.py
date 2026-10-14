"""Atomically switch the audited Python tasks; never regrade existing solutions."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paste_server import app
from models import Task, db
from io_test_import import PYTHON_TASK_IDS, import_environment_tests, preset_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            raise SystemExit('This release command requires the production PostgreSQL database.')
        try:
            if args.apply:
                # Old suites also get compact list/public-example metadata.
                ids = [row[0] for row in db.session.query(Task.id).filter(Task.test_mode == 'io').all()]
                for task_id in ids:
                    task = Task.query.filter_by(id=task_id).with_for_update().one()
                    if task.test_summary is None:
                        task.test_config = task.test_config
                        db.session.flush()
                    db.session.expunge(task)
            total = 0
            for task_id in sorted(PYTHON_TASK_IDS):
                query = Task.query.filter_by(id=task_id)
                task = (query.with_for_update() if args.apply else query).one()
                metadata = preset_metadata(task_id)
                assert (task.lang, task.points, task.check_type) == ('python', metadata['points'], 'tests'), task_id
                config = import_environment_tests(task_id, task.lang, task.points)
                if args.verify or task.test_mode == 'io':
                    assert task.test_mode == 'io' and task.test_config == config, f'Changed IO configuration: {task_id}'
                    assert task.test_summary == dict(count=len(config['tests']), public_tests=[]), task_id
                elif args.apply:
                    assert task.test_mode == 'environment', task_id
                    task.test_config = config
                    task.test_mode = 'io'
                    db.session.flush()
                total += len(config['tests'])
                print(json.dumps(dict(task=task_id, tests=len(config['tests']), mode=task.test_mode)), flush=True)
                db.session.expunge(task)
            assert total == 1335
            if args.apply:
                db.session.commit()
            else:
                db.session.rollback()
            print(json.dumps(dict(tasks=len(PYTHON_TASK_IDS), tests=total,
                                  result='committed' if args.apply else 'verified' if args.verify else 'dry-run')), flush=True)
        except BaseException:
            db.session.rollback()
            raise


if __name__ == '__main__':
    main()
