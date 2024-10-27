scenarios = [
    (
        "1000000\n4\n100000\n300000\n300000\n500000\n",
        "Дохода не хватает!\nНужно дополнительно 200000 руб."
    ),
    (
        "1500000\n3\n400000\n300000\n500000\n",
        "Дохода хватает!"
    ),
    (
        "500000\n2\n150000\n200000\n",
        "Дохода хватает!"
    ),
    (
        "300000\n3\n100000\n150000\n100000\n",
        "Дохода не хватает!\nНужно дополнительно 50000 руб."
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
income = int(input("Введите доход за этот месяц: "))

# Input number of employees
num_employees = int(input("Введите количество сотрудников: "))

# Input salaries
salaries = []
for i in range(num_employees):
    salary = int(input(f"Введите зарплату сотрудника {i + 1}: "))
    salaries.append(salary)

total_salaries = sum(salaries)

# Check if income is enough
if income >= total_salaries:
    print("Дохода хватает!")
else:
    deficit = total_salaries - income
    print(f"Дохода не хватает!\nНужно дополнительно {deficit} руб.")
"""
