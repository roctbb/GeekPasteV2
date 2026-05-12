from config import IGNORED_FILE_SUFFIXES, IGNORED_PARTS


def should_ignore_submission_file(file_name):
    normalized_name = file_name.replace('\\', '/').strip('/')
    if not normalized_name:
        return True

    path_parts = [part for part in normalized_name.split('/') if part and part != '.']
    lower_parts = [part.lower() for part in path_parts]
    lower_name = normalized_name.lower()

    for ignored_part in IGNORED_PARTS:
        part = ignored_part.strip().replace('\\', '/').strip('/').lower()
        if not part:
            continue
        if '/' in part:
            if lower_name == part or lower_name.startswith(part + '/') or f'/{part}/' in lower_name:
                return True
            continue
        if part in lower_parts:
            return True

    for suffix in IGNORED_FILE_SUFFIXES:
        suffix = suffix.strip().lower()
        if not suffix:
            continue
        if suffix.endswith('.*'):
            base_suffix = suffix[:-2]
            versioned_suffix = suffix[:-1]
            if any(
                path_part.endswith(base_suffix) or versioned_suffix in path_part
                for path_part in lower_parts
            ):
                return True
        elif lower_name.endswith(suffix) or any(path_part.endswith(suffix) for path_part in lower_parts):
            return True

    return False
