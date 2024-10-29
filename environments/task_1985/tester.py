scenarios = [
    # (input_data, expected_output)
    ("5\n3\n34\n10\n23\n56\n2\n", "56\n34\n23\n"),
    ("6\n2\n100\n200\n150\n90\n80\n210\n", "210\n200\n"),
    ("4\n1\n10\n20\n30\n40\n", "40\n"),
    ("3\n3\n30\n20\n10\n", "30\n20\n10\n"),
    ("5\n2\n1\n2\n3\n4\n5\n", "5\n4\n")
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
        result = runner(input_data)
        if not result.strip().endswith(expected_output.strip()):
            return 1, comment_template.format(input_data, expected_output, result)
    return 5, "OK! :)"


def get_winners(number_of_winners, results):
    sorted_results = sorted(results, reverse=True)
    return sorted_results[:number_of_winners]


def calculate_winners(input_data):
    lines = input_data.strip().split('\n')
    number_of_athletes = int(lines[0])
    number_of_winners = int(lines[1])
    results = list(map(int, lines[2:2 + number_of_athletes]))

    winners = get_winners(number_of_winners, results)
    return "\n".join(map(str, winners)) + "\n"


def simulated_runner(user_input):
    return calculate_winners(user_input)


if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))
