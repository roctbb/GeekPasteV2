"""Explicit opt-in for contest tasks; ordinary lessons retain attempt points."""

# MKOSHP 2026, CodingProjects course publication, 18 tasks A..L2.
ALL_OR_NOTHING_TASK_POINTS = dict.fromkeys(range(2871, 2889), 5)

def full_solution_points(task_id, points):
    maximum = ALL_OR_NOTHING_TASK_POINTS.get(task_id)
    if maximum is None:
        return None
    return maximum if (points or 0) >= maximum else 0
