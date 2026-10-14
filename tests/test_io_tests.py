import copy
import hashlib
from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from werkzeug.datastructures import MultiDict

import io_tests as io_checks
import methods
from io_test_import import (PILOT_TASK_IDS, PRESETS_PATH, ADDITIONAL_TASK_IDS,
                            REMAINING_PATH, REMAINING_PRESETS, import_environment_tests)
import paste_server as server
from models import Task, db
from runner import ExecutionException, SolutionException


CONFIG = {
    'comparison': 'tokens', 'time_limit': 2,
    'tests': [
        {'input': '2 3\n', 'output': '5\n', 'is_public': True},
        {'input': 'SECRET_INPUT', 'output': 'SECRET_OUTPUT', 'is_public': False},
    ],
}


def make_code(points=10, config=None):
    return SimpleNamespace(
        id='IO', code='print(input())', lang='python', task_id=9000, user_id=1, course_id=1,
        task=SimpleNamespace(id=9000, points=points, test_mode='io', check_type='tests',
                             test_config=copy.deepcopy(config or CONFIG)),
    )


class IOCheckerTests(unittest.TestCase):
    def test_comparison_contract(self):
        self.assertTrue(io_checks.outputs_equal('1  \n2\t', '1 2', 'tokens'))
        self.assertFalse(io_checks.outputs_equal('12', '1 2', 'tokens'))
        self.assertFalse(io_checks.outputs_equal('YES', 'yes', 'tokens'))
        self.assertFalse(io_checks.outputs_equal('1.0', '1', 'tokens'))
        self.assertTrue(io_checks.outputs_equal(' a\r\nb\r\n', ' a\nb', 'exact'))
        self.assertFalse(io_checks.outputs_equal(' a \nb', ' a\nb', 'exact'))
        self.assertFalse(io_checks.outputs_equal('a\n\n', 'a\n', 'exact'))
        self.assertTrue(io_checks.outputs_equal('', '', 'exact'))

    def test_config_validation_and_empty_strings(self):
        invalid = [None, {}, {**CONFIG, 'tests': []}, {**CONFIG, 'tests': CONFIG['tests'] * 26},
                   {**CONFIG, 'time_limit': 0}, {**CONFIG, 'time_limit': 31},
                   {**CONFIG, 'time_limit': True}, {**CONFIG, 'time_limit': 1.5},
                   {**CONFIG, 'comparison': 'unknown'}]
        for test in ({'input': '', 'output': '', 'is_public': 'false'},
                     {'input': [], 'output': '', 'is_public': False},
                     {'input': 'я' * (io_checks.MAX_TEXT_BYTES // 2 + 1), 'output': '', 'is_public': False}):
            invalid.append({**CONFIG, 'tests': [test]})
        invalid.append({**CONFIG, 'tests': [{'input': 'x' * io_checks.MAX_TEXT_BYTES, 'output': '', 'is_public': False}] * 9})
        for config in invalid:
            with self.subTest(index=invalid.index(config)), self.assertRaises(ValueError):
                io_checks.validate_test_config(config)
        config = io_checks.validate_test_config({**CONFIG, 'tests': [
            {'input': '', 'output': '', 'is_public': False},
            {'input': '\r\na\r\n', 'output': ' \r\n', 'is_public': True},
        ]})
        self.assertEqual(config['tests'][0]['input'], '')
        self.assertEqual(config['tests'][1]['input'], '\na\n')

    @patch('io_tests.ExecutionContainer')
    def test_partial_credit_and_private_output_never_reach_report(self, factory):
        first, second = Mock(), Mock()
        first.__enter__ = Mock(return_value=first)
        first.__exit__ = Mock()
        second.__enter__ = Mock(return_value=second)
        second.__exit__ = Mock()
        first.run.return_value = '5\n'
        second.run.return_value = 'SECRET_ACTUAL'
        factory.side_effect = [first, second]
        code = make_code()
        methods.check_task_with_tests(code.task, code)
        self.assertEqual(code.check_points, 5)
        self.assertEqual(code.check_state, 'partially done')
        self.assertNotIn('SECRET', code.check_comments)
        self.assertIn('приватный', code.check_comments)
        self.assertEqual(factory.call_count, 2)
        for call in factory.call_args_list:
            self.assertEqual(call.args, ('python', None, code.code))
            self.assertEqual(call.kwargs, {'isolated': True})
        first.run.assert_called_once_with('2 3\n', time_limit=2, capture_limit=102400)
        second.run.assert_called_once_with('SECRET_INPUT', time_limit=2, capture_limit=102400)
        first.__exit__.assert_called_once()
        second.__exit__.assert_called_once()

    @patch('io_tests.ExecutionContainer')
    def test_private_exception_is_hidden_and_following_test_still_runs(self, factory):
        factory.return_value.__enter__.return_value.run.side_effect = [
            SolutionException('SECRET_INPUT in stderr'), '<script>bad</script>',
        ]
        config = copy.deepcopy(CONFIG)
        config['tests'].reverse()
        code = make_code(config=config)
        methods.check_task_with_tests(code.task, code)
        self.assertEqual(code.check_points, 1)
        self.assertNotIn('SECRET', code.check_comments)
        self.assertIn('&lt;script&gt;', code.check_comments)
        self.assertIn('Ожидаемый вывод', code.check_comments)
        self.assertEqual(factory.call_count, 2)

    @patch('io_tests.ExecutionContainer')
    def test_full_credit_and_single_point_task_status(self, factory):
        run = factory.return_value.__enter__.return_value.run
        run.side_effect = ['5', 'SECRET_OUTPUT']
        code = make_code()
        methods.check_task_with_tests(code.task, code)
        self.assertEqual((code.check_points, code.check_state), (10, 'done'))
        run.side_effect = ['wrong', 'wrong']
        code = make_code(points=1)
        methods.check_task_with_tests(code.task, code)
        self.assertEqual((code.check_points, code.check_state), (1, 'partially done'))

    @patch('methods.send_telegram_message')
    @patch('io_tests.ExecutionContainer')
    def test_infrastructure_error_does_not_expose_private_data(self, factory, notify):
        factory.return_value.__enter__.return_value.run.side_effect = ExecutionException('SECRET stderr')
        code = make_code()
        methods.check_task_with_tests(code.task, code)
        self.assertEqual(code.check_state, 'execution error')
        self.assertNotIn('SECRET', code.check_comments)
        self.assertNotIn('SECRET', str(notify.call_args))

    @patch('io_tests.ExecutionContainer')
    def test_invalid_configuration_never_runs_student_code(self, factory):
        code = make_code()
        code.task.test_config = {'tests': []}
        with self.assertRaises(ExecutionException):
            io_checks.IOTestExecutor(code).perform()
        factory.assert_not_called()


class IOWebBase(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
        self.app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(self.app)
        for path, view, method in [('/tasks/new', server.tasks_new, 'GET'),
                                   ('/tasks', server.tasks_create, 'POST'),
                                   ('/tasks', server.tasks_list, 'GET'),
                                   ('/tasks/<int:task_id>/edit', server.tasks_edit, 'GET'),
                                   ('/tasks/<int:task_id>/import-tests', server.tasks_import_tests, 'GET'),
                                   ('/tasks/<int:task_id>/test-data/<token>', server.tasks_test_data, 'GET'),
                                   ('/tasks/<int:task_id>', server.tasks_update, 'POST'),
                                   ('/tasks/<int:task_id>/delete', server.tasks_delete, 'POST'),
                                   ('/', server.index, 'GET')]:
            self.app.add_url_rule(path, view_func=view, methods=[method])
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.login('teacher')

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def login(self, role):
        with self.client.session_transaction() as session:
            session['user_id'] = 1
            session['role'] = role

    def form(self, **overrides):
        data = {'name': 'Сумма', 'lang': 'python', 'points': '10', 'check_type': 'tests',
                'test_mode': 'io', 'test_time_limit': '2', 'test_comparison': 'tokens',
                'test_input': ['2 3\n', 'SECRET_INPUT'],
                'test_output': ['5\n', 'SECRET_OUTPUT'], 'test_visibility': ['public', 'private']}
        data.update(overrides)
        result = MultiDict(data)
        for key, value in overrides.items():
            if isinstance(value, tuple) and isinstance(value[0], BytesIO):
                result[key] = value
        return result

    def create(self):
        response = self.client.post('/tasks', data=self.form())
        self.assertEqual(response.status_code, 302)
        return Task.query.one()



class IOWebTests(IOWebBase):
    def test_teacher_can_create_edit_reorder_remove_and_recheck(self):
        task = self.create()
        self.assertEqual(task.test_config, io_checks.validate_test_config(CONFIG))
        response = self.client.get(f'/tasks/{task.id}/edit')
        self.assertIn('SECRET_INPUT', response.text)
        self.assertIn('SECRET_OUTPUT', response.text)
        response = self.client.post(f'/tasks/{task.id}', data=self.form(
            test_input=['SECRET_INPUT', '2 3\n'], test_output=['SECRET_OUTPUT', '5\n'],
            test_visibility=['private', 'public']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.test_config['tests'][0]['input'], 'SECRET_INPUT')
        with patch.object(server, '_queue_mass_recheck', return_value=2) as recheck:
            response = self.client.post(f'/tasks/{task.id}', data=self.form(
                test_input=[''], test_output=[''], test_visibility=['public'], mass_recheck='on'))
            self.assertEqual(response.status_code, 302)
            recheck.assert_called_once_with(task.id)
            self.assertEqual(task.test_config['tests'], [{'input': '', 'output': '', 'is_public': True}])
        self.assertIn('Ввод / вывод', self.client.get('/tasks').text)
        self.assertEqual(self.client.post(f'/tasks/{task.id}/delete').status_code, 302)
        self.assertEqual(Task.query.count(), 0)

    def test_student_sees_only_public_examples_and_cannot_edit_tests(self):
        task = self.create()
        self.login('student')
        response = self.client.get(f'/?task_id={task.id}&course_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn('2 3', response.text)
        self.assertIn('Публичные тесты', response.text)
        self.assertNotIn('SECRET', response.text)
        self.assertEqual(self.client.get(f'/tasks/{task.id}/edit').status_code, 403)
        self.assertEqual(self.client.get('/tasks/new').status_code, 403)
        self.assertEqual(self.client.post('/tasks', data=self.form()).status_code, 403)
        self.assertEqual(self.client.post(f'/tasks/{task.id}', data=self.form()).status_code, 403)
        self.assertEqual(Task.query.count(), 1)

    def test_invalid_updates_are_atomic_and_preserve_entered_values(self):
        task = self.create()
        invalid = [dict(test_input=[], test_output=[], test_visibility=[]), dict(test_time_limit='nan'),
                   dict(test_visibility=['public']), dict(test_visibility=['public', 'hidden']),
                   dict(test_comparison='bad'), dict(lang='js'), dict(points='0'), dict(points='1.5')]
        for fields in invalid:
            with self.subTest(fields=fields):
                response = self.client.post(f'/tasks/{task.id}', data=self.form(name='Несохранённое', **fields))
                self.assertEqual(response.status_code, 400)
                self.assertIn('Несохранённое', response.text)
                db.session.expire_all()
                self.assertEqual(task.name, 'Сумма')
                self.assertEqual(task.test_config, io_checks.validate_test_config(CONFIG))
        self.assertEqual(self.client.post('/tasks', data=self.form(id=str(task.id))).status_code, 400)
        self.assertEqual(Task.query.count(), 1)

    def test_switching_modes_preserves_saved_tests_and_legacy_form_works(self):
        task = self.create()
        for mode, check_type in [('environment', 'tests'), ('io', 'gpt')]:
            response = self.client.post(f'/tasks/{task.id}', data={
                'name': task.name, 'lang': 'python', 'points': '10',
                'test_mode': mode, 'check_type': check_type})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(task.test_config, io_checks.validate_test_config(CONFIG))
            self.assertEqual(io_checks.public_tests(task), [])
        response = self.client.post('/tasks', data={
            'name': 'Legacy', 'lang': 'python', 'points': '5', 'check_type': 'tests'})
        self.assertEqual(response.status_code, 302)
        legacy = Task.query.filter_by(name='Legacy').one()
        self.assertEqual(legacy.test_mode, 'environment')
        self.assertIsNone(legacy.test_config)

    def test_examples_are_escaped_and_whitespace_survives_form_rendering(self):
        self.client.post('/tasks', data=self.form(test_input=['\n<script>alert(1)</script>\n'],
                                                test_output=['  \n'], test_visibility=['public']))
        task = Task.query.one()
        html = self.client.get(f'/tasks/{task.id}/edit').text
        self.assertIn('\n\n&lt;script&gt;alert(1)&lt;/script&gt;\n</textarea>', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.login('student')
        html = self.client.get(f'/?task_id={task.id}&course_id=1').text
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_large_valid_multipart_form_can_be_saved(self):
        response = self.client.post('/tasks', data=self.form(
            test_input=['x' * 65536] * 10, test_output=[''] * 10,
            test_visibility=['private'] * 10), content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(Task.query.one().test_config['tests']), 10)


class IOAdvancedTests(unittest.TestCase):
    def test_float_absolute_relative_and_text_contract(self):
        def equal(actual, expected, absolute='0', relative='0'):
            return io_checks.outputs_equal(actual, expected, 'float',
                                           absolute_tolerance=absolute, relative_tolerance=relative)
        self.assertTrue(equal('OK 1.0 -2e3', 'OK 1 -2000'))
        self.assertTrue(equal('0.000001', '0', '0.000001'))
        self.assertFalse(equal('0.0000011', '0', '0.000001'))
        self.assertTrue(equal('1000001', '1000000', relative='0.000001'))
        self.assertFalse(equal('1000002', '1000000', relative='0.000001'))
        self.assertFalse(equal('ok 1', 'OK 1'))
        self.assertFalse(equal('1 2', '1'))
        for token in ('nan', 'NaN', '-inf', '+Infinity', '1e99999999999999999999'):
            self.assertFalse(equal(token, token))
        self.assertFalse(equal('1.' + '0' * 99 + '1', '1'))
        self.assertFalse(equal('0.1' + '0' * 150 + '1', '0', '0.1'))
        config = io_checks.validate_test_config({**CONFIG, 'absolute_tolerance': '-0e99999999'})
        self.assertEqual(config['absolute_tolerance'], '0')
        for tolerance in ('nan', '-1', '1.1', 'inf', 'invalid', True, '1e-999999999'):
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                io_checks.validate_test_config({**CONFIG, 'absolute_tolerance': tolerance})

    def test_exact_trailing_rules_and_legacy_carriage_returns(self):
        self.assertTrue(io_checks.outputs_equal('a\n\n', 'a', 'exact', trailing_whitespace='newlines'))
        self.assertFalse(io_checks.outputs_equal('a \n', 'a', 'exact', trailing_whitespace='newlines'))
        self.assertTrue(io_checks.outputs_equal('a \n', 'a', 'exact', trailing_whitespace='all'))
        self.assertTrue(io_checks.outputs_equal('1\r2', '12', 'tokens_ignore_cr'))
        self.assertFalse(io_checks.outputs_equal('1\r2', '12', 'tokens'))

    def grouped(self):
        return {**CONFIG, 'scoring': 'groups',
                'groups': [{'id': 'a', 'name': 'SECRET_GROUP', 'points': 3},
                           {'id': 'b', 'name': 'Другая', 'points': 7}],
                'tests': [dict(CONFIG['tests'][0], group='a'),
                          dict(CONFIG['tests'][1], group='a'),
                          dict(CONFIG['tests'][0], group='b')]}

    def test_group_scores_privacy_and_configuration_rejections(self):
        config = io_checks.validate_test_config(self.grouped(), 10)
        points, comments = io_checks.score_results(config, [True, False, True], 10)
        self.assertEqual(points, 7)
        self.assertNotIn('SECRET', str(comments))
        self.assertEqual(io_checks.score_results(config, [True] * 3, 10)[0], 10)
        mutations = [dict(groups=config['groups'] * 2), dict(groups=[]),
                     dict(tests=[config['tests'][0]]),
                     dict(tests=[dict(config['tests'][0], group='missing')]),
                     dict(groups=[dict(config['groups'][0], points=4), config['groups'][1]])]
        for fields in mutations:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                io_checks.validate_test_config({**config, **fields}, 10)
        for field, value in [('time_limit', 31), ('output_limit', 8192 * 1024 + 1), ('output_limit', True)]:
            with self.assertRaises(ValueError):
                io_checks.validate_test_config({**CONFIG, 'tests': [dict(CONFIG['tests'][0], **{field: value})]})

    @patch('io_tests.ExecutionContainer')
    def test_worker_uses_group_scores_limits_and_all_or_nothing(self, factory):
        config = self.grouped()
        config['tests'][0].update(time_limit=4, output_limit=2 * 1024 * 1024)
        run = factory.return_value.__enter__.return_value.run
        run.side_effect = ['5', 'wrong', '5']
        code = make_code(config=config)
        methods.check_task_with_tests(code.task, code)
        self.assertEqual((code.check_points, code.check_state), (7, 'partially done'))
        self.assertNotIn('SECRET', code.check_comments)
        self.assertEqual(run.call_args_list[0].kwargs, dict(time_limit=4, capture_limit=2 * 1024 * 1024))
        run.side_effect = ['5', 'wrong']
        code = make_code(config={**CONFIG, 'scoring': 'all_or_nothing'})
        methods.check_task_with_tests(code.task, code)
        self.assertEqual((code.check_points, code.check_state), (1, 'partially done'))

    def test_frozen_presets_keep_migrated_cases_scores_and_limits(self):
        # Exported from ae5f534, compared against the old handlers before retirement.
        self.assertEqual(hashlib.sha256(PRESETS_PATH.read_bytes()).hexdigest(),
                         '760b385451994b3526bd470da58246332f936f5bf7b97307b6435d5c554a63c3')
        counts = {2593: 1, 2594: 8, 2595: 8, 2596: 8, 2597: 10, 2598: 6,
                  2599: 8, 2600: 6, 2605: 3, 2611: 16, 2636: 7}
        self.assertEqual(set(counts), PILOT_TASK_IDS)
        for task_id, count in counts.items():
            maximum = 10 if task_id == 2599 else 5
            config = import_environment_tests(task_id, 'cpp', maximum)
            self.assertEqual(len(config['tests']), count)
            expected_comparison = 'tokens_ignore_cr' if task_id in (2597, 2605, 2611, 2636) else 'exact'
            self.assertEqual(config['comparison'], expected_comparison)
            self.assertEqual(config['trailing_whitespace'], 'newlines')
            for case in config['tests']:
                self.assertFalse(case['is_public'])
                self.assertEqual(case['time_limit'], 1)
                self.assertEqual(case['output_limit'], 102400)
            self.assertEqual(io_checks.score_results(config, [True] * count, maximum)[0], maximum)
            self.assertEqual(io_checks.score_results(config, [False] * count, maximum)[0], 0)
            for failed in range(count):
                results = [i != failed for i in range(count)]
                self.assertEqual(io_checks.score_results(config, results, maximum)[0], 5 if task_id == 2599 else 0)
        with self.assertRaises(ValueError):
            import_environment_tests(9999, 'cpp', 5)
        with self.assertRaises(ValueError):
            import_environment_tests(2593, 'python', 5)
        with self.assertRaises(ValueError):
            import_environment_tests(2593, 'cpp', 10)

    def test_import_does_not_depend_on_retired_environment_module(self):
        with patch.dict('sys.modules', {'environments.grade8_2026_chapters_1_4': None}):
            config = import_environment_tests(2611, 'cpp', 5)
        config['tests'][0]['input'] = 'edited'
        self.assertNotEqual(import_environment_tests(2611, 'cpp', 5)['tests'][0]['input'], 'edited')


class IOAdditionalPresetTests(unittest.TestCase):
    def test_all_frozen_presets_keep_limits_groups_and_complete_inputs(self):
        self.assertEqual(hashlib.sha256((REMAINING_PATH / 'index.json').read_bytes()).hexdigest(),
                         'c9bd764fee8cb61679cea10b62994c79930d870e2a699ca90f5398cf757a299d')
        self.assertEqual(len(ADDITIONAL_TASK_IDS), 63)
        self.assertEqual(sum(meta['test_count'] for meta in REMAINING_PRESETS.values()), 318)
        for task_id in sorted(ADDITIONAL_TASK_IDS):
            meta = REMAINING_PRESETS[str(task_id)]
            with self.subTest(task_id=task_id):
                config = import_environment_tests(task_id, meta['language'], meta['points'])
                self.assertEqual(len(config['tests']), meta['test_count'])
                self.assertTrue(all(not test['is_public'] for test in config['tests']))
                for test in config['tests']:
                    self.assertGreater(test['time_limit'], 0)
                    self.assertGreaterEqual(test['output_limit'], 102400)
                count = len(config['tests'])
                self.assertEqual(io_checks.score_results(config, [True] * count, meta['points'])[0], meta['points'])
                self.assertEqual(io_checks.score_results(config, [False] * count, meta['points'])[0], 0)
                for failed in range(count):
                    expected = meta['points'] - 5 if config['scoring'] == 'groups' else 0
                    self.assertEqual(io_checks.score_results(config, [i != failed for i in range(count)], meta['points'])[0], expected)
        large = import_environment_tests(2652, 'cpp', 5)
        self.assertGreater(max(len(t['input']) for t in large['tests']), 3_000_000)
        self.assertGreater(max(len(t['output']) for t in large['tests']), 3_000_000)

    def test_compatibility_comparators_preserve_boundary_behavior(self):
        from environments.grade8_2026_common import exact_text_equal, float_tokens_equal
        pairs = [('a\rb', 'a\nb'), ('a\r\nb  \n', 'a\nb'), ('a  b', 'a b'),
                 ('1_000', '1000'), ('1.000001', '1'), ('1.0000010000000001', '1'),
                 ('nan', 'nan'), ('inf', 'inf'), ('words', 'words'), ('', ''),
                 ('1\r2', '12'), ('1e999999', '1e999999'), ('١.٥', '1.5')]
        for mode, original in [('exact_crlf', exact_text_equal), ('float_binary64', float_tokens_equal)]:
            for actual, expected in pairs:
                with self.subTest(mode=mode, actual=actual):
                    self.assertEqual(io_checks.outputs_equal(actual, expected, mode), original(actual, expected))

    @patch('io_tests.ExecutionContainer')
    def test_per_case_comparison_is_used_and_private_output_stays_hidden(self, factory):
        config = {**CONFIG, 'scoring': 'groups', 'groups': [
            {'id': 'a', 'name': 'a', 'points': 5}, {'id': 'b', 'name': 'b', 'points': 5}],
            'tests': [{'input': 'public', 'output': 'a  b', 'is_public': True, 'group': 'a', 'comparison': 'exact_crlf'},
                      {'input': 'SECRET_INPUT', 'output': 'a  b', 'is_public': False, 'group': 'b'}]}
        factory.return_value.__enter__.return_value.run.return_value = 'a b'
        code = make_code(config=config)
        points, report = io_checks.IOTestExecutor(code).perform()
        self.assertEqual(points, 5)
        self.assertIn('неверный ответ', report)
        self.assertIn('Ожидаемый вывод', report)
        self.assertNotIn('SECRET_INPUT', report)


class IOAdvancedWebTests(IOWebBase):
    def test_per_case_comparison_survives_editor_save_and_validation_error(self):
        task = self.create()
        data = self.form(test_case_comparison=['exact_crlf', 'float_binary64'])
        self.assertEqual(self.client.post(f'/tasks/{task.id}', data=data).status_code, 302)
        self.assertEqual([row['comparison'] for row in task.test_config['tests']], ['exact_crlf', 'float_binary64'])
        response = self.client.get(f'/tasks/{task.id}/edit')
        self.assertIn(b'value="exact_crlf" selected', response.data)
        self.assertIn(b'value="float_binary64" selected', response.data)
        data['test_case_comparison'] = ['unknown', '']
        self.assertEqual(self.client.post(f'/tasks/{task.id}', data=data).status_code, 400)
        self.assertEqual(task.test_config['tests'][0]['comparison'], 'exact_crlf')

    def test_group_settings_round_trip_and_failed_validation_keeps_upload(self):
        task = self.create()
        data = self.form(test_scoring='groups', group_id=['a', 'b'], group_name=['SECRET_GROUP', 'Основные'],
                         group_points=['3', '7'], test_group=['a', 'b'],
                         test_case_time_limit=['3', ''], test_case_output_limit=['2048', ''],
                         test_comparison='float', test_absolute_tolerance='0.001', test_relative_tolerance='0')
        response = self.client.post(f'/tasks/{task.id}', data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.test_config['groups'][0]['points'], 3)
        self.assertEqual(task.test_config['tests'][0]['output_limit'], 2 * 1024 * 1024)
        html = self.client.get(f'/tasks/{task.id}/edit').text
        self.assertIn('value="2048"', html)
        self.assertIn('SECRET_GROUP', html)
        data.setlist('group_points', ['4', '7'])
        data['test_input_file_0'] = (BytesIO(b'uploaded input'), 'test.in')
        response = self.client.post(f'/tasks/{task.id}', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)
        self.assertIn('uploaded input', response.text)
        self.assertIn('SECRET_GROUP', response.text)
        db.session.expire_all()
        self.assertEqual(task.test_config['tests'][0]['input'], '2 3\n')
        self.login('student')
        self.assertNotIn('SECRET', self.client.get(f'/?task_id={task.id}&course_id=1').text)

    def test_files_replace_text_support_empty_bom_and_large_edit(self):
        payload = 'я' * (600 * 1024)
        data = self.form(test_input_file_0=(BytesIO(payload.encode()), 'large.in'),
                         test_output_file_0=(BytesIO(b'\xef\xbb\xbf5\r\n'), 'answer.txt'),
                         test_input_file_1=(BytesIO(b''), 'empty.in'))
        response = self.client.post('/tasks', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)
        task = Task.query.one()
        self.assertEqual(task.test_config['tests'][0]['input'], payload)
        self.assertEqual(task.test_config['tests'][0]['output'], '5\n')
        self.assertEqual(task.test_config['tests'][1]['input'], '')
        html = self.client.get(f'/tasks/{task.id}/edit').text
        self.assertNotIn(payload, html)
        self.assertIn('Скачать', html)
        response = self.client.post(f'/tasks/{task.id}', data=self.form(
            test_input=[payload, ''], test_output=['5\n', 'SECRET_OUTPUT']), content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.test_config['tests'][0]['input'], payload)

    def test_bad_upload_does_not_discard_other_uploaded_text(self):
        task = self.create()
        for bad in (b'\xff', b'x' * (io_checks.MAX_TEXT_BYTES + 1)):
            response = self.client.post(f'/tasks/{task.id}', data=self.form(
                test_input_file_0=(BytesIO(b'preserved'), 'input.txt'),
                test_output_file_1=(BytesIO(bad), 'bad.txt')), content_type='multipart/form-data')
            self.assertEqual(response.status_code, 400)
            self.assertIn('preserved', response.text)
            self.assertEqual(task.test_config, io_checks.validate_test_config(CONFIG))

    def test_import_is_teacher_only_preview_and_does_not_write_task(self):
        task = Task(id=2599, name='Таблица', lang='cpp', points=10, check_type='tests', test_mode='environment')
        db.session.add(task)
        db.session.commit()
        response = self.client.get('/tasks/2599/import-tests')
        self.assertEqual(response.status_code, 200)
        self.assertIn('после нажатия', response.text)
        self.assertIn('value="groups" selected', response.text)
        self.assertEqual(task.test_mode, 'environment')
        self.assertIsNone(task.test_config)
        task.points = 5
        db.session.commit()
        self.assertEqual(self.client.get('/tasks/2599/import-tests').status_code, 400)
        self.login('student')
        self.assertEqual(self.client.get('/tasks/2599/import-tests').status_code, 403)

    def test_migrated_task_cannot_switch_to_deleted_environment(self):
        task = Task(id=2593, name='Poem', lang='cpp', points=5, check_type='tests', test_mode='io',
                    test_config=import_environment_tests(2593, 'cpp', 5))
        db.session.add(task)
        db.session.commit()
        response = self.client.post('/tasks/2593', data=self.form(
            id='2593', lang='cpp', points='5', test_mode='environment'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Окружение этой задачи перенесено', response.text)
        db.session.expire_all()
        self.assertEqual(task.test_mode, 'io')


@unittest.skipUnless(os.getenv('RUN_IO_DOCKER_INTEGRATION') == '1', 'requires Docker')
class IODockerTests(unittest.TestCase):
    def test_python_and_cpp_stdin_stdout(self):
        for lang, source in [('python', 'a, b = map(int, input().split()); print(a + b)'),
                             ('cpp', '#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b;}')]:
            code = make_code(config={**CONFIG, 'tests': [CONFIG['tests'][0]]})
            code.lang, code.code = lang, source
            self.assertEqual(io_checks.IOTestExecutor(code).perform()[0], 10)

    def test_private_file_cannot_be_read_by_later_public_test(self):
        code = make_code(config={**CONFIG, 'tests': [
            {'input': 'PRIVATE\n', 'output': '', 'is_public': False},
            {'input': 'PUBLIC\n', 'output': 'clean', 'is_public': True},
        ]})
        code.code = "from pathlib import Path\ns=input()\np=Path('/code/secret')\nif s=='PRIVATE': p.write_text(s)\nelse: print(p.read_text() if p.exists() else 'clean')"
        points, report = io_checks.IOTestExecutor(code).perform()
        self.assertEqual(points, 10)
        self.assertNotIn('PRIVATE', report)

    def test_timeout_does_not_prevent_next_test(self):
        code = make_code(config={**CONFIG, 'time_limit': 1, 'tests': [
            {'input': 'hang\n', 'output': '', 'is_public': False},
            {'input': 'ok\n', 'output': 'ok', 'is_public': True},
        ]})
        code.code = "s=input()\nif s=='hang':\n while True: pass\nprint(s)"
        points, report = io_checks.IOTestExecutor(code).perform()
        self.assertEqual(points, 5)
        self.assertIn('Тест 2 (публичный): пройден', report)


if __name__ == '__main__':
    unittest.main()
