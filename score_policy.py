from functools import wraps
from olympiad_policy import full_solution_points


# Kept as compatibility names for callers of older release policies.
ZERO_SCORE_TEST_TASK_IDS = frozenset()


def normalize_test_points(task_id, points):
    """Every graded submission receives at least one attempt point."""
    contest_points = full_solution_points(task_id, points)
    if contest_points is not None:
        return contest_points
    return max(1, points or 0)


GRADE8_2026_TASK_IDS = range(2567, 2794)
ZERO_SCORE_GPT_TASK_IDS = frozenset()


def normalize_gpt_points(task_id, language, points, maximum):
    """Keep the maximum cap, without course/language exceptions to the floor."""
    return max(1, min(points, maximum))


ATTEMPT_COMMENT = 'Начислен 1 балл за сданную попытку. По критериям проверки — 0 баллов.'


def attempt_comment(comments):
    comments = comments or ''
    return comments if ATTEMPT_COMMENT in comments else ATTEMPT_COMMENT + '\n\n' + comments


def finalize_submission_score(code):
    """Defence at checker/callback boundaries; never award missing/pending work."""
    if getattr(code, 'check_points', None) is not None:
        contest_points = full_solution_points(getattr(code, 'task_id', None), code.check_points)
        if contest_points is not None:
            code.check_points = contest_points
            return
    if (getattr(code, 'check_points', None) == 0
            and str(getattr(code, 'code', '') or '').strip()
            and getattr(code, 'check_state', None) not in (
                None, 'not checked', 'checking', 'fetching')):
        code.check_points = 1
        code.check_comments = attempt_comment(code.check_comments)


def minimum_submission_score(checker):
    @wraps(checker)
    def checked(task, code, *args, **kwargs):
        result = checker(task, code, *args, **kwargs)
        finalize_submission_score(code)
        return result
    return checked
