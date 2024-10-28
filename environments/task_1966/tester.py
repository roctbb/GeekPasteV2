from PIL import Image, ImageChops
import numpy as np

tests = [
    {
        "input": "img.jpg",
        "output": "result.png",
        "steps": 5,
    },
    {
        "input": "img.jpg",
        "output": "result.png",
        "steps": 10,
    }
]


def process_image(path, steps=5):
    img = Image.open(path)

    vstep = img.height // (steps * 2)
    hstep = img.width // (steps * 2)

    vpos = 0
    hpos = 0

    for i in range(steps):
        part = img.crop((hpos, vpos, img.width - hpos, img.height - vpos))
        part = part.transpose(Image.ROTATE_180)
        img.paste(part, (hpos, vpos, img.width - hpos, img.height - vpos))
        vpos += vstep
        hpos += hstep

    return img


def perform_tests(runner, source_code=None):
    for test in tests:
        input_filename = test["input"]
        output_filename = test["output"]
        steps = test["steps"]

        correct_result = process_image(input_filename, steps)

        stdin = f"{input_filename}\n{output_filename}\n{steps}"
        runner(stdin)

        user_result = Image.open(output_filename)
        if not np.array_equal(np.array(correct_result), np.array(user_result)):
            return 1, "Изображения не совпадают."

    return 5, "OK! :)"


def synthetic_runner(stdin):
    input_filename, output_filename, steps = stdin.strip().split("\n")

    processed_image = process_image(input_filename, int(steps))
    processed_image.save(output_filename)


if __name__ == "__main__":
    score, comments = perform_tests(synthetic_runner)
    print(comments)
