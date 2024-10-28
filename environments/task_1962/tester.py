import os
from PIL import Image
import numpy as np
import random

# Larger test images
scenarios = [
    (
        np.array([
                     [(255, 255, 0), (60, 170, 20)] * 10,
                     [(15, 45, 75), (90, 120, 150)] * 10
                 ] * 10, dtype=np.int16),
        'input_image1.png',
        'output_image1.png',
        100
    ),
    (
        np.array([
                     [(255, 0, 0), (0, 255, 0)] * 10,
                     [(0, 0, 255), (255, 255, 255)] * 10
                 ] * 10, dtype=np.int16),
        'input_image2.png',
        'output_image2.png',
        150
    ),
    (
        np.array([
                     [(100, 100, 100), (150, 150, 150), (200, 200, 200)] * 10,
                     [(50, 50, 50), (0, 0, 0), (255, 255, 255)] * 10
                 ] * 10, dtype=np.int16),
        'input_image3.png',
        'output_image3.png',
        60
    )
]


def perform_tests(runner, source_code=None):
    for index, (input_pixels, input_filename, output_filename, level) in enumerate(scenarios):
        # Save input image
        input_image = Image.fromarray(input_pixels.astype(np.uint8))
        input_image.save(input_filename)
        stdin = f"{input_filename}\n{output_filename}\n{level}"
        runner(stdin)
        # Load result image and check
        with Image.open(output_filename) as output_image:
            result = np.array(output_image)
        # Check for overflow
        if np.any(result < 0) or np.any(result > 255):
            return 1, "Результирующее изображение имеет пиксельные компоненты вне допустимого диапазона (0-255)."
        if result.shape != input_pixels.shape:
            return 1, "Размер изображения изменился."

        # Check that pixel components changed by different values
        diff = input_pixels - result
        components_check = True
        for i in range(input_pixels.shape[0]):
            for j in range(input_pixels.shape[1]):
                deltas = set(diff[i, j])
                if len(deltas) == 1 and all(val == 0 for val in deltas):
                    components_check = False
                if not components_check:
                    break
            if not components_check:
                break
        if components_check:
            return 1, "Не все компоненты пикселей изменились на разные значения."
        # Check that noise was added
        if not np.any(diff):
            return 1, "Шум не был добавлен в изображение или он слишком мал."
        # Check that noise didn't drastically alter the brightness
        input_brightness = np.mean(input_pixels)
        result_brightness = np.mean(result)
        brightness_diff = np.abs(result_brightness - input_brightness)
        if brightness_diff > 10:
            return 1, "Яркость результирующего изображения значительно отличается."
    return 5, "OK! :)"


def synthetic_runner(stdin):
    input_filename, output_filename, level = stdin.strip().split("\n")
    level = int(level)
    from PIL import Image
    import random
    def add_color_noise(img, noise_level=20, seed=42):
        random.seed(seed)
        for i in range(img.width):
            for j in range(img.height):
                r, g, b = img.getpixel((i, j))
                noise_r = random.randint(-noise_level, noise_level)
                noise_g = random.randint(-noise_level, noise_level)
                noise_b = random.randint(-noise_level, noise_level)
                img.putpixel((i, j), (min(255, max(0, r + noise_r)),
                                      min(255, max(0, g + noise_g)),
                                      min(255, max(0, b + noise_b))))
        return img

    input_image = Image.open(input_filename)
    noisy_image = add_color_noise(input_image, level)
    noisy_image.save(output_filename)


if __name__ == "__main__":
    score, comments = perform_tests(synthetic_runner)
    print(comments)
