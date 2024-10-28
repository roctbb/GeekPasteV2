from PIL import Image, ImageChops
import numpy as np

tests = [
    {
        "input": "img.jpg",
        "output": "result.png",
    }
]


def process_image(path):
    img = Image.open(path)

    for j in range(img.height // 2, img.height):
        for i in range(img.width):
            img.putpixel((i, j), img.getpixel((i, img.height - 1)))

    return img


def perform_tests(runner, source_code=None):
    for test in tests:
        input_filename = test["input"]
        output_filename = test["output"]
        correct_result = process_image(input_filename)

        stdin = f"{input_filename}\n{output_filename}"
        runner(stdin)

        user_result = Image.open(output_filename)
        if not np.array_equal(np.array(correct_result), np.array(user_result)):
            return 1, "Изображения не совпадают."

    return 5, "OK! :)"


def synthetic_runner(stdin):
    input_filename, output_filename = stdin.strip().split("\n")

    processed_image = process_image(input_filename)
    processed_image.save(output_filename)


if __name__ == "__main__":
    score, comments = perform_tests(synthetic_runner)
    print(comments)
