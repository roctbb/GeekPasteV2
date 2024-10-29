def calculate_above_average_students(input_data):
    lines = input_data.strip().split('\n')
    num_students = int(lines[0])
    scores = [list(map(int, line.split())) for line in lines[1:]]

    avg_scores = [sum(student_scores) / len(student_scores) for student_scores in scores]
    class_avg = sum(avg_scores) / num_students
    above_avg_count = sum(1 for score in avg_scores if score > class_avg)

    return f"{above_avg_count}\n"


# Test scenarios
scenarios = [
    # (input_data, expected_output)
    ("3\n5 5 5 4\n3 3 3\n4 4 4 4\n", "2\n"),
    ("2\n2 2 2\n5 5 5 5\n", "1\n"),
    ("1\n3 3 4 4\n", "0\n"),
    ("5\n5 4 4\n3 2 2\n4 4 4\n5 5 5\n2 2 2\n", "3\n"),
    ("4\n3 3 3 3\n4 4 4 4\n2 2 2 2\n5 5 5 5\n", "2\n"),
    ("6\n5 5 5 5\n4 4 4 4\n3 3 3 3\n2 2 2 2\n5 5 4 4\n3 3 4 4\n", "3\n"),
    ("3\n2 2 2 2 2\n5 5 5 5 5\n4 4 4 4 4\n", "2\n")
]
comment_template = """
Ввод:
{0}

Ожидаемый вывод:
{1}

Вывод программы:
{2}

"""


def perform_tests(runner, source_code=None):
    for index, (input_data, expected_output) in enumerate(scenarios):
        result = runner(input_data)
        if not result.strip() == expected_output.strip():
            return 1, comment_template.format(input_data, expected_output, result)
    return 5, "OK! :)"


# Simulated runner to use the calculation function
def simulated_runner(user_input):
    return calculate_above_average_students(user_input)


if __name__ == "__main__":
    points, comments = perform_tests(simulated_runner, None)
    print(comments)
