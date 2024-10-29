scenarios = [
    # (input_data, expected_output)
    ("0 1 2 3\n1\n", "3 0 1 2\n"),
    ("0 1 2 3\n6\n", "2 3 0 1\n"),
    ("1 2 3 4 5\n3\n", "3 4 5 1 2\n"),
    ("4 5 6 7\n2\n", "6 7 4 5\n"),
    ("1 2 3\n0\n", "1 2 3\n"),
    ("1 2 3\n4\n", "3 1 2\n"),  # shift greater than array size
    ("0 1 2 3\n8\n", "0 1 2 3\n"),  # shift equal to 2*array size
    ("0 1 2 3\n9\n", "3 0 1 2\n")  # shift greater than 2*array size
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


def rotate_array(arr, shift):
    shift = shift % len(arr)  # handle cases where shift >= len(arr)
    return arr[-shift:] + arr[:-shift]


def calculate_rotation(input_data):
    lines = input_data.strip().split('\n')
    array = list(map(int, lines[0].split()))
    shift = int(lines[1])
    rotated_array = rotate_array(array, shift)
    return " ".join(map(str, rotated_array)) + "\n"


def simulated_runner(user_input):
    return calculate_rotation(user_input)


if __name__ == "__main__":
    print(perform_tests(simulated_runner, None))
