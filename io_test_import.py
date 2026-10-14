"""Load frozen IO presets independently of the retired environment handlers."""
from functools import lru_cache
import json
import gzip
import hashlib
from pathlib import Path

from io_tests import validate_test_config


PILOT_TASK_IDS = frozenset((*range(2593, 2601), 2605, 2611, 2636))
REMAINING_PATH = Path(__file__).parent / 'io_test_presets' / 'grade8_remaining'
REMAINING_PRESETS = json.loads((REMAINING_PATH / 'index.json').read_text(encoding='utf-8'))['tasks']
ADDITIONAL_TASK_IDS = frozenset(map(int, REMAINING_PRESETS))
IMPORTABLE_TASK_IDS = PILOT_TASK_IDS | ADDITIONAL_TASK_IDS
RETIRED_TASK_IDS = PILOT_TASK_IDS
PRESETS_PATH = Path(__file__).parent / 'io_test_presets' / 'grade8_2026.json'


@lru_cache(maxsize=1)
def _presets():
    data = json.loads(PRESETS_PATH.read_text(encoding='utf-8'))
    if data['format'] != 1 or {int(key) for key in data['tasks']} != PILOT_TASK_IDS:
        raise ValueError('Некорректный исходный набор тестов.')
    return data['tasks']


@lru_cache(maxsize=4)
def _additional_config(task_id):
    raw = gzip.decompress((REMAINING_PATH / f'{task_id}.json.gz').read_bytes())
    if hashlib.sha256(raw).hexdigest() != REMAINING_PRESETS[str(task_id)]['sha256']:
        raise ValueError('Повреждён исходный набор тестов.')
    return json.loads(raw)


def preset_metadata(task_id):
    if task_id in PILOT_TASK_IDS:
        preset = _presets()[str(task_id)]
        return {'language': preset['language'], 'points': preset['points']}
    if task_id in ADDITIONAL_TASK_IDS:
        return dict(REMAINING_PRESETS[str(task_id)])
    raise ValueError('Для этой задачи перенос тестов пока не подготовлен.')


def import_environment_tests(task_id, language, maximum_points):
    # Frozen data are independent of the retired environment handlers.
    metadata = preset_metadata(task_id)
    if language != metadata['language'] or maximum_points != metadata['points']:
        raise ValueError(f'Исходные тесты рассчитаны на {metadata["language"]} и {metadata["points"]} баллов. Проверьте параметры задачи.')
    config = (_presets()[str(task_id)]['config'] if task_id in PILOT_TASK_IDS
              else _additional_config(task_id))
    return validate_test_config(config, maximum_points)
