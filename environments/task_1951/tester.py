comment_template = """
Ввод:

{0}

Ожидаемый вывод:

{1}

Вывод программы:

{2}
"""


def perform_tests(runner):
    for length in [5, 10, 50]:
        input_data = f"{length}\n"
        expected_length = length
        result = runner(input_data).strip().split(" ")[-1]

        passed = len(result) == expected_length and all(33 <= ord(c) <= 127 for c in result) and len(
            set(result)) > length // 2

        if not passed:
            return 1, comment_template.format(input_data.strip(), "[сообщение длиной {0}]".format(expected_length), result)

    return 5, "OK! :)"


"""
import random
a = int(input())
print(''.join(chr(random.randint(33, 127)) for _ in range(a)))
"""
