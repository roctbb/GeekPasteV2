import base64
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
import pytest

from notebook_submission import NotebookSubmissionError, prepare_notebook_submission


def png():
    buffer = BytesIO()
    Image.new('RGB', (3, 2), color=(20, 40, 60)).save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


def notebook(*cells, **extra):
    return json.dumps({'nbformat': 4, 'nbformat_minor': 5, 'cells': list(cells), **extra})


def cell(source, kind='code', **extra):
    return {'cell_type': kind, 'source': source, **extra}


def test_markdown_attachments_and_plots_are_images_not_base64_text():
    encoded = png()
    raw = notebook(
        cell(['Explanation\n', '![figure](attachment:figure.png)'], 'markdown',
             attachments={'figure.png': {'image/png': encoded}},
             metadata={'unused': 'do not send'}),
        cell(['x = 13\n', 'print(x)'], execution_count=4, outputs=[
            {'output_type': 'stream', 'name': 'stdout', 'text': ['13\n']},
            {'output_type': 'display_data', 'data': {
                'image/png': encoded, 'text/plain': ['<Figure>'],
                'text/html': '<script>huge duplicate html</script>',
            }},
        ]),
        metadata={'widgets': {'large_state': 'do not send'}},
    )
    result = prepare_notebook_submission(raw)
    evidence = json.loads(result['evidence'])
    assert encoded not in result['evidence']
    assert 'large_state' not in result['evidence']
    assert 'huge duplicate html' not in result['evidence']
    assert evidence['cells'][1]['source'] == 'x = 13\nprint(x)'
    assert evidence['cells'][1]['outputs'][0]['text'] == '13\n'
    assert evidence['cells'][1]['execution_count'] == 4
    assert evidence['cells'][0]['attachments'][0]['image_id'] == 'image_1'
    assert evidence['cells'][1]['outputs'][1]['image_id'] == 'image_1'
    assert len(result['images']) == 1
    assert result['images'][0]['data_url'] == 'data:image/png;base64,' + encoded


def test_cleared_outputs_still_extract_markdown_attachments():
    encoded = png()
    result = prepare_notebook_submission(notebook(
        cell('![figure](attachment:figure.png)', 'markdown',
             attachments={'figure.png': {'image/png': encoded}}),
        cell('print(1)', execution_count=None, outputs=[]),
    ))
    assert encoded not in result['evidence']
    assert len(result['images']) == 1
    assert json.loads(result['evidence'])['cells'][1]['outputs'] == []


def test_inline_data_images_do_not_remain_in_markdown_or_html_output():
    encoded = png()
    result = prepare_notebook_submission(notebook(
        cell('![plot](data:image/png;base64,' + encoded + ')', 'markdown'),
        cell('show()', outputs=[{'output_type': 'display_data', 'data': {
            'text/html': '<p>answer 13</p><img src="data:image/png;base64,' + encoded + '">'
        }}]),
    ))
    assert encoded not in result['evidence']
    assert 'answer 13' in result['evidence']
    assert len(result['images']) == 1


def test_streams_errors_and_json_outputs_are_kept_without_executing_code():
    result = prepare_notebook_submission(notebook(cell('raise ValueError()', outputs=[
        {'output_type': 'error', 'ename': 'ValueError', 'evalue': 'bad input',
         'traceback': ['cell 1', 'ValueError: bad input']},
        {'output_type': 'execute_result', 'data': {'application/json': {'count': 13}}},
    ])))
    assert 'ValueError: bad input' in result['evidence']
    assert 'count' in result['evidence']
    assert 'код не запускался' in result['evidence']


def test_long_outputs_are_explicitly_shortened_but_code_is_not():
    source = 'print("output")\n'
    output = 'START' + 'x' * 20000 + 'END'
    result = prepare_notebook_submission(notebook(cell(source, outputs=[
        {'output_type': 'stream', 'text': output},
    ])))
    evidence = json.loads(result['evidence'])
    saved = evidence['cells'][0]
    assert saved['source'] == source
    assert saved['outputs'][0]['text'].startswith('START')
    assert saved['outputs'][0]['text'].endswith('END')
    assert 'Вывод сокращён' in saved['outputs'][0]['text']
    assert evidence['shortened_outputs'] == 1
    with patch('notebook_submission.MAX_SOURCE_CHARS', 2):
        with pytest.raises(NotebookSubmissionError, match='Код не был обрезан'):
            prepare_notebook_submission(notebook(cell(source)))


@pytest.mark.parametrize('raw', ['not json', '[]', '{}', '{"cells": [null]}',
                                '{"cells":[{"cell_type":"code","source":123}]}'])
def test_bad_notebooks_have_a_clear_error(raw):
    with pytest.raises(NotebookSubmissionError):
        prepare_notebook_submission(raw)


def test_notebook_grading_sends_images_and_cleared_output_rules_in_correct_roles():
    from grading_prompts import COURSE_RUBRIC_PREFIX
    from methods import check_task_with_gpt
    encoded = png()
    raw = notebook(cell('![figure](attachment:figure.png)', 'markdown',
                        attachments={'figure.png': {'image/png': encoded}}),
                   cell('print(13)', outputs=[]))
    task = SimpleNamespace(id=99999, points=10, lang='ipynb', gpt_model='test-model',
                           text=COURSE_RUBRIC_PREFIX + 'Два независимых критерия.')
    code = SimpleNamespace(id='TEST', user_id=1, task_id=99999, lang='ipynb', code=raw,
                           check_points=0, check_comments=None, check_state=None,
                           gpt_llm_probability=None)
    with patch('methods.generate_text', return_value='10\nВерно.') as generate, \
         patch('methods.analyze_code_for_ai_usage', return_value={'suspicious': False}), \
         patch('methods.db.session', Mock()):
        check_task_with_gpt(task, code)
    messages = generate.call_args.args[0]
    assert 'Вывод ячеек мог быть очищен' in messages[0]['content']
    assert encoded not in messages[0]['content']
    content = messages[-1]['content']
    assert content[0]['type'] == 'input_text'
    assert encoded not in content[0]['text']
    assert any(p['type'] == 'input_image' and p['image_url'].endswith(encoded) for p in content)
    assert code.check_points == 10 and code.check_state == 'done'
    assert code.code == raw


def test_invalid_notebook_never_reaches_the_ai_provider():
    from methods import check_task_with_gpt
    task = SimpleNamespace(id=99999)
    code = SimpleNamespace(lang='ipynb', code='not json', check_points=0,
                           check_comments=None, check_state=None)
    with patch('methods.generate_text') as generate:
        check_task_with_gpt(task, code)
    generate.assert_not_called()
    assert code.check_state == 'execution error'
    assert 'JSON тетрадки' in code.check_comments
