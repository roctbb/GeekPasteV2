import random


def generate_random_scenarios(num_scenarios, num_elements):
    scenarios = []
    for _ in range(num_scenarios):
        input_data = list(range(1, num_elements + 1))
        random.shuffle(input_data)
        input_str = "\n".join(map(str, input_data)) + "\n"
        output_str = "\n".join(map(str, sorted(input_data, reverse=True))) + "\n"
        scenarios.append((input_str, output_str))
    return scenarios


random.seed(0)  # Ensure reproducibility for the generated scenarios
scenarios = generate_random_scenarios(1, 10)

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
        result = runner(input_data).replace("\r", "")  # Normalize line endings
        if result.strip().replace('\n', ' ').endswith(expected_output.strip().replace('\n', ' ')):
            return 1, comment_template.format(input_data, expected_output, result)
    return 5, "OK! :)"


def reverse_numbers(numbers):
    return "\n".join(map(str, reversed(numbers))) + "\n"


def simulated_runner(user_input):
    numbers = list(map(int, user_input.strip().split()))
    return reverse_numbers(numbers)


if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))
