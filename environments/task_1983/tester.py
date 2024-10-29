

scenarios = [
    # (input_data, expected_output)
    ("10\n12\n8\n6\n14\n10\n10\n", "0\n2\n-2\n-4\n4\n0\n0\n"),
    ("5\n5\n5\n5\n5\n5\n5\n", "0\n0\n0\n0\n0\n0\n0\n"),
    ("0\n0\n0\n0\n0\n0\n0\n", "0\n0\n0\n0\n0\n0\n0\n")
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


def calculate_temperature_deviations(input_data):
    temperatures = list(map(int, input_data.strip().split('\n')))
    avg_temp = sum(temperatures) / len(temperatures)
    deviations = [round(temp - avg_temp) for temp in temperatures]
    deviations_str = "\n".join(map(str, deviations))
    output = f"Средняя температура за неделю: {avg_temp}\nОтклонения от средней температуры по дням:\n{deviations_str}\n"
    return output


def simulated_runner(user_input):
    return calculate_temperature_deviations(user_input)


if __name__ == "__main__":
    points, comments = perform_tests(simulated_runner, None)
    print(comments)

