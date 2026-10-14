"""Load frozen IO presets independently of the retired environment handlers."""
from functools import lru_cache
import json
from pathlib import Path

from io_tests import validate_test_config


PILOT_TASK_IDS = frozenset((*range(2593, 2601), 2605, 2611, 2636))
PRESETS_PATH = Path(__file__).parent / 'io_test_presets' / 'grade8_2026.json'


@lru_cache(maxsize=1)
def _presets():
    data = json.loads(PRESETS_PATH.read_text(encoding='utf-8'))
    if data['format'] != 1 or {int(key) for key in data['tasks']} != PILOT_TASK_IDS:
        raise ValueError('Некорректный исходный набор тестов.')
    return data['tasks']


def import_environment_tests(task_id, language, maximum_points):
    # Keep the entry point used by the editor; no environment code is imported.
    if task_id not in PILOT_TASK_IDS:
        raise ValueError('Для этой задачи перенос тестов пока не подготовлен.')
    preset = _presets()[str(task_id)]
    if language != preset['language'] or maximum_points != preset['points']:
        raise ValueError(f'Исходные тесты рассчитаны на C++ и {preset["points"]} баллов. Проверьте параметры задачи.')
    return validate_test_config(preset['config'], maximum_points)
