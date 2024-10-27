scenarios = [
    (
        "100\n150\n150\n100\n-1\n",
        "125.0"
    ),
    (
        "200\n300\n-1\n",
        "250.0"
    ),
    (
        "50\n50\n50\n50\n-1\n",
        "50.0"
    ),
    (
        "-1\n",
        "0"
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
        if not result.endswith(expected_output.lower()):
            return 1, comment_template.format(input_data, expected_output, result)
    return 5, "OK! :)"


"""
total_likes = 0
count = 0

while True:
    like = int(input("Сколько лайков у поста: "))
    if like == -1:
        break
    total_likes += like
    count += 1

average_likes = total_likes / count if count != 0 else 0
print(f"Среднее количество лайков: {average_likes}")
"""
