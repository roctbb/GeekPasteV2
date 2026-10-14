import copy
import gzip
import hashlib
from io import BytesIO
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from sqlalchemy import event

from io_test_import import PYTHON_PATH, PYTHON_PRESETS, PYTHON_TASK_IDS, import_environment_tests
from io_tests import IOTestExecutor, outputs_equal, validate_test_config
from models import Task, db
from runner import ExecutionContainer
from tests.test_io_tests import IOWebBase, make_code, CONFIG


def input_references(html):
    class References(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'input' and attrs.get('name') == 'test_input_ref' and attrs.get('value'):
                result.append(attrs['value'])
    result = []
    References().feed(html)
    return result


class PythonIOContracts(unittest.TestCase):
    def test_migrated_environments_are_retired_but_custom_checkers_remain(self):
        root = Path(__file__).resolve().parents[1] / 'environments'
        for task_id, metadata in PYTHON_PRESETS.items():
            self.assertFalse((root / f'task_{task_id}' / 'tester.py').exists(), task_id)
            if metadata['source'].startswith('mkoshp'):
                self.assertFalse((root / metadata['source'] / 'data' /
                                  f'{metadata["source_key"]}.json.gz').exists(), task_id)
        for task_id in (1979, 1998, 2872, 2902):
            self.assertTrue((root / f'task_{task_id}' / 'tester.py').exists(), task_id)

    def test_numeric_and_suffix_boundaries(self):
        cases = [
            ('strip_suffix', 'Ввод: ответ\n', 'ответ', True),
            ('strip_suffix', 'ответ \nдругое', 'ответ', False),
            ('lower_suffix', 'Ввод: ПРИВЕТ\n', 'привет', True),
            ('lower_suffix', 'SS', 'ß', False),
            ('lower_exact', 'ABC\n', 'abc', True),
            ('lower_exact', 'Ввод: ABC', 'abc', False),
            ('normalized_suffix', 'Ввод: １\u00a0ч.\n15 мин.', '1 ч. 15 мин.', True),
            ('exact_suffix', 'prompt\na  b\n\n', 'a  b', True),
            ('exact_suffix', 'prompt\na b', 'a  b', False),
            ('last_time', 'Время 12:00\n', '12:00', True),
            ('last_time', '112:00', '12:00', False),
            ('last_integer', 'Ответ: +001\n', '1', True),
            ('last_integer', 'Ответ: +-1', '1', False),
            ('integer_tokens', '١_٠ +01 -0', '10 1 0', True),
            ('integer_tokens', '1.0', '1', False),
            ('integer_tokens_ascii30', '+001 -0', '1 0', True),
            ('integer_tokens_ascii30', '١', '1', False),
            ('integer_tokens_ascii30', '0' * 30 + '1', '1', False),
            ('keyword_integers_ascii30', 'yes +01 -0', 'YES 1 0', True),
            ('word_integer_ascii30', 'win +01', 'win 1', True),
            ('word_integer_ascii30', 'WIN 1', 'win 1', False),
            ('word_lower', 'YeS\n', 'yes', True),
            ('word_lower', 'yes extra', 'yes', False),
            ('splitlines', 'a\vb\n', 'a\nb\n', True),
            ('splitlines', 'a\nb\n\n', 'a\nb\n', False),
            ('rational_absolute', '0.500001', '1/2', True),
            ('rational_absolute', '0.5000010000000000000000001', '1/2', False),
            ('rational_absolute', '0.499999', '1/2', True),
            ('rational_absolute', 'NaN', '1/2', False),
        ]
        for mode, actual, expected, accepted in cases:
            with self.subTest(mode=mode, actual=actual):
                self.assertEqual(outputs_equal(actual, expected, mode), accepted)

    def test_frozen_inventory_integrity_and_resources(self):
        self.assertEqual(len(PYTHON_TASK_IDS), 56)
        self.assertEqual(sum(row['count'] for row in PYTHON_PRESETS.values()), 1335)
        self.assertNotIn(1979, PYTHON_TASK_IDS)
        self.assertNotIn(1998, PYTHON_TASK_IDS)
        for task_id in sorted(PYTHON_TASK_IDS):
            meta = PYTHON_PRESETS[str(task_id)]
            config = import_environment_tests(task_id, 'python', meta['points'])
            raw = gzip.decompress((PYTHON_PATH / f'{task_id}.json.gz').read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['sha256'])
            frozen = json.loads(raw)
            if task_id == 2914:
                self.assertEqual(frozen['time_limit'], 6)
                self.assertEqual(meta['time_limit_override'], 12)
                frozen['time_limit'] = 12
            self.assertEqual(config, frozen)
            self.assertEqual(len(config['tests']), meta['count'])
            self.assertTrue(all(not test['is_public'] for test in config['tests']))
            if task_id >= 2871:
                self.assertEqual(config['memory_limit'], 256 if task_id <= 2888 else 512)
                self.assertEqual(config['process_limit'], 64)
                self.assertTrue(config['disable_swap'])
                self.assertEqual(config['output_limit'], 8 * 1024 * 1024)
        largest = import_environment_tests(2914, 'python', 5)
        self.assertEqual(max(len(t['input'].encode()) for t in largest['tests']), 21777915)
        self.assertEqual(sum(len(t[k].encode()) for t in largest['tests'] for k in ('input', 'output')), 163711993)

    def test_resource_and_fraction_validation(self):
        for update in (dict(memory_limit=0), dict(memory_limit=True), dict(process_limit=1),
                       dict(disable_swap='yes'), dict(memory_limit=2049)):
            with self.assertRaises(ValueError):
                validate_test_config({**CONFIG, **update})
        for expected in ('1/0', '1/-2', '1/2/3', 'inf', '1e3/2'):
            with self.assertRaises(ValueError):
                validate_test_config({**CONFIG, 'comparison': 'rational_absolute',
                                      'tests': [dict(input='', output=expected, is_public=False)]})

    @patch('io_tests.ExecutionContainer')
    def test_executor_applies_olympiad_resources(self, factory):
        config = import_environment_tests(2871, 'python', 5)
        factory.return_value.__enter__.return_value.run.side_effect = [t['output'] for t in config['tests']]
        code = make_code(points=5, config=config)
        self.assertEqual(IOTestExecutor(code).perform()[0], 5)
        self.assertTrue(all(call.kwargs['resource_limits'] == dict(memory_limit=256, process_limit=64, disable_swap=True)
                            for call in factory.call_args_list))


class PythonIOLargeEditorTests(IOWebBase):
    def test_task_lists_and_student_page_do_not_load_private_suites(self):
        task = self.create()
        task_id = task.id
        task.test_config = validate_test_config({**CONFIG, 'tests': [
            dict(input='PRIVATE' * 50000, output='SECRET', is_public=False)]})
        db.session.commit()
        db.session.remove()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            self.assertEqual(self.client.get('/tasks').status_code, 200)
            self.login('student')
            response = self.client.get(f'/?task_id={task_id}&course_id=1')
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('PRIVATE', response.text)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
        self.assertFalse(any('tasks.test_config' in statement for statement in statements))

    def large_task(self):
        task = self.create()
        config = copy.deepcopy(task.test_config)
        config['tests'][0]['input'] = 'PRIVATE_LONG_INPUT\n' * 20000
        config['tests'][1]['input'] = 'OTHER_PRIVATE_INPUT\n' * 20000
        task.test_config = config
        db.session.commit()
        html = self.client.get(f'/tasks/{task.id}/edit').text
        refs = input_references(html)
        return task, html, refs

    def test_large_fields_round_trip_reorder_download_and_role_checks(self):
        task, html, refs = self.large_task()
        original = copy.deepcopy(task.test_config)
        self.assertEqual(len(refs), 2)
        self.assertNotIn('PRIVATE_LONG_INPUT', html)
        self.assertLess(len(html), 80000)
        url = f'/tasks/{task.id}/test-data/{refs[0]}'
        download = self.client.get(url)
        self.assertEqual(download.data.decode(), original['tests'][0]['input'])
        self.assertEqual(download.headers['Cache-Control'], 'private, no-store')
        response = self.client.post(f'/tasks/{task.id}', data=self.form(
            test_input=['', ''], test_output=['SECRET_OUTPUT', '5\n'],
            test_input_ref=list(reversed(refs)), test_output_ref=['', ''],
            test_visibility=['private', 'public']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.test_config['tests'], list(reversed(original['tests'])))
        self.login('student')
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_stale_foreign_and_tampered_references_are_rejected_atomically(self):
        task, _, refs = self.large_task()
        for token in (refs[0] + 'x', refs[1]):
            response = self.client.post(f'/tasks/{task.id}', data=self.form(
                name='CHANGED', test_output_ref=[token, '']))
            self.assertEqual(response.status_code, 400)
            self.assertEqual(task.name, 'Сумма')
        other = Task(name='Other', lang='python', points=10, test_mode='io', test_config=task.test_config)
        db.session.add(other)
        db.session.commit()
        response = self.client.post(f'/tasks/{other.id}', data=self.form(test_input_ref=refs))
        self.assertEqual(response.status_code, 400)
        config = copy.deepcopy(task.test_config)
        config['tests'][0]['input'] = 'changed'
        task.test_config = config
        db.session.commit()
        self.assertEqual(self.client.get(f'/tasks/{task.id}/test-data/{refs[0]}').status_code, 409)
        self.assertEqual(self.client.post(f'/tasks/{task.id}', data=self.form(test_input_ref=refs)).status_code, 400)

    def test_validation_error_and_upload_replacement_preserve_large_fields(self):
        task, _, refs = self.large_task()
        response = self.client.post(f'/tasks/{task.id}', data=self.form(
            test_time_limit='invalid', test_input=['', ''], test_input_ref=refs))
        self.assertEqual(response.status_code, 400)
        self.assertIn(refs[0], response.text)
        self.assertNotIn('PRIVATE_LONG_INPUT', response.text)
        response = self.client.post(f'/tasks/{task.id}', data=self.form(
            test_input=['', ''], test_input_ref=refs,
            test_input_file_0=(BytesIO(b''), 'empty.txt')), content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.test_config['tests'][0]['input'], '')
        self.assertTrue(task.test_config['tests'][1]['input'].startswith('OTHER_PRIVATE_INPUT'))

    def test_exact_byte_limits_and_resources_survive_editor(self):
        task = self.create()
        data = self.form(test_output_limit='97.65625', test_case_output_limit=['97.65625', ''],
                         test_memory_limit='256', test_process_limit='64', test_disable_swap='on')
        self.assertEqual(self.client.post(f'/tasks/{task.id}', data=data).status_code, 302)
        self.assertEqual(task.test_config['output_limit'], 100000)
        self.assertEqual(task.test_config['tests'][0]['output_limit'], 100000)
        html = self.client.get(f'/tasks/{task.id}/edit').text
        self.assertIn('value="97.65625"', html)
        self.assertEqual(task.test_config['memory_limit'], 256)
        self.assertEqual(task.test_config['process_limit'], 64)
        self.assertTrue(task.test_config['disable_swap'])
        data['test_output_limit'] = '1.00001'
        self.assertEqual(self.client.post(f'/tasks/{task.id}', data=data).status_code, 400)

    def test_largest_preset_opens_without_embedding_stress_inputs(self):
        task = Task(id=2914, name='Large', lang='python', points=5, check_type='tests', test_mode='environment')
        db.session.add(task)
        db.session.commit()
        response = self.client.get('/tasks/2914/import-tests')
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(response.data), 2 * 1024 * 1024)
        refs = input_references(response.text)
        self.assertGreater(len(refs), 0)
        first = self.client.get(f'/tasks/2914/test-data/{refs[0]}')
        self.assertEqual(first.status_code, 200)
        self.assertGreater(len(first.data), 256 * 1024)
        self.assertIsNone(task.test_config)


@unittest.skipUnless(os.getenv('RUN_IO_DOCKER_INTEGRATION') == '1', 'requires Docker')
class PythonIOResourceDockerTests(unittest.TestCase):
    def test_sandbox_enforces_memory_swap_and_pid_limits(self):
        limits = dict(memory_limit=256, process_limit=64, disable_swap=True)
        with ExecutionContainer('python', None, 'print(input())', isolated=True, resource_limits=limits) as container:
            import subprocess
            info = json.loads(subprocess.check_output(['docker', 'inspect', container.container_id]))[0]
            swap_supported = subprocess.check_output(
                ['docker', 'info', '--format', '{{.SwapLimit}}'], text=True).strip() == 'true'
            self.assertEqual(info['HostConfig']['Memory'], 256 * 1024 * 1024)
            # Older production kernels cannot enforce swap limits; Docker reports -1.
            self.assertEqual(info['HostConfig']['MemorySwap'],
                             256 * 1024 * 1024 if swap_supported else -1)
            self.assertEqual(info['HostConfig']['PidsLimit'], 64)
            self.assertEqual(info['HostConfig']['NanoCpus'], 1000000000)
            self.assertEqual(info['HostConfig']['NetworkMode'], 'none')
            self.assertEqual(container.run('ok\n').strip(), 'ok')
