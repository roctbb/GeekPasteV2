"""Display saved IO reports without interpreting contestant output as HTML."""
from html import unescape
from pathlib import Path
import re

from jinja2 import Environment, FileSystemLoader


_templates = Environment(loader=FileSystemLoader(Path(__file__).parent / 'templates'), autoescape=True)
_summary = re.compile(r'\AПройдено тестов: (\d+) из (\d+)\.')
_row = re.compile(r'Тест (\d+) \((публичный|приватный)\): (пройден|неверный ответ|ошибка выполнения или превышение лимита)\.')
_fields = {'Ввод:': 'input', 'Ожидаемый вывод:': 'expected', 'Вывод программы:': 'actual', 'Ошибка:': 'error'}
_statuses = {
    'пройден': ('passed', 'Пройден'),
    'неверный ответ': ('failed', 'Неверный ответ'),
    'ошибка выполнения или превышение лимита': ('error', 'Ошибка / лимит'),
}


def parse_io_test_report(value):
    text = str(value or '')
    match = _summary.match(text)
    if not match:
        return None
    passed, total = map(int, match.groups())
    if not 0 <= passed <= total <= 50 or total == 0:
        return None
    rows, notes = [], []
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
    missing = any(row['public'] and row['input'] is None for row in rows)
    return dict(passed=passed, total=total, rows=rows, notes=notes, missing_data=missing)


def render_io_test_report(value):
    report = parse_io_test_report(value)
    if report is None:
        return None
    return _templates.get_template('partials/io_test_results.html').render(report=report)
