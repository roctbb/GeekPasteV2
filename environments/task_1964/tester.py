from PIL import Image
import numpy as np

scenarios = [
    (
        np.array([
            [(20, 100, 0), (60, 170, 20)],
            [(15, 45, 75), (90, 120, 150)]
        ], dtype=np.uint8),
        'input_image1.png',
        'output_image1.png'
    ),
    (
        np.array([
            [(255, 0, 0), (0, 255, 0)],
            [(0, 0, 255), (255, 255, 255)]
        ], dtype=np.uint8),
        'input_image2.png',
        'output_image2.png'
    ),
    (
        np.array([
            [(100, 100, 100), (150, 150, 150), (200, 200, 200)],
            [(50, 50, 50), (0, 0, 0), (255, 255, 255)]
        ], dtype=np.uint8),
        'input_image3.png',
        'output_image3.png'
    )
]
comment_template = """
Ввод:
Изображение {0}

Вывод программы:
Изображение {1}

Ожидаемый вывод:
Изображение {2}
"""


def reflect_left_half(image_array):
    input_image = Image.fromarray(image_array)
    for y in range(input_image.height):
        for x in range(input_image.width // 2):
            input_image.putpixel((input_image.width - x - 1, y), input_image.getpixel((x, y)))
    return np.array(input_image)



def perform_tests(runner):
    for index, (input_pixels, input_filename, output_filename) in enumerate(scenarios):
        # Сохранение входного изображения
        input_image = Image.fromarray(input_pixels)
        input_image.save(input_filename)
        stdin = f"{input_filename}\n{output_filename}"

        # Запуск программы
        runner(stdin)

        # Сравнение с отраженным результатом
        with Image.open(output_filename) as output_image:
            result = np.array(output_image)
        expected_result = reflect_left_half(input_pixels)
        if not np.array_equal(result, expected_result):
            return 1, comment_template.format(input_pixels, result, expected_result)
    return 5, "OK! :)"


def synthetic_runner(stdin):
    input_filename, output_filename = stdin.strip().split("\n")

    # Чтение входного изображения
    input_image = Image.open(input_filename)
    input_array = input_image.load()
    width, height = input_image.size

    # Разделение изображения на две части
    half_width = width // 2

    # Отражение половины изображения и объединение изображений
    for y in range(height):
        for x in range(half_width):
            input_image.putpixel((width - x - 1, y), input_image.getpixel((x, y)))

    # Сохранение выходного изображения
    input_image.save(output_filename)


if __name__ == "__main__":
    score, comments = perform_tests(synthetic_runner)
    print(comments)
