scenarios = [
    (
        "кандибобер\n",
        "кандииднак"
    ),
    (
        "вундервафля\n",
        "вундереднув"
    ),
    (
        "abcdef\n",
        "abccba"
    ),
    (
        "xyz\n",
        "xyx"
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
        result = runner(input_data).strip().lower()
        if not result.lower().endswith(expected_output.lower()):
            return 1, comment_template.format(input_data, expected_output, result)
    return 5, "OK! :)"

def simulated_runner(user_input):
    # Calculate the middle index
    user_input = user_input.strip()
    middle_index = len(user_input) // 2
    # Reflect the left half on the right half
    if len(user_input) % 2 == 0:
        result = user_input[:middle_index] + user_input[:middle_index][::-1]
    else:
        result = user_input[:middle_index + 1] + user_input[:middle_index][::-1]
    # Output the result
    return result

if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))


