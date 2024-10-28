from PIL import Image, ImageChops
import numpy as np

tests = [
    {
        "input": "img.jpg",
        "output": "result.png",
        "step": 10,
    },
    {
        "input": "img.jpg",
        "output": "result.png",
        "step": 50,
    }
]


def process_image(path, step=10):
    img = Image.open(path)

    for i in range(0, img.width, step):
        part = img.crop((i, 0, i + step, img.height))
        part = part.transpose(Image.ROTATE_180)
        img.paste(part, (i, 0, i + step, img.height))

    return img.transpose(Image.ROTATE_180)

def perform_tests(runner, source_code=None):
    for test in tests:
        input_filename = test["input"]
        output_filename = test["output"]
        step = test["step"]

        correct_result = process_image(input_filename, step)

        stdin = f"{input_filename}\n{output_filename}\n{step}"
        runner(stdin)

        user_result = Image.open(output_filename)
        if not np.array_equal(np.array(correct_result), np.array(user_result)):
            return 1, "Изображения не совпадают."
        

    return 5, "OK! :)"


def synthetic_runner(stdin):
    input_filename, output_filename, step = stdin.strip().split("\n")

    processed_image = process_image(input_filename, int(step))
    processed_image.save(output_filename)


if __name__ == "__main__":
    score, comments = perform_tests(synthetic_runner)
    print(comments)
