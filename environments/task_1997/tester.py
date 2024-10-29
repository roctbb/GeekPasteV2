scenarios = [
    (
        "RoctBB@gmail.com\nroctbb@GMAIL.com\n",
        "Одинаковые"
    ),
    (
        "roctbb@gmail.com\nroctbb@yandex.ru\n",
        "Разные"
    ),
    (
        "User@Example.Com \n user@example.com\n",
        "Одинаковые"
    ),
    (
        "user@example.com \nanother@example.com \n",
        "Разные"
    )
]

comment_template = """
Ввод:
{0}

Ожидаемое завершение вывода:
{1}

Вывод программы:
{2}

"""


def perform_tests(runner, source_code=None):
    for index, (input_data, expected_output) in enumerate(scenarios):
        result = runner(input_data).strip()
        if not result.lower().endswith(expected_output.lower()):
            return 1, comment_template.format(input_data, expected_output, result)
    return 5, "OK! :)"


def simulated_runner(user_input):
    emails = user_input.strip().split("\n")
    if len(emails) != 2:
        return "Ошибка ввода"
    email_1 = emails[0].strip().lower()
    email_2 = emails[1].strip().lower()
    if email_1 == email_2:
        return "Одинаковые"
    else:
        return "Разные"


if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))
