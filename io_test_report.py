"""Display saved IO reports without interpreting contestant output as HTML."""
from html import unescape
from pathlib import Path
import re

from jinja2 import Environment, FileSystemLoader
from score_policy import ATTEMPT_COMMENT


_templates = Environment(loader=FileSystemLoader(Path(__file__).parent / 'templates'), autoescape=True)
_summary = re.compile(r'\AПройдено тестов: (\d+) из (\d+)\.')
_fields = {'Ввод:': 'input', 'Ожидаемый вывод:': 'expected', 'Вывод программы:': 'actual', 'Ошибка:': 'error'}
_statuses = {
    'пройден': ('passed', 'Пройден'),
    'неверный ответ': ('failed', 'Неверный ответ'),
    'превышено время': ('time_limit_exceeded', 'Превышено время'),
    'ошибка выполнения': ('runtime_error', 'Ошибка выполнения'),
    'превышен объём вывода': ('output_limit_exceeded', 'Превышен объём вывода'),
    'ошибка компиляции': ('compilation_error', 'Ошибка компиляции'),
    'ошибка проверки': ('error', 'Ошибка проверки'),
    'ошибка выполнения или превышение лимита': ('error', 'Ошибка проверки'),
}
_row = re.compile(r'Тест (\d+) \((публичный|приватный)\): (' + '|'.join(map(re.escape, _statuses)) + r')\.')
_timeout_diagnostic = re.compile(
    r'(?:(?:Test failed: )?Execution timed out after ([0-9]+(?:\.[0-9]+)?) seconds\.'
    r'|Превышен лимит времени: ([0-9]+(?:[.,][0-9]+)?) с\.?)'
)


def parse_io_test_report(value):
    text = str(value or '')
    notes = []
    attempt_prefix = ATTEMPT_COMMENT + '\n\n'
    if text.startswith(attempt_prefix):
        notes.append(ATTEMPT_COMMENT)
        text = text[len(attempt_prefix):]
    match = _summary.match(text)
    if not match:
        return None
    passed, total = map(int, match.groups())
    if not 0 <= passed <= total <= 50 or total == 0:
        return None
    rows = []
    legacy_rows = []
    current = pending = None
    # Escaped content inside a legacy <pre> is one token, even when it contains
    # fake test headings or HTML. Only the surrounding report is parsed.
    for part in re.split(r'(<pre>.*?</pre>)', text[match.end():], flags=re.S):
        if part.startswith('<pre>'):
            if current is None or pending is None:
                return None
            if current['public']:
                current[pending] = unescape(part[5:-6])
            pending = None
            continue
        for line in part.splitlines():
            line = line.strip()
            if not line:
                continue
            if pending is not None:
                return None
            heading = _row.fullmatch(line)
            if heading:
                number, visibility, status = heading.groups()
                status_key, status_label = _statuses[status]
                current = dict(number=int(number), public=visibility == 'публичный',
                               status=status_key, status_label=status_label,
                               input=None, expected=None, actual=None, error=None)
                rows.append(current)
                if status == 'ошибка выполнения или превышение лимита':
                    legacy_rows.append(current)
            elif line in _fields and current is not None:
                pending = _fields[line]
                if current[pending] is not None:
                    return None
            else:
                notes.append(line)
    if pending is not None or [row['number'] for row in rows] != list(range(1, total + 1)):
        return None
    if sum(row['status'] == 'passed' for row in rows) != passed:
        return None
    # Only legacy reports lack a typed verdict. Recognize exact runner messages,
    # never a timeout word inside arbitrary contestant stderr.
    for row in legacy_rows:
        error = (row['error'] or '').strip()
        if _timeout_diagnostic.fullmatch(error):
            row['status'], row['status_label'] = _statuses['превышено время']
        elif error.startswith('Runtime error:'):
            row['status'], row['status_label'] = _statuses['ошибка выполнения']
    for row in rows:
        row['error_detail'] = row['error']
        if row['status'] == 'time_limit_exceeded':
            match = _timeout_diagnostic.fullmatch((row['error'] or '').strip())
            if match:
                limit = (match.group(1) or match.group(2)).replace('.', ',')
                row['error_detail'] = f'Лимит: {limit} с'
    missing = any(row['public'] and row['input'] is None for row in rows)
    return dict(passed=passed, total=total, rows=rows, notes=notes, missing_data=missing,
                has_public=any(row['public'] for row in rows),
                has_private=any(not row['public'] for row in rows))


def render_io_test_report_parts(value):
    report = parse_io_test_report(value)
    if report is None:
        return None
    return {
        'check_comments_html': _templates.get_template('partials/io_test_summary.html').render(report=report),
        'test_results_html': _templates.get_template('partials/io_test_results.html').render(report=report),
    }


def render_io_test_report(value):
    parts = render_io_test_report_parts(value)
    return parts['test_results_html'] if parts else None
