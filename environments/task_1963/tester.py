import os
from PIL import Image
import numpy as np

scenarios = [
    (
        np.array([
                     [(255, 255, 255)] * 20,
                     [(200, 200, 200)] * 20
                 ] * 20, dtype=np.uint8),
        'input_image1.png',
        'output_image1.png'
    ),
    (
        np.array([
                     [(0, 0, 0)] * 20,
                     [(50, 50, 50)] * 20
                 ] * 20, dtype=np.uint8),
        'input_image2.png',
        'output_image2.png'
    ),
    (
        np.array([
                     [(100, 100, 100)] * 20,
                     [(150, 150, 150)] * 20
                 ] * 20, dtype=np.uint8),
        'input_image3.png',
        'output_image3.png'
    )
]


def perform_tests(runner, source_code=None):
    for index, (input_pixels, input_filename, output_filename) in enumerate(scenarios):
        # Save input image
        input_image = Image.fromarray(input_pixels.astype(np.uint8))
        input_image.save(input_filename)
        stdin = f"{input_filename}\n{output_filename}"
        runner(stdin)
        # Load result image and check
        with Image.open(output_filename) as output_image:
            result = np.array(output_image)

        # Check for overflow
        if np.any(result < 0) or np.any(result > 255):
            return 1, "Результирующее изображение имеет пиксельные компоненты вне допустимого диапазона (0-255)."
        if result.shape != input_pixels.shape:
            return 1, "Размер изображения изменился."

        if np.array_equal(result, input_pixels):
            return 1, "Изображение не изменилось."

        # Check quadrants
        height, width, _ = result.shape
        mid_h, mid_w = height // 2, width // 2

        quadrants = [
            (result[:mid_h, :mid_w, :], input_pixels[:mid_h, :mid_w, :]),
            (result[:mid_h, mid_w:, :], input_pixels[:mid_h, mid_w:, :]),
            (result[mid_h:, :mid_w, :], input_pixels[mid_h:, :mid_w, :]),
            (result[mid_h:, mid_w:, :], input_pixels[mid_h:, mid_w:, :])
        ]

        levels = []  # For storing levels of each quadrant

        for quadrant, original in quadrants:
            diff = quadrant - original
            qlevel = []

            for channel in range(3):  # Loop over color channels
                level = None
                for i in range(quadrant.shape[0]):
                    for j in range(quadrant.shape[1]):
                        if quadrant[i, j, channel] != 0 and quadrant[i, j, channel] != 255:
                            if level is None:
                                level = diff[i, j, channel]
                            else:
                                if level != diff[i, j, channel]:
                                    return 1, "Изменения не одинаковы в рамках квадранта."
                qlevel.append(level)
            levels.append(np.array(qlevel))

        for i in range(len(levels)):
            for j in range(i + 1, len(levels)):
                if np.array_equal(levels[i], levels[j]):
                    return 2, "Изменения одинаковы между различными квадрантами."

    return 5, "OK! :)"


def synthetic_runner(stdin):
    input_filename, output_filename = stdin.strip().split("\n")
    from PIL import Image

    def tint_quadrants(img):
        width, height = img.size
        mid_w, mid_h = width // 2, height // 2

        pixels = img.load()

        for i in range(width):
            for j in range(height):
                r, g, b = pixels[i, j]

                if i < mid_w and j < mid_h:
                    cr, cg, cb = 255, 255, 0  # Yellow tint for top-left quadrant
                elif i >= mid_w and j < mid_h:
                    cr, cg, cb = 255, 0, 0  # Red tint for top-right quadrant
                elif i < mid_w and j >= mid_h:
                    cr, cg, cb = 0, 0, 255  # Blue tint for bottom-left quadrant
                else:
                    cr, cg, cb = 0, 255, 0  # Green tint for bottom-right quadrant

                pixels[i, j] = (r + cr, g + cg, b + cb)

        return img

    input_image = Image.open(input_filename)
    tinted_image = tint_quadrants(input_image)
    tinted_image.save(output_filename)


if __name__ == "__main__":
    score, comments = perform_tests(synthetic_runner)
    print(comments)
