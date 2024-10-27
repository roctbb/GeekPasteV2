comment_template = """
Ввод:

{0}

Ожидаемый вывод:

{1}

Вывод программы:

{2}
"""


def perform_tests(runner, source_code=None):
    for width, height in [(5, 6), (10, 8), (12, 4)]:
        input_data = f"{width}\n{height}\n"
        expected_width = width
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
                passed = len(row) == expected_width and all(33 <= ord(c) <= 127 for c in row)

                if not passed:
                    error = f"недостаточно символов в строке {i + 1 }"
                    break

                passed = len(set(row)) > width // 2
                if passed:
                    error = f"недостаточно уникальных символов в строке {i}"
                    break

        if not passed:
            return 1, comment_template.format(input_data.strip(), f"квадрат размером {width}x{height} ({error})",
                                              original_result)

    return 5, "OK! :)"


"""
import random

def generate_square_message(width, height):
    square_message = [
        ''.join(chr(random.randint(33, 127)) for _ in range(width))
        for _ in range(height)
    ]
    return '\n'.join(square_message)

width = int(input("Введите ширину:"))
height = int(input("Введите высоту:"))
print()
print()
print(generate_square_message(width, height))
"""
