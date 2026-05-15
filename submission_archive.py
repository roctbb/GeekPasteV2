import io
import json
import re
import zipfile

from submission_file_filter import should_ignore_submission_file


MAX_NESTED_ZIP_DEPTH = 3
MAX_ARCHIVE_FILE_COUNT = 1000
MAX_TOTAL_EXTRACTED_BYTES = 50 * 1024 * 1024
MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024


def _normalize_zip_path(path):
    return path.replace('\\', '/').lstrip('/')


def _is_nested_zip(file_name, content):
    if not file_name.lower().endswith('.zip'):
        return False
    return zipfile.is_zipfile(io.BytesIO(content))


def _append_file_info(file_info, file_name, content):
    if b'\x00' in content:
        file_info.append({
            "name": file_name,
            "content": f"Файл размером {len(content)} байт.",
            "is-binary": True
        })
    else:
        file_info.append({
            "name": file_name,
            "content": content.decode(errors='replace'),
            "is-binary": False
        })


def _append_large_file_placeholder(file_info, file_name, file_size):
    file_info.append({
        "name": file_name,
        "content": f"Файл размером {file_size} байт.",
        "is-binary": True
    })


def _track_zip_entry_limits(zip_item, state):
    state['file_count'] += 1
    if state['file_count'] > MAX_ARCHIVE_FILE_COUNT:
        raise ValueError("Слишком много файлов в архиве.")

    state['total_size'] += zip_item.file_size
    if state['total_size'] > MAX_TOTAL_EXTRACTED_BYTES:
        raise ValueError("Слишком большой распакованный архив.")


def _extract_zip_entries(zip_ref, file_info, prefix='', depth=0, state=None):
    if state is None:
        state = {'file_count': 0, 'total_size': 0}

    for zip_item in zip_ref.infolist():
        file_name = _normalize_zip_path(prefix + zip_item.filename)

        if zip_item.is_dir():
            continue

        if should_ignore_submission_file(file_name):
            continue

        _track_zip_entry_limits(zip_item, state)

        if zip_item.file_size > MAX_TEXT_FILE_BYTES:
            _append_large_file_placeholder(file_info, file_name, zip_item.file_size)
            continue

        with zip_ref.open(zip_item) as extracted_file:
            content = extracted_file.read()

        if depth < MAX_NESTED_ZIP_DEPTH and _is_nested_zip(file_name, content):
            with zipfile.ZipFile(io.BytesIO(content), 'r') as nested_zip:
                _extract_zip_entries(nested_zip, file_info, prefix=f"{file_name}/", depth=depth + 1, state=state)
            continue

        _append_file_info(file_info, file_name, content)


def extract_data_from_zipfile(file):
    try:
        with zipfile.ZipFile(io.BytesIO(file), 'r') as zip_ref:
            file_info = []
            _extract_zip_entries(zip_ref, file_info)
            return json.dumps(file_info, ensure_ascii=False)
    except Exception:
        return None


def rebuild_zip(code):
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for f in json.loads(code.code):
            if f.get("is-binary") or (
                    "is-binary" not in f and re.fullmatch(r"Файл размером \d+ байт\.", f["content"].strip())):
                continue
            zipf.writestr(f["name"], f["content"])

    memory_file.seek(0)

    return memory_file.read()
