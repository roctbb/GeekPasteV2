ZERO_SCORE_TEST_TASK_IDS = frozenset(range(2440, 2463))


def normalize_test_points(task_id, points):
    """Preserve explicit zeroes for checkers whose rubric allows a zero score."""
    if points == 0 and task_id in ZERO_SCORE_TEST_TASK_IDS:
        return 0
    if not points:
        return 1
    return points
