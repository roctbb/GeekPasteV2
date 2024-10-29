scenarios = [
    (
        "roctbb@gmail.com\n",
        "Правильно"
    ),
    (
        "roctbbgmail.@com\n",
        "Неправильно"
    ),
    (
        "user@example.com\n",
        "Правильно"
    ),
    (
        "user@example@com\n",
        "Неправильно"
    ),
    (
        "example-.test@site.org\n",
        "Правильно"
    ),
    (
        "@example.com\n",
        "Неправильно"
    ),
    (
        "example.com\n",
        "Неправильно"
    ),
    (
        "example@com.\n",
        "Неправильно"
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


def is_valid_email(email):
    import re
    pattern = r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$'
    if re.match(pattern, email):
        last_dot_pos = email.rfind('.')
        if last_dot_pos > email.find('@') + 1 and (len(email) - last_dot_pos in [3, 4]):
            return True
    return False


def simulated_runner(user_input):
    email = user_input.strip()
    if is_valid_email(email):
        return "Правильно"
    else:
        return "Неправильно"


if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))
