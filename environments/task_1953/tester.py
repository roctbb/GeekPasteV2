scenarios = [
    (
        "3\nСветлана\n10\nТатьяна\n12\nАлексей\n3\n",
        "Самый-самый птиц - Татьяна!"
    ),
    (
        "2\nАндрей\n8\nМария\n15\n",
        "Самый-самый птиц - Мария!"
    ),
    (
        "4\nИван\n7\nПетр\n5\nОльга\n12\nНастя\n10\n",
        "Самый-самый птиц - Ольга!"
    ),
    (
        "1\nСергей\n20\n",
        "Самый-самый птиц - Сергей!"
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
num_birds = int(input("Сколько птиц в деревне? "))
birds = []

for i in range(num_birds):
    name = input(f"Как зовут птицу №{i + 1}? ")
    count = int(input(f"Сколько блестяшек у птицы №{i + 1}? "))
    birds.append((name, count))

max_bird = max(birds, key=lambda x: x[1])
print(f"Самый-самый птиц - {max_bird[0]}!")
"""
