"""Configuration and execution of teacher-authored stdin/stdout tests."""
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
from html import escape
import math
import re

from runner import ExecutionContainer, ExecutionException, SolutionException
from io_test_comparisons import COMPATIBILITY_LABELS, compatibility_equal, rational_parts


MAX_TESTS = 50
MAX_TEXT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
# An edit can contain both the saved text and replacement files.
MAX_REQUEST_BYTES = 2 * MAX_TOTAL_BYTES + 2 * 1024 * 1024
DEFAULT_OUTPUT_LIMIT = 100 * 1024
MAX_OUTPUT_LIMIT = 8 * 1024 * 1024
SUPPORTED_LANGUAGES = {'python', 'cpp'}
COMPARISON_LABELS = {
    'tokens': 'По словам и числам — без учёта разделяющих пробелов',
    'exact': 'Точное — с учётом пробелов и строк',
    'float': 'Числа с погрешностью',
    'tokens_ignore_cr': 'По словам — CR игнорируется',
    'exact_crlf': 'Точное, без конечных пробелов — прежнее правило курса',
    'float_binary64': 'Числа с погрешностью 10⁻⁶ — прежнее правило курса',
    **COMPATIBILITY_LABELS,
}
COMPARISONS = tuple(COMPARISON_LABELS)
NUMBER_PATTERN = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


def _integer(value, minimum, maximum, message):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(message)
    return value


def _tolerance(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('Погрешность должна быть числом от 0 до 1.')
    text = str(value)
    if len(text) > 100 or not NUMBER_PATTERN.fullmatch(text):
        raise ValueError('Погрешность должна быть числом от 0 до 1.')
    try:
        number = Decimal(text)
        if not number.is_finite() or not 0 <= number <= 1 or (number and number.adjusted() < -10000):
            raise InvalidOperation
    except DecimalException:
        raise ValueError('Погрешность должна быть числом от 0 до 1.') from None
    return str(number) if number else '0'


def validate_test_config(config, maximum_points=None):
    if not isinstance(config, dict):
        raise ValueError('Не заданы настройки тестов ввода/вывода.')
    comparison = config.get('comparison', 'tokens')
    if comparison not in COMPARISONS:
        raise ValueError('Выберите допустимый способ сравнения вывода.')
    trailing = config.get('trailing_whitespace', 'one_newline')
    if trailing not in ('one_newline', 'newlines', 'all'):
        raise ValueError('Выберите обработку пробелов в конце вывода.')
    scoring = config.get('scoring', 'proportional')
    if scoring not in ('proportional', 'all_or_nothing', 'groups'):
        raise ValueError('Выберите допустимый способ начисления баллов.')
    time_limit = _integer(config.get('time_limit', 2), 1, 30,
                          'Лимит времени должен быть целым числом от 1 до 30 секунд.')
    output_limit = _integer(config.get('output_limit', DEFAULT_OUTPUT_LIMIT),
                            1024, MAX_OUTPUT_LIMIT, 'Лимит вывода должен быть от 1 КиБ до 8 МиБ.')
    memory_limit = _integer(config.get('memory_limit', 512), 128, 2048,
                            'Память должна быть целым числом от 128 до 2048 МиБ.')
    process_limit = _integer(config.get('process_limit', 128), 16, 256,
                             'Число процессов должно быть от 16 до 256.')
    disable_swap = config.get('disable_swap', False)
    if type(disable_swap) is not bool:
        raise ValueError('Выберите ограничение подкачки памяти.')
    tests = config.get('tests')
    if not isinstance(tests, list) or not 1 <= len(tests) <= MAX_TESTS:
        raise ValueError(f'Добавьте от 1 до {MAX_TESTS} тестов.')

    groups = []
    group_ids = set()
    if scoring == 'groups':
        raw_groups = config.get('groups')
        if not isinstance(raw_groups, list) or not 1 <= len(raw_groups) <= MAX_TESTS:
            raise ValueError('Добавьте хотя бы одну группу тестов.')
        for group in raw_groups:
            if not isinstance(group, dict):
                raise ValueError('Неверные настройки группы тестов.')
            group_id = group.get('id')
            name = group.get('name')
            if not isinstance(group_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', group_id) or group_id in group_ids:
                raise ValueError('Идентификаторы групп должны быть уникальными.')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                raise ValueError('Название группы должно содержать от 1 до 100 символов.')
            points = _integer(group.get('points'), 1, 1000000,
                              'Баллы группы должны быть положительным целым числом до 1000000.')
            group_ids.add(group_id)
            groups.append({'id': group_id, 'name': name.strip(), 'points': points})
        if maximum_points is not None and sum(group['points'] for group in groups) != maximum_points:
            raise ValueError('Сумма баллов групп должна совпадать с баллами задачи.')

    normalized = []
    used_groups = set()
    total_bytes = 0
    for number, test in enumerate(tests, 1):
        if not isinstance(test, dict) or type(test.get('is_public')) is not bool:
            raise ValueError(f'Тест {number}: выберите публичность.')
        row = {'is_public': test['is_public']}
        if test.get('comparison'):
            if test['comparison'] not in COMPARISONS:
                raise ValueError(f'Тест {number}: выберите допустимый способ сравнения.')
            row['comparison'] = test['comparison']
        for key in ('input', 'output'):
            value = test.get(key)
            if not isinstance(value, str):
                raise ValueError(f'Тест {number}: ввод и вывод должны быть текстом.')
            value = value.replace('\r\n', '\n').replace('\r', '\n')
            size = len(value.encode('utf-8'))
            if size > MAX_TEXT_BYTES:
                raise ValueError(f'Тест {number}: каждое поле должно быть не больше 32 МиБ.')
            total_bytes += size
            row[key] = value
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValueError('Общий размер тестов должен быть не больше 256 МиБ.')
        if row.get('comparison', comparison) == 'rational_absolute':
            rational_parts(row['output'])
        for key, low, high, message in (
            ('time_limit', 1, 30, f'Тест {number}: время должно быть от 1 до 30 секунд.'),
            ('output_limit', 1024, MAX_OUTPUT_LIMIT, f'Тест {number}: лимит вывода должен быть от 1 КиБ до 8 МиБ.'),
        ):
            if test.get(key) is not None:
                row[key] = _integer(test[key], low, high, message)
        if scoring == 'groups':
            group_id = test.get('group')
            if not isinstance(group_id, str) or group_id not in group_ids:
                raise ValueError(f'Тест {number}: выберите существующую группу.')
            row['group'] = group_id
            used_groups.add(group_id)
        normalized.append(row)
    if scoring == 'groups' and used_groups != group_ids:
        raise ValueError('В каждой группе должен быть хотя бы один тест.')
    return {
        'comparison': comparison, 'trailing_whitespace': trailing,
        'absolute_tolerance': _tolerance(config.get('absolute_tolerance', '0.000001')),
        'relative_tolerance': _tolerance(config.get('relative_tolerance', '0.000001')),
        'time_limit': time_limit, 'output_limit': output_limit,
        'memory_limit': memory_limit, 'process_limit': process_limit, 'disable_swap': disable_swap,
        'scoring': scoring, 'groups': groups, 'tests': normalized,
    }


def draft_test_config_from_form(form, files=None, resolve_field=None):
    """Read the draft once, retaining uploaded text when later validation fails."""
    inputs = form.getlist('test_input')
    outputs = form.getlist('test_output')
    visibility = form.getlist('test_visibility')
    if len(inputs) != len(outputs) or len(inputs) != len(visibility):
        raise ValueError('У каждого теста должны быть ввод, вывод и публичность.')
    if any(value not in ('public', 'private') for value in visibility):
        raise ValueError('Выберите публичность каждого теста.')

    def optional_list(name):
        values = form.getlist(name)
        if values and len(values) != len(inputs):
            raise ValueError('Неверное число параметров тестов. Обновите страницу.')
        return values or [''] * len(inputs)

    group_ids = optional_list('test_group')
    times = optional_list('test_case_time_limit')
    limits = optional_list('test_case_output_limit')
    comparisons = optional_list('test_case_comparison')
    references = {key: optional_list(f'test_{key}_ref') for key in ('input', 'output')}
    rows = []
    file_error = None
    for i, (stdin, stdout, public) in enumerate(zip(inputs, outputs, visibility)):
        row = {'input': stdin, 'output': stdout, 'is_public': public == 'public',
               'group': group_ids[i], 'time_limit': times[i], 'output_limit': limits[i],
               'comparison': comparisons[i]}
        for key in ('input', 'output'):
            reference = references[key][i]
            if reference:
                if resolve_field is None:
                    raise ValueError('Не удалось восстановить сохранённый тест. Обновите страницу.')
                row[key] = resolve_field(reference, key)
                row[f'{key}_ref'] = reference
            uploaded = files.get(f'test_{key}_file_{i}') if files else None
            if uploaded and uploaded.filename:
                content = uploaded.read(MAX_TEXT_BYTES + 1)
                if len(content) > MAX_TEXT_BYTES:
                    file_error = f'Тест {i + 1}: файл должен быть не больше 32 МиБ.'
                    continue
                try:
                    row[key] = content.decode('utf-8-sig')
                    row.pop(f'{key}_ref', None)
                except UnicodeDecodeError:
                    file_error = f'Тест {i + 1}: сохраните файл в кодировке UTF-8.'
        rows.append(row)
    ids, names, points = (form.getlist(name) for name in ('group_id', 'group_name', 'group_points'))
    if len(ids) != len(names) or len(ids) != len(points):
        raise ValueError('У каждой группы должны быть название и баллы.')
    draft = {
        'comparison': form.get('test_comparison', 'tokens'),
        'trailing_whitespace': form.get('test_trailing_whitespace', 'one_newline'),
        'absolute_tolerance': form.get('test_absolute_tolerance', '0.000001'),
        'relative_tolerance': form.get('test_relative_tolerance', '0.000001'),
        'time_limit': form.get('test_time_limit', '2'),
        'output_limit': form.get('test_output_limit', '100'),
        'memory_limit': form.get('test_memory_limit', '512'),
        'process_limit': form.get('test_process_limit', '128'),
        'disable_swap': form.get('test_disable_swap') == 'on',
        'scoring': form.get('test_scoring', 'proportional'),
        'groups': [{'id': key, 'name': name, 'points': score}
                   for key, name, score in zip(ids, names, points)],
        'tests': rows,
    }
    return draft, file_error


def validate_form_draft(draft, maximum_points=None):
    def number(value, label, factor=1):
        try:
            if factor != 1:
                exact = Decimal(str(value)) * factor
                if not exact.is_finite() or exact != exact.to_integral_value():
                    raise ValueError
                return int(exact)
            return int(value) * factor
        except (TypeError, ValueError, DecimalException):
            raise ValueError(f'{label}: укажите точное число байт.' if factor != 1
                             else f'{label}: введите целое число.') from None
    config = dict(draft)
    config['time_limit'] = number(draft['time_limit'], 'Лимит времени')
    config['output_limit'] = number(draft['output_limit'], 'Лимит вывода', 1024)
    config['memory_limit'] = number(draft.get('memory_limit', '512'), 'Память')
    config['process_limit'] = number(draft.get('process_limit', '128'), 'Число процессов')
    config['disable_swap'] = draft.get('disable_swap', False)
    config['groups'] = [dict(group, points=number(group['points'], 'Баллы группы'))
                        for group in draft['groups']] if draft['scoring'] == 'groups' else []
    config['tests'] = []
    for row in draft['tests']:
        test = dict(row)
        test['time_limit'] = number(row['time_limit'], 'Время на тест') if row['time_limit'] != '' else None
        test['output_limit'] = number(row['output_limit'], 'Лимит вывода теста', 1024) if row['output_limit'] != '' else None
        config['tests'].append(test)
    return validate_test_config(config, maximum_points)


def test_config_from_form(form, files=None, maximum_points=None):
    draft, error = draft_test_config_from_form(form, files)
    if error:
        raise ValueError(error)
    return validate_form_draft(draft, maximum_points)


def public_tests(task):
    if not task or task.check_type != 'tests' or task.test_mode != 'io':
        return []
    summary = getattr(task, 'test_summary', None)
    if summary is not None:
        return summary.get('public_tests', [])
    return [test for test in (task.test_config or {}).get('tests', [])
            if test.get('is_public') is True]


def outputs_equal(actual, expected, comparison, *, trailing_whitespace='one_newline',
                  absolute_tolerance='0.000001', relative_tolerance='0.000001'):
    if comparison in COMPATIBILITY_LABELS:
        return compatibility_equal(actual, expected, comparison)
    if comparison == 'exact_crlf':
        # Preserve the course checker: a lone CR inside a line is significant.
        return actual.replace('\r\n', '\n').rstrip() == expected.replace('\r\n', '\n').rstrip()
    if comparison == 'float_binary64':
        # Compatibility with the original float_tokens_equal, including float
        # parsing/rounding and rejection of nonnumeric and nonfinite tokens.
        left, right = actual.replace('\r', '').split(), expected.replace('\r', '').split()
        if len(left) != len(right):
            return False
        try:
            return all(math.isfinite(a) and math.isfinite(b)
                       and abs(a - b) <= 1e-6 * max(1.0, abs(b))
                       for a, b in zip(map(float, left), map(float, right)))
        except (ValueError, OverflowError):
            return False
    if comparison == 'tokens_ignore_cr':
        return actual.replace('\r', '').split() == expected.replace('\r', '').split()
    if comparison == 'tokens':
        return actual.split() == expected.split()
    if comparison == 'float':
        actual_tokens, expected_tokens = actual.split(), expected.split()
        if len(actual_tokens) != len(expected_tokens):
            return False
        absolute, relative = Decimal(absolute_tolerance), Decimal(relative_tolerance)
        for left, right in zip(actual_tokens, expected_tokens):
            if left.casefold().lstrip('+-') in ('nan', 'inf', 'infinity') or right.casefold().lstrip('+-') in ('nan', 'inf', 'infinity'):
                return False
            numeric_left, numeric_right = NUMBER_PATTERN.fullmatch(left), NUMBER_PATTERN.fullmatch(right)
            if not numeric_left or not numeric_right:
                if left != right:
                    return False
                continue
            if len(left) > 1000 or len(right) > 1000:
                return False
            try:
                a, b = Decimal(left), Decimal(right)
                if not a.is_finite() or not b.is_finite() or max(abs(a.adjusted()), abs(b.adjusted())) > 10000:
                    return False
                with localcontext() as context:
                    context.prec = max(len(left), len(right)) + abs(a.adjusted() - b.adjusted()) + 150
                    if abs(a - b) > max(absolute, relative * abs(b)):
                        return False
            except DecimalException:
                return False
        return True
    if comparison != 'exact':
        raise ValueError('Неизвестный способ сравнения.')

    def normalize(text):
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        if trailing_whitespace == 'newlines':
            return text.rstrip('\n')
        if trailing_whitespace == 'all':
            return text.rstrip()
        return text.removesuffix('\n')
    return normalize(actual) == normalize(expected)


def score_results(config, results, maximum):
    if config['scoring'] == 'all_or_nothing':
        return (maximum if all(results) else 0), []
    if config['scoring'] == 'groups':
        points, comments = 0, []
        for group in config['groups']:
            passed = all(result for test, result in zip(config['tests'], results) if test['group'] == group['id'])
            earned = group['points'] if passed else 0
            points += earned
            # Group names are teacher-only: they may describe hidden scenarios.
            comments.append(f'Группа {len(comments) + 1}: {earned} из {group["points"]} баллов.')
        return points, comments
    return maximum * sum(results) // len(results), []


def _report_text(label, text):
    if len(text) > 2000:
        text = text[:2000] + '\n… (показаны первые 2000 символов)'
    return f'{label}:\n\n<pre>{escape(text or "(пусто)")}</pre>'


class IOTestExecutor:
    def __init__(self, code):
        self.code = code
        self.all_passed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def perform(self):
        task = self.code.task
        if type(task.points) is not int or task.points < 1:
            raise ExecutionException('Для тестов ввода/вывода задайте положительное число баллов.')
        try:
            config = validate_test_config(task.test_config, task.points)
        except ValueError as error:
            raise ExecutionException(str(error)) from None
        if self.code.lang not in SUPPORTED_LANGUAGES:
            raise SolutionException('Тесты ввода/вывода поддерживают Python и C++.')

        results, comments = [], []
        limits = {}
        if (config['memory_limit'], config['process_limit'], config['disable_swap']) != (512, 128, False):
            limits['resource_limits'] = {
                'memory_limit': config['memory_limit'], 'process_limit': config['process_limit'],
                'disable_swap': config['disable_swap'],
            }
        for number, test in enumerate(config['tests'], 1):
            label = f'Тест {number} ({"публичный" if test["is_public"] else "приватный"})'
            try:
                # New sandbox per case: no private files or background processes
                # survive into a later public test. Expected outputs stay outside.
                with ExecutionContainer(self.code.lang, None, self.code.code, isolated=True, **limits) as container:
                    actual = container.run(test['input'],
                                           time_limit=test.get('time_limit', config['time_limit']),
                                           capture_limit=test.get('output_limit', config['output_limit']))
            except SolutionException as error:
                results.append(False)
                comments.append(f'{label}: ошибка выполнения или превышение лимита.')
                if test['is_public']:
                    comments.extend([_report_text('Ввод', test['input']),
                                     _report_text('Ожидаемый вывод', test['output'])])
                    comments.append(_report_text('Ошибка', str(error)))
                continue
            except ExecutionException:
                raise ExecutionException('Не удалось запустить проверку ввода/вывода. Повторите позже.') from None

            passed = outputs_equal(actual, test['output'], test.get('comparison', config['comparison']),
                                   trailing_whitespace=config['trailing_whitespace'],
                                   absolute_tolerance=config['absolute_tolerance'],
                                   relative_tolerance=config['relative_tolerance'])
            results.append(passed)
            if passed:
                comments.append(f'{label}: пройден.')
            else:
                comments.append(f'{label}: неверный ответ.')
            if test['is_public']:
                comments.extend([_report_text('Ввод', test['input']),
                                 _report_text('Ожидаемый вывод', test['output']),
                                 _report_text('Вывод программы', actual)])
        self.all_passed = all(results)
        points, group_comments = score_results(config, results, task.points)
        return points, f'Пройдено тестов: {sum(results)} из {len(results)}.\n\n' + '\n\n'.join(group_comments + comments)
