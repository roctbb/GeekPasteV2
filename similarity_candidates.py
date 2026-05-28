from models import Code


def same_value_filter(column, value):
    if value is None:
        return column.is_(None)
    return column == value


def similarity_candidates_query(code):
    return (
        Code.query
        .filter(Code.user_id.isnot(None), Code.user_id != code.user_id)
        .filter(same_value_filter(Code.task_id, code.task_id))
        .filter(same_value_filter(Code.course_id, code.course_id))
        .filter(same_value_filter(Code.lang, code.lang))
    )
