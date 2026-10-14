"""Explicitly reviewed environment imports; never execute arbitrary uploaded code."""
from inspect import getclosurevars

from io_tests import DEFAULT_OUTPUT_LIMIT, validate_test_config


PILOT_TASK_IDS = frozenset((*range(2593, 2601), 2605, 2611, 2636))


def import_environment_tests(task_id, language, maximum_points):
    if task_id not in PILOT_TASK_IDS:
        raise ValueError('Для этой задачи перенос тестов пока не подготовлен.')
    from environments import grade8_2026_chapters_1_4 as source

    maximum, handler = source.TASKS[task_id]
    if language != 'cpp' or maximum_points != maximum:
        raise ValueError(f'Исходные тесты рассчитаны на C++ и {maximum} баллов. Проверьте параметры задачи.')
    closure = getclosurevars(handler).nonlocals
    comparator = closure.get('comparator')
    if any(closure.get('source_checks', [True])) or comparator not in (source.tokens_equal, source.strict_text_equal):
        raise ValueError('Проверяющий модуль изменился; автоматический перенос требует проверки.')
    groups = source.materialize_task_groups(task_id)
    if len(groups) * 5 != maximum:
        raise ValueError('Правила оценки исходного модуля изменились.')
    tests = []
    for index, cases in enumerate(groups, 1):
        for case in cases:
            if case.get('comparator', comparator) is not comparator:
                raise ValueError('Тест использует отдельный алгоритм сравнения.')
            tests.append({
                'input': str(case['input']), 'output': str(case['expected']),
                'is_public': False, 'group': f'g{index}',
                'time_limit': case['time_limit'],
                'output_limit': case.get('capture_limit', DEFAULT_OUTPUT_LIMIT),
            })
    return validate_test_config({
        'comparison': 'exact' if comparator is source.strict_text_equal else 'tokens_ignore_cr',
        'trailing_whitespace': 'newlines',
        'scoring': 'groups' if len(groups) > 1 else 'all_or_nothing',
        'groups': [{'id': f'g{i}', 'name': f'Группа {i}', 'points': 5}
                   for i in range(1, len(groups) + 1)],
        'tests': tests,
    }, maximum_points)
