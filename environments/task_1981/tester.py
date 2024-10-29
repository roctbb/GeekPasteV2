import random

scenarios = [
    # (input_data, expected_output)
    ("2\n3\n4\n5\n0\n", "2: 25.0%\n3: 25.0%\n4: 25.0%\n5: 25.0%\n"),
    ("5\n4\n5\n0\n", "2: 0.0%\n3: 0.0%\n4: 33.3%\n5: 66.7%\n"),
    ("5\n5\n5\n5\n0\n", "2: 0.0%\n3: 0.0%\n4: 0.0%\n5: 100.0%\n"),
    ("2\n3\n0\n", "2: 50.0%\n3: 50.0%\n4: 0.0%\n5: 0.0%\n"),
    # Более крупный тестовый случай
    ("2\n2\n2\n2\n3\n3\n3\n4\n4\n5\n5\n5\n0\n",
     "2: 33.3%\n3: 25.0%\n4: 16.7%\n5: 25.0%\n")
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


def calculate_percentages(grades):
    counts = {2: 0, 3: 0, 4: 0, 5: 0}
    total = 0
    for grade in grades:
        if grade == 0:
            break
        if grade in counts:
            counts[grade] += 1
            total += 1

    result = []
    for grade in sorted(counts.keys()):
        percentage = counts[grade] / total * 100
        result.append(f"{grade}: {percentage:.1f}%")

    return "\n".join(result) + "\n"


def simulated_runner(user_input):
    grades = list(map(int, user_input.strip().split()))
    return calculate_percentages(grades)


if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))
