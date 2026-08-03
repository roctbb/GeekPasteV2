from io import BytesIO
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from image_submission import create_image_submission
from methods import check_task_with_gpt


class _GatewayResponse:
    content = b''

    def __init__(self, text='10\nРешение верное.'):
        self.text = text

    def json(self):
        return {
            'result': {
                'output': [{
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': self.text}],
                }]
            }
        }


def make_png():
    output = BytesIO()
    Image.new('RGB', (2, 3), color=(20, 40, 60)).save(output, format='PNG')
    return output.getvalue()


class ImageGptCheckTests(unittest.TestCase):
    @patch('methods.requests.post', return_value=_GatewayResponse())
    def test_sends_image_as_multimodal_responses_input(self, post):
        image = make_png()
        task = SimpleNamespace(
            id=2567,
            text='Решите задачу на листе.',
            points=10,
            lang='image',
            gpt_model='gpt-vision-test',
        )
        code = SimpleNamespace(
            lang='image',
            code=create_image_submission('answer.png', image, max_bytes=1024),
            check_points=0,
            check_state=None,
            check_comments=None,
            gpt_llm_probability=None,
        )

        check_task_with_gpt(task, code)

        gateway_payload = post.call_args.kwargs['json']
        solution_content = gateway_payload['input'][-1]['content']
        self.assertEqual(gateway_payload['model'], 'gpt-vision-test')
        self.assertEqual(solution_content[0]['type'], 'input_text')
        self.assertEqual(solution_content[1]['type'], 'input_image')
        self.assertTrue(solution_content[1]['image_url'].startswith('data:image/png;base64,'))
        self.assertEqual(solution_content[1]['detail'], 'high')
        self.assertEqual(code.check_points, 10)
        self.assertEqual(code.check_state, 'done')
        self.assertEqual(code.check_comments, 'Решение верное.')

    @patch(
        'methods.requests.post',
        return_value=_GatewayResponse('0\nИзображение не содержит решения.'),
    )
    def test_preserves_zero_points_from_image_gpt(self, post):
        task = SimpleNamespace(
            id=2567,
            text='Решите задачу на листе.',
            points=10,
            lang='image',
            gpt_model='gpt-vision-test',
        )
        code = SimpleNamespace(
            lang='image',
            code=create_image_submission(
                'answer.png',
                make_png(),
                max_bytes=4096,
            ),
            check_points=None,
            check_state=None,
            check_comments=None,
            gpt_llm_probability=None,
        )

        check_task_with_gpt(task, code)

        self.assertEqual(code.check_points, 0)
        self.assertEqual(code.check_state, 'partially done')
        self.assertEqual(
            code.check_comments,
            'Изображение не содержит решения.',
        )


if __name__ == '__main__':
    unittest.main()
