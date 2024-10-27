import os
from PIL import Image
import numpy as np
import io

scenarios = [
    (
        np.array([
            [(255, 255, 0), (60, 170, 20)],
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

Ошибка: 

В итоговом изображении было найдено больше или меньше двух цветов.

Вывод программы:

Изображение {1}
"""


def perform_tests(runner, source_code=None):
    for index, (input_pixels, input_filename, output_filename) in enumerate(scenarios):
        # Сохранение входного изображения
        input_image = Image.fromarray(input_pixels)
        input_image.save(input_filename)
        stdin = f"{input_filename}\n{output_filename}"
        runner(stdin)
        # Проверка количества цветов в итоговом изображении
        with Image.open(output_filename) as output_image:
            result = np.array(output_image)
        unique_colors = np.unique(result.reshape(-1, result.shape[2]), axis=0)
        if len(unique_colors) != 2:
            return 1, comment_template.format(input_pixels, result)
    return 5, "OK! :)"


"""
from PIL import Image
input_filename = input("Введите имя входного файла: ")
output_filename = input("Введите имя выходного файла: ")
black = (0, 0, 0)
white = (255, 255, 255)
threshold = 128

input_image = Image.open(input_filename)
for i in range(input_image.height):
    for j in range(input_image.width):
        r, g, b = input_image.getpixel((j, i))
        a = (r + g + b) // 3
        input_image.putpixel((j, i), black if a < threshold else white)

input_image.save(output_filename)
print(f"Изображение сохранено как {output_filename}")
"""
