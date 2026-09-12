import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from methods import check_task_with_gpt


class _GatewayResponse:
    content = b''

    def json(self):
        return {
            'result': {
                'output': [{
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': '15\nВсе уровни пройдены.'}],
                }]
            }
        }


def make_task(task_id=2582):
    return SimpleNamespace(
        id=task_id,
        text='Проверьте JSON-экспорт nandgame.',
        points=15,
        lang='python',
        gpt_model='gpt-test',
    )


def make_code(value):
    return SimpleNamespace(
        lang='python',
        code=value,
        check_points=None,
        check_state=None,
        check_comments=None,
        gpt_llm_probability=None,
        user_id=None,
        task_id=2582,
    )


class NandgameJsonGptCheckTests(unittest.TestCase):
    @patch('methods.requests.post')
    def test_rejects_fences_explanations_arrays_and_malformed_json_without_gpt(self, post):
        for task_id in (2582, 2586, 2589, 2590, 2592):
            for value in (
                '```json\n{}\n```',
                '{}\nВсе готово.',
                '[]',
                '{not json',
            ):
                with self.subTest(task_id=task_id, value=value):
                    code = make_code(value)
                    code.task_id = task_id
                    check_task_with_gpt(make_task(task_id), code)
                    self.assertEqual(code.check_points, 1)
                    self.assertEqual(code.check_state, 'partially done')
                    self.assertIn('только один JSON-объект', code.check_comments)
        post.assert_not_called()

    @patch('methods.analyze_code_for_ai_usage', return_value={'suspicious': False})
    @patch('methods.requests.post', return_value=_GatewayResponse())
    def test_sends_raw_json_to_gpt_without_python_requirement(self, post, _analyze):
        export = {'NandGame:Levels': ['ARITHMETICS']}
        code = make_code(json.dumps(export))
        check_task_with_gpt(make_task(), code)

        payload = post.call_args.kwargs['json']
        system_prompt = payload['input'][0]['content']
        self.assertIn('JSON-экспорт', system_prompt)
        self.assertNotIn('Код должен быть написан на языке python', system_prompt)
        self.assertEqual(code.check_points, 15)
        self.assertEqual(code.check_state, 'done')


if __name__ == '__main__':
    unittest.main()
