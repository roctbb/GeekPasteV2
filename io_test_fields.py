"""Keep large private test fields out of HTML; resolve signed references on save."""
import hashlib

from flask import current_app, g, url_for
from itsdangerous import BadSignature, URLSafeSerializer

from io_test_import import import_environment_tests


INLINE_FIELD_BYTES = 256 * 1024


def _signer():
    return URLSafeSerializer(current_app.secret_key, salt='io-test-field-v1')


def _field_reference(task, source, index, field, value):
    return _signer().dumps([task.id, source, index, field,
                            hashlib.sha256(value.encode('utf-8')).hexdigest()])


def private_test_previews(task, preview_chars=2048):
    """Called only by the teacher endpoint; never include these in live payloads."""
    config = task.test_config or {}
    tests = config.get('tests', []) if isinstance(config, dict) else []
    if not isinstance(tests, list):
        raise ValueError('Некорректные данные тестов.')
    previews = []
    for index, test in enumerate(tests):
        if not isinstance(test, dict):
            raise ValueError('Некорректные данные теста.')
        if test.get('is_public') is True:
            continue
        row = {'number': index + 1}
        for field in ('input', 'output'):
            value = test.get(field)
            if not isinstance(value, str):
                raise ValueError('Некорректные данные теста.')
            row[field] = value[:preview_chars]
            if len(value) > preview_chars:
                token = _field_reference(task, 'saved', index, field, value)
                row[f'{field}_url'] = url_for('tasks_test_data', task_id=task.id, token=token)
                row[f'{field}_bytes'] = len(value.encode('utf-8'))
        previews.append(row)
    return previews


def _config(task, source):
    if source == 'saved':
        return task.test_config or {}
    if source != 'preset':
        raise ValueError('Неизвестный источник теста.')
    cache = g.setdefault('io_field_presets', {})
    if task.id not in cache:
        cache[task.id] = import_environment_tests(task.id, task.lang, task.points)
    return cache[task.id]


def resolve_field(task, token, key=None):
    try:
        task_id, source, index, field, digest = _signer().loads(token)
        if task.id != task_id or field not in ('input', 'output') or (key and key != field):
            raise ValueError
        if type(index) is not int or index < 0:
            raise ValueError
        value = _config(task, source)['tests'][index][field]
        if hashlib.sha256(value.encode('utf-8')).hexdigest() != digest:
            raise ValueError
        return value
    except (BadSignature, TypeError, ValueError, KeyError, IndexError):
        raise ValueError('Сохранённый тест изменился или недоступен. Откройте редактор заново.') from None


def prepare_fields(task, cases, source='saved', draft=False):
    result = []
    for index, case in enumerate(cases):
        row = dict(case)
        for key in ('input', 'output'):
            value = row[key]
            if len(value) < INLINE_FIELD_BYTES // 4:
                continue
            size = len(value.encode('utf-8'))
            if size <= INLINE_FIELD_BYTES:
                continue
            token = row.get(f'{key}_ref')
            # Unsaved uploads must survive validation errors too. They stay in
            # the draft textarea until saved; never reference unrelated DB data.
            if not token and not draft and task:
                token = _field_reference(task, source, index, key, value)
            if token:
                row[key] = ''
                row[f'{key}_ref'] = token
                row[f'{key}_bytes'] = size
                row[f'{key}_url'] = url_for('tasks_test_data', task_id=task.id, token=token)
        result.append(row)
    return result
