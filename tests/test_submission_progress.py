import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, call

import submission_progress as progress_store
from methods import build_submission_status_payload, check_task_with_tests
from runner import ExecutionContainer, SolutionException, TestExecutor as EnvironmentExecutor
from tests.test_io_tests import make_code
import paste_server as server


class ProgressStoreTests(unittest.TestCase):
    @patch.object(progress_store, 'client')
    def test_reconnect_reads_counts_but_no_internal_or_test_data(self, client):
        client.get.return_value = json.dumps(dict(phase='testing', completed=2, total=7,
                                                run_id='internal', input='SECRET'))
        self.assertEqual(progress_store.read_submission_progress('CODE'),
                         dict(phase='testing', completed=2, total=7))
        client.get.return_value = None
        self.assertEqual(progress_store.read_submission_progress('CODE'), dict(phase='queued'))
        for value in ('not json', '[]', '{"phase":"testing","completed":8,"total":7}'):
            client.get.return_value = value
            result = progress_store.read_submission_progress('CODE')
            self.assertNotIn('completed', result)

    @patch.object(progress_store, 'client')
    def test_superseded_worker_cannot_emit_stale_progress(self, client):
        client.eval.return_value = 1
        emit = Mock()
        report = progress_store.start_submission_progress('CODE', emit)
        emit.assert_called_once_with({'phase': 'preparing'})
        emit.reset_mock()
        client.eval.return_value = 0
        report('testing', completed=2, total=7)
        emit.assert_not_called()

    @patch.object(progress_store, 'client')
    def test_progress_outage_does_not_break_grading_or_invent_a_stage(self, client):
        client.get.side_effect = OSError('offline')
        client.setex.side_effect = OSError('offline')
        client.delete.side_effect = OSError('offline')
        emit = Mock(side_effect=OSError('socket offline'))
        self.assertEqual(progress_store.read_submission_progress('CODE'), {'phase': 'unknown'})
        report = progress_store.start_submission_progress('CODE', emit)
        report('testing', completed=1, total=2)
        progress_store.clear_submission_progress('CODE')
        self.assertEqual(emit.call_count, 2)

    @patch('methods.read_submission_progress')
    def test_terminal_grade_wins_over_stale_progress(self, read):
        code = make_code()
        code.check_state, code.check_points, code.check_comments, code.checked_at = 'done', 10, '', None
        payload = build_submission_status_payload(code)
        self.assertEqual(payload['check_progress'], {'phase': 'finished'})
        self.assertEqual(payload['max_points'], 10)
        read.assert_not_called()
        code.check_state = 'not checked'
        read.return_value = {'phase': 'compiling'}
        self.assertEqual(build_submission_status_payload(code)['check_progress'], {'phase': 'compiling'})


class ExecutorProgressTests(unittest.TestCase):
    @patch('io_tests.ExecutionContainer')
    def test_counts_advance_after_execution_including_failed_private_cases(self, factory):
        events = []
        code = make_code()
        code.task.test_config['tests'].reverse()  # Private failing case first.
        def run(value, **kwargs):
            self.assertEqual(events[-1], ('testing', len([e for e in events if e[0] == 'finished_case']), 2))
            events.append(('finished_case', None, None))
            if value == 'SECRET_INPUT':
                raise SolutionException('SECRET ERROR')
            return '5\n'
        factory.return_value.__enter__.return_value.run.side_effect = run
        report = lambda phase, completed=None, total=None: events.append((phase, completed, total))
        check_task_with_tests(code.task, code, progress=report)
        self.assertEqual([e for e in events if e[0] == 'testing'],
                         [('testing', 0, 2), ('testing', 1, 2), ('testing', 1, 2), ('testing', 2, 2)])
        self.assertNotIn('compiling', [e[0] for e in events])
        self.assertNotIn('SECRET', str(events))
        self.assertEqual((code.check_state, code.check_points), ('partially done', 5))

    def test_compile_event_precedes_compiler_and_failure_never_reports_testing(self):
        events = []
        container = ExecutionContainer.__new__(ExecutionContainer)
        container.language = 'cpp'
        container.compiled_program = None
        container.container_id = container.path = None
        container.on_compile = lambda: events.append('compiling')
        def compile_program(*args):
            events.append('compiler')
            raise SolutionException('bad code', 'compilation_error')
        container._compile_cpp_harness = compile_program
        with self.assertRaises(SolutionException):
            container.setup()
        self.assertEqual(events, ['compiling', 'compiler'])

    @patch('runner.ExecutionContainer')
    def test_environment_checker_reports_testing_without_made_up_counts(self, factory):
        import os
        code = make_code()
        code.lang = 'cpp'
        report = Mock()
        def create(*args, **kwargs):
            kwargs['on_compile']()
            return SimpleNamespace(path=os.getcwd(), cleanup=Mock())
        factory.side_effect = create
        tester = SimpleNamespace(perform_tests=Mock(return_value=(10, 'ok')))
        with patch.object(EnvironmentExecutor, '_load_tester_module', return_value=tester):
            with EnvironmentExecutor(code, progress=report) as executor:
                self.assertEqual(executor.perform(), (10, 'ok'))
        self.assertEqual(report.call_args_list, [call('compiling'), call('testing')])


class ProgressEndpointTests(unittest.TestCase):
    def test_polling_uses_the_same_access_rules_as_live_events(self):
        code = make_code()
        code.check_state, code.check_points, code.check_comments, code.checked_at = 'not checked', 0, '', None
        code.available_without_auth = False
        client = server.app.test_client()
        with patch.object(server, 'get_code', return_value=code), patch('methods.read_submission_progress', return_value={'phase': 'testing'}):
            self.assertEqual(client.get('/submission/status?id=IO').status_code, 403)
            with client.session_transaction() as session:
                session.update(user_id=99, role='student')
            self.assertEqual(client.get('/submission/status?id=IO').status_code, 403)
            for user_id, role in [(1, 'student'), (99, 'teacher')]:
                with client.session_transaction() as session:
                    session.update(user_id=user_id, role=role)
                response = client.get('/submission/status?id=IO')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['check_progress'], {'phase': 'testing'})
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            with client.session_transaction() as session:
                session.clear()
            code.available_without_auth = True
            self.assertEqual(client.get('/submission/status?id=IO').status_code, 200)
        with patch.object(server, 'get_code', return_value=None):
            self.assertEqual(client.get('/submission/status?id=missing').status_code, 404)
