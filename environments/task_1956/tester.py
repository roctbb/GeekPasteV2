comment_template = """
Ввод:

{0}

Ожидаемое завершение:

{1}

Вывод программы:

{2}

"""

import re


def perform_tests(runner, source_code=None):
    variable_pattern = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b\s*=')
    loop_iterator_pattern = re.compile(r'for\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+in')

    heights = [5, 7, 3]
    for height in heights:
        input_data = f"{height}\n"
        expected_height = height
        expected_result = "\n".join(" " * (expected_height - i - 1) + "*" * (2 * i + 1) for i in range(expected_height))
        original_result = runner(input_data)
        result = '\n'.join(original_result.rstrip().split('\n')[-height:])

        if not result.endswith(expected_result):
            return 1, comment_template.format(input_data.strip(), expected_result, original_result)

    variables = set(variable_pattern.findall(source_code))
    loop_iterators = set(loop_iterator_pattern.findall(source_code))

    variables = loop_iterators | variables

    if len(variables) > 2:
        return 5, f"OK! :) (использованы переменные {', '.join(variables)})"

    return 10, "OK! :)"

def synthetic_runner(stdin):
    height = int(stdin)

    spaces = height - 1
    res = "Введите высоту:\n\n"
    for i in range(height):
        res += " " * spaces + "*" * (2 * i + 1) + '\n'
        spaces -= 1
    return res

if __name__ == "__main__":
    print(perform_tests(synthetic_runner, "")[1])

"""

height = int(input("Введите высоту:"))
spaces = height -1
print()
for i in range(height):
    print(" " * spaces + "*" * (2 * i + 1))
    spaces -= 1
"""
