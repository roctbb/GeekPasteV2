def repeat_string(task):
    # Split input task to get the input string
    lines = task.split('\n')
    input_string = lines[0]

    result = ""
    for i in range(len(input_string), 0, -1):
        result += input_string[:i] + "\n"

    return result

comment_template = """
Ввод:

{0}

Ожидаемый вывод:

{1}

Вывод программы:

{2}
"""


def perform_tests(runner):
    tasks = [
        "Это фиаско, братан!", "Hello World", "Lets Rock!"
    ]

    points = 1

    for task in tasks:
        result = runner(task).strip()
        expected_result = repeat_string(task).strip()

        if result.endswith(expected_result):
            points += 1
        else:
            return points, comment_template.format(task, expected_result, result)

    return 5, "OK! :)"

"""
text = input()
for i in range(len(text)):
    print(text[:len(text) - i])
"""
