ZERO_SCORE_TEST_TASK_IDS = frozenset(
    (*range(2440, 2463), *range(2567, 2770))
)


def normalize_test_points(task_id, points):
    """Preserve explicit zeroes for the deterministic rubric-based releases."""
    if points == 0 and task_id in ZERO_SCORE_TEST_TASK_IDS:
        return 0
    if not points:
        return 1
    return points


GRADE8_2026_TASK_IDS = range(2567, 2770)


def normalize_gpt_points(task_id, language, points, maximum):
    """Allow a real zero for image answers and the grade 8 (2026) rubric."""
    minimum = 0 if language == "image" or task_id in GRADE8_2026_TASK_IDS else 1
    return max(min(points, maximum), minimum)
