scenarios = [
    (
        "Лол, кек, чебурек.",
        "В тексте недопустимая лексика!\n***, ***, чебурек."
    ),
    (
        "Кандибобер - отличная шляпа!",
        "Все хорошо!\nКандибобер - отличная шляпа!"
    ),
    (
        "КЕК и ЛоЛ - популярные интернет-мемы.",
        "В тексте недопустимая лексика!\n*** и *** - популярные интернет-мемы."
    ),
    (
        "Мой новый проект называется ЛоЛКеК.",
        "В тексте недопустимая лексика!\nМой новый проект называется ******."
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
        if not result.lower() == expected_output.lower():
            return 1, comment_template.format(input_data, expected_output, result)
    return 5, "OK! :)"


def simulated_runner(user_input):
    censored_words = ["кек", "лол"]
    text = user_input.strip()
    lower_text = text.lower()
    censored = False

    for word in censored_words:
        if word in lower_text:
            censored = True
            text = text.lower().replace(word, '*' * len(word))

    if censored:
        return f"В тексте недопустимая лексика!\n{text.capitalize()}"
    else:
        return f"Все хорошо!\n{user_input}"


if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))
