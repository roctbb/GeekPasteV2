"""
AI/LLM Usage Detection Module

Проверяет код на вероятность использования нейросетей для решения задач.
"""

import re
import ast
from datetime import datetime, timedelta


def check_rapid_progression(user_id, task_id, current_code_length, db_session):
    """
    Проверяет быстрые последовательные сдачи с большим приростом кода.

    Возвращает: (bool, str) - (обнаружено, причина)
    """
    from models import Code

    # Получаем последние сдачи за последние 30 минут
    window_start = datetime.now() - timedelta(minutes=30)
    recent_submissions = (Code.query
                         .filter_by(user_id=user_id, task_id=task_id)
                         .filter(Code.created_at >= window_start)
                         .order_by(Code.created_at.desc())
                         .limit(3)
                         .all())

    if len(recent_submissions) >= 2:
        # Проверяем прирост кода
        prev_submission = recent_submissions[1]

        try:
            prev_length = len(prev_submission.code) if prev_submission.lang != 'zip' else sum(len(part['content']) for part in eval(prev_submission.code) if not part.get('is-binary'))
        except:
            prev_length = len(prev_submission.code)

        # Если прирост более 200% или более 500 символов за короткое время
        time_diff = (recent_submissions[0].created_at - prev_submission.created_at).total_seconds() / 60
        code_growth = current_code_length - prev_length

        if time_diff < 10 and (code_growth > 500 or (prev_length > 0 and code_growth / prev_length > 2)):
            return True, f"Быстрый прирост кода: +{code_growth} символов за {time_diff:.1f} мин"

    return False, ""


def check_single_letter_names_python(code):
    """
    Проверяет наличие однобуквенных названий функций и переменных в Python.
    LLM часто генерируют нормальные имена, в отличие от студентов.

    Возвращает: (bool, str) - (подозрительно, причина)
    """
    try:
        tree = ast.parse(code)

        # Собираем все имена переменных и функций
        var_names = set()
        func_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_names.add(node.name)
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Store):
                    var_names.add(node.id)

        # Исключаем стандартные однобуквенные имена
        excluded = {'i', 'j', 'k', 'x', 'y', 'z', 'n', '_'}

        single_letter_vars = [v for v in var_names if len(v) == 1 and v not in excluded]
        single_letter_funcs = [f for f in func_names if len(f) == 1]

        total_names = len(var_names) + len(func_names)

        # Если почти нет однобуквенных имен, это подозрительно
        if total_names > 5 and len(single_letter_vars) + len(single_letter_funcs) == 0:
            return True, "Отсутствие однобуквенных имен переменных (типично для LLM)"

        return False, ""
    except:
        return False, ""


def check_unusual_patterns_python(code):
    """
    Проверяет наличие нестандартных языковых конструкций для Python,
    которые типичны для LLM, но редки у студентов.

    Возвращает: (bool, str) - (подозрительно, причина)
    """
    suspicious_reasons = []

    # Type hints (редко используются студентами)
    if re.search(r'def\s+\w+\([^)]*:\s*\w+', code) or re.search(r'->\s*\w+:', code):
        suspicious_reasons.append("использование type hints")

    # Docstrings (особенно многострочные)
    if re.search(r'"""[\s\S]{50,}"""', code) or re.search(r"'''[\s\S]{50,}'''", code):
        suspicious_reasons.append("подробные docstrings")

    # List/dict comprehensions с условиями (сложные)
    if re.search(r'\[.+\s+for\s+.+\s+in\s+.+\s+if\s+.+\]', code):
        suspicious_reasons.append("сложные list comprehensions")

    # Использование enumerate вместо range(len())
    enumerate_count = len(re.findall(r'enumerate\(', code))
    if enumerate_count >= 2:
        suspicious_reasons.append(f"частое использование enumerate ({enumerate_count} раз)")

    # Context managers (with statement с несколькими ресурсами)
    if re.search(r'with\s+\w+.*,.*:', code):
        suspicious_reasons.append("множественные context managers")

    # Walrus operator (Python 3.8+)
    if ':=' in code:
        suspicious_reasons.append("использование walrus operator (:=)")

    if suspicious_reasons:
        return True, "; ".join(suspicious_reasons)

    return False, ""


def check_unusual_patterns_cpp(code):
    """
    Проверяет нестандартные конструкции C++, типичные для LLM.
    """
    suspicious_reasons = []

    # Auto keyword с lambda
    if re.search(r'auto\s+\w+\s*=\s*\[', code):
        suspicious_reasons.append("auto с lambda")

    # Range-based for loops
    range_for_count = len(re.findall(r'for\s*\(\s*(?:auto|const\s+auto)\s*&?\s*\w+\s*:\s*\w+\s*\)', code))
    if range_for_count >= 2:
        suspicious_reasons.append(f"range-based for loops ({range_for_count})")

    # Smart pointers
    if 'std::unique_ptr' in code or 'std::shared_ptr' in code:
        suspicious_reasons.append("использование smart pointers")

    # Structured bindings (C++17)
    if re.search(r'auto\s*\[.*\]\s*=', code):
        suspicious_reasons.append("structured bindings")

    if suspicious_reasons:
        return True, "; ".join(suspicious_reasons)

    return False, ""


def check_unusual_patterns_js(code):
    """
    Проверяет нестандартные конструкции JavaScript, типичные для LLM.
    """
    suspicious_reasons = []

    # Arrow functions
    arrow_count = len(re.findall(r'=>', code))
    if arrow_count >= 3:
        suspicious_reasons.append(f"частое использование arrow functions ({arrow_count})")

    # Destructuring
    if re.search(r'(?:const|let|var)\s*\{[^}]+\}\s*=', code):
        suspicious_reasons.append("destructuring assignment")

    # Template literals с выражениями
    if re.search(r'`[^`]*\$\{[^}]+\}[^`]*`', code):
        suspicious_reasons.append("template literals")

    # Async/await
    if 'async ' in code and 'await ' in code:
        suspicious_reasons.append("async/await")

    # Optional chaining
    if '?.' in code:
        suspicious_reasons.append("optional chaining")

    # Nullish coalescing
    if '??' in code:
        suspicious_reasons.append("nullish coalescing (??)")

    if suspicious_reasons:
        return True, "; ".join(suspicious_reasons)

    return False, ""


def analyze_code_for_ai_usage(code, lang, user_id=None, task_id=None, db_session=None):
    """
    Основная функция анализа кода на использование AI.

    Возвращает: dict с ключами:
        - suspicious: bool - обнаружены ли подозрения
        - reasons: list - список причин подозрений
        - confidence: str - уровень уверенности (low/medium/high)
    """
    reasons = []

    # Проверка быстрого прироста кода (если есть данные о пользователе)
    if user_id and task_id and db_session:
        try:
            code_length = len(code) if lang != 'zip' else sum(len(part['content']) for part in eval(code) if not part.get('is-binary'))
        except:
            code_length = len(code)

        is_rapid, reason = check_rapid_progression(user_id, task_id, code_length, db_session)
        if is_rapid:
            reasons.append(reason)

    # Извлекаем текст кода для анализа
    code_text = code
    if lang == 'zip':
        try:
            parts = eval(code)
            code_text = '\n\n'.join([part['content'] for part in parts if not part.get('is-binary')])
        except:
            pass
    elif lang == 'ipynb':
        try:
            import json
            notebook = json.loads(code)
            code_cells = [cell['source'] for cell in notebook.get('cells', []) if cell['cell_type'] == 'code']
            code_text = "\n".join("".join(cell) for cell in code_cells)
        except:
            pass

    # Проверки в зависимости от языка
    if lang == 'python' or lang == 'ipynb':
        # Проверка однобуквенных имен
        is_suspicious, reason = check_single_letter_names_python(code_text)
        if is_suspicious:
            reasons.append(reason)

        # Проверка необычных паттернов
        is_suspicious, reason = check_unusual_patterns_python(code_text)
        if is_suspicious:
            reasons.append(reason)

    elif lang == 'cpp':
        is_suspicious, reason = check_unusual_patterns_cpp(code_text)
        if is_suspicious:
            reasons.append(reason)

    elif lang == 'javascript' or lang == 'js':
        is_suspicious, reason = check_unusual_patterns_js(code_text)
        if is_suspicious:
            reasons.append(reason)

    # Определяем уровень уверенности
    confidence = 'low'
    if len(reasons) >= 3:
        confidence = 'high'
    elif len(reasons) >= 2:
        confidence = 'medium'
    elif len(reasons) >= 1:
        confidence = 'low'

    return {
        'suspicious': len(reasons) > 0,
        'reasons': reasons,
        'confidence': confidence
    }


def get_ai_detection_prompt_addition():
    """
    Возвращает дополнение к промпту для GPT-проверки,
    чтобы модель оценивала вероятность использования LLM.
    """
    return (
        "\n\nДополнительно оцени вероятность того, что это решение было сгенерировано "
        "с помощью LLM (ChatGPT, Claude и т.п.) по шкале от 0 до 100. "
        "Обрати внимание на: идеальное форматирование, комментарии на английском, "
        "использование продвинутых конструкций языка, отсутствие типичных студенческих ошибок. "
        "В конце своего ответа добавь строку в формате: 'LLM_PROBABILITY: [число от 0 до 100]'"
    )
