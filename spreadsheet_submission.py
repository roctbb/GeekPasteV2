"""Bounded, read-only XLSX evidence for direct report uploads.

Read saved cells and native chart definitions; never evaluate formulas, follow
external links, or extract files to disk. The original upload remains the download.
"""

import io
import base64
import binascii
import json
import os
import posixpath
import zipfile

from defusedxml import ElementTree as ET


MAX_XLSX_PARTS = 1000
MAX_XLSX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_XLSX_SHEETS = 20
MAX_XLSX_CELLS = 10000
MAX_XLSX_CHARTS = 20
MAX_XLSX_TEXT_CHARS = 200000
MAX_XLSX_XML_PART_BYTES = 2 * 1024 * 1024
XLSX_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
NS = {
    's': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
}


def _xml(archive, part):
    if archive.getinfo(part).file_size > MAX_XLSX_XML_PART_BYTES:
        raise ValueError('Слишком большая часть Excel-файла.')
    return ET.fromstring(archive.read(part))


def _relationships(archive, part):
    folder, name = posixpath.split(part)
    rel_path = posixpath.join(folder, '_rels', name + '.rels') if part else '_rels/.rels'
    if rel_path not in archive.namelist():
        return {}
    result = {}
    for rel in _xml(archive, rel_path):
        # External links are descriptions only; no network request is made.
        if rel.get('TargetMode') == 'External':
            continue
        target = rel.get('Target', '')
        resolved = posixpath.normpath(posixpath.join(folder, target))
        if target.startswith('/'):
            resolved = target.lstrip('/')
        if resolved == '..' or resolved.startswith('../') or '\\' in resolved:
            raise ValueError('Недопустимый путь внутри Excel-файла.')
        result[rel.get('Id')] = (resolved, rel.get('Type', '').rsplit('/', 1)[-1])
    return result


def _read_cells(root, shared_strings, state):
    cells = []
    for cell in root.findall('s:sheetData/s:row/s:c', NS):
        value = cell.find('s:v', NS)
        formula = cell.find('s:f', NS)
        inline = cell.find('s:is', NS)
        if value is None and formula is None and inline is None:
            continue  # Formatting alone is not a student's answer.
        state['cells'] += 1
        if state['cells'] > MAX_XLSX_CELLS:
            raise ValueError('В Excel-файле слишком много заполненных ячеек.')
        entry = {'cell': cell.get('r'), 'type': cell.get('t', 'n')}
        text = value.text if value is not None else None
        if cell.get('t') == 's' and text is not None:
            index = int(text)
            if not 0 <= index < len(shared_strings):
                raise ValueError('Повреждена ссылка на текст ячейки Excel.')
            text = shared_strings[index]
        elif inline is not None:
            text = ''.join(t.text or '' for t in inline.iterfind('.//s:t', NS))
        entry['value'] = text
        if formula is not None:
            # Shared/array formulas can refer to a master cell. Preserve attributes.
            entry['formula'] = formula.text
            if formula.attrib:
                entry['formula_attributes'] = dict(formula.attrib)
        cells.append(entry)
    return cells


def _read_charts(archive, sheet_root, sheet_part, sheet_name, state):
    charts = []
    sheet_rels = _relationships(archive, sheet_part)
    for drawing in sheet_root.findall('s:drawing', NS):
        drawing_part, kind = sheet_rels[drawing.get('{' + NS['r'] + '}id')]
        if kind != 'drawing':
            continue
        drawing_root = _xml(archive, drawing_part)
        drawing_rels = _relationships(archive, drawing_part)
        for chart_ref in drawing_root.iterfind('.//c:chart', NS):
            chart_part, kind = drawing_rels[chart_ref.get('{' + NS['r'] + '}id')]
            if kind != 'chart':
                continue
            state['charts'] += 1
            if state['charts'] > MAX_XLSX_CHARTS:
                raise ValueError('В Excel-файле слишком много диаграмм.')
            chart_root = _xml(archive, chart_part)
            charts.append({
                'sheet': sheet_name,
                'part': chart_part,
                # The saved specification includes titles, series, cell references,
                # cached points and axes. It is not a rendered screenshot.
                'definition_xml': ET.tostring(chart_root, encoding='unicode'),
            })
    return charts


def extract_xlsx_evidence(content):
    """Return JSON text, or raise when a workbook cannot be read completely."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        parts = archive.infolist()
        if len(parts) > MAX_XLSX_PARTS:
            raise ValueError('Слишком много частей внутри Excel-файла.')
        if sum(part.file_size for part in parts) > MAX_XLSX_UNCOMPRESSED_BYTES:
            raise ValueError('Распакованный Excel-файл слишком большой.')
        if len({part.filename for part in parts}) != len(parts):
            raise ValueError('В Excel-файле повторяются имена частей.')
        roots = _relationships(archive, '')
        workbook_part = next(path for path, kind in roots.values() if kind == 'officeDocument')
        workbook_root = _xml(archive, workbook_part)
        rels = _relationships(archive, workbook_part)
        strings_part = next((path for path, kind in rels.values() if kind == 'sharedStrings'), None)
        shared_strings = []
        if strings_part:
            strings_root = _xml(archive, strings_part)
            shared_strings = [
                ''.join(t.text or '' for t in item.iterfind('.//s:t', NS))
                for item in strings_root
            ]
        sheets = workbook_root.findall('s:sheets/s:sheet', NS)
        if not sheets or len(sheets) > MAX_XLSX_SHEETS:
            raise ValueError('Ожидается от 1 до 20 листов Excel.')
        result = {
            'format': 'xlsx',
            'notice': (
                'Сохранённые ячейки и определения диаграмм OOXML; это не изображение. '
                'Формулы не исполнялись. value у формулы — сохранённый результат, '
                'который может отсутствовать или быть устаревшим. '
                'Внешние ссылки не загружались. Встроенные картинки не распознавались.'
            ),
            'sheets': [],
            'charts': [],
        }
        state = {'cells': 0, 'charts': 0}
        for sheet in sheets:
            part, kind = rels[sheet.get('{' + NS['r'] + '}id')]
            if kind != 'worksheet':
                raise ValueError('Этот тип листа Excel не поддерживается.')
            root = _xml(archive, part)
            result['sheets'].append({
                'name': sheet.get('name'),
                'state': sheet.get('state', 'visible'),
                'cells': _read_cells(root, shared_strings, state),
            })
            result['charts'].extend(_read_charts(archive, root, part, sheet.get('name'), state))
            if len(json.dumps(result, ensure_ascii=False)) > MAX_XLSX_TEXT_CHARS:
                raise ValueError('Слишком много текста для проверки Excel-отчёта.')
        text = json.dumps(result, ensure_ascii=False)
        if len(text) > MAX_XLSX_TEXT_CHARS:
            raise ValueError('Слишком много текста для проверки Excel-отчёта.')
        return text


def _safe_filename(filename):
    name = os.path.basename((filename or '').replace('\\', '/')).strip()
    name = ''.join(char for char in name if char.isprintable() and char not in '/\\')[:255]
    if not name.lower().endswith('.xlsx'):
        raise ValueError('Прикрепите книгу Excel в формате .xlsx.')
    return name


def create_spreadsheet_submission(filename, data, max_bytes):
    name = _safe_filename(filename)
    if not data or len(data) > max_bytes:
        raise ValueError(f'Выберите непустой Excel-файл размером до {max_bytes // (1024 * 1024)} МБ.')
    try:
        extract_xlsx_evidence(data)
    except Exception as exc:
        raise ValueError('Не удалось прочитать Excel-файл: он повреждён, не поддерживается или превышает ограничения.') from exc
    return json.dumps({'version': 1, 'filename': name,
                       'data': base64.b64encode(data).decode('ascii')}, ensure_ascii=False)


def parse_spreadsheet_submission(raw_value, max_bytes):
    try:
        if len(raw_value) > 4 * ((max_bytes + 2) // 3) + 2048:
            raise ValueError('Excel-файл слишком большой.')
        payload = json.loads(raw_value)
        if not isinstance(payload, dict) or payload.get('version') != 1:
            raise ValueError('Неизвестный формат данных Excel.')
        filename = _safe_filename(payload.get('filename'))
        data = base64.b64decode(payload.get('data', ''), validate=True)
        if not data or len(data) > max_bytes:
            raise ValueError('Excel-файл пуст или слишком большой.')
        evidence = extract_xlsx_evidence(data)
    except (TypeError, KeyError, StopIteration, binascii.Error, zipfile.BadZipFile) as exc:
        raise ValueError('Повреждены данные Excel-файла.') from exc
    return {'filename': filename, 'data': data, 'evidence': evidence}
