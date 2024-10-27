comment_template = """
Ввод:

{0}

Ожидаемый вывод:

{1}

Вывод программы:

{2}
"""


def perform_tests(runner, source_code=None):
    heights = [5, 7, 3]
    for height in heights:
        input_data = f"{height}\n"
        expected_height = height
        original_result = runner(input_data)
        result = original_result.strip().split("\n")
        error = ""

        passed = len(result) >= expected_height
        if not passed:
            error = "недостаточно строк"
        result = result[len(result) - expected_height:]
        if passed:
            for i, row in enumerate(result):
                expected_width = i + 1
                passed = len(row) == expected_width and all(33 <= ord(c) <= 127 for c in row)
                if not passed:
                    error = f"недостаточно символов в строке {i + 1}"
                    break
                passed = len(set(row)) > expected_width // 2
                if not passed:
                    error = f"недостаточно уникальных символов в строке {i + 1}"
                    break
        if not passed:
            return 1, comment_template.format(input_data.strip(), f"треугольник высотой {height} ({error})",
                                              original_result)
    return 5, "OK! :)"


"""
import random

def generate_triangle_message(height):
    message = [
        ''.join(chr(random.randint(33, 127)) for _ in range(i + 1))
        for i in range(height)
    ]
    return '\n'.join(message)

height = int(input("Введите высоту:"))
print()
print()
print(generate_triangle_message(height))
"""
