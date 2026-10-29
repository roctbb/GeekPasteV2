import io
import json
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from grading_prompts import COURSE_RUBRIC_PREFIX
from spreadsheet_submission import (extract_xlsx_evidence, create_spreadsheet_submission,
                                    parse_spreadsheet_submission)


def zip_bytes(parts):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return output.getvalue()


def workbook_bytes(*, chart=True, extra_parts=None, cell_xml=None):
    # Small OOXML fixtures exercise the actual archive/relationship reader.
    parts = {
        '_rels/.rels': '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
        </Relationships>''',
        'xl/workbook.xml': '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Замеры" sheetId="1" r:id="r1"/></sheets></workbook>''',
        'xl/_rels/workbook.xml.rels': '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
          <Relationship Id="r2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
        </Relationships>''',
        'xl/sharedStrings.xml': '''<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Медленный алгоритм</t></si></sst>''',
        'xl/worksheets/sheet1.xml': '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetData><row r="1">'''
        + (cell_xml or '''<c r="A1" t="s"><v>0</v></c><c r="B1"><v>2000</v></c>
          <c r="C1"><f>B1*4</f><v>8000</v></c><c r="D1" t="inlineStr"><is><t>O(n²)</t></is></c>
          <c r="E1" s="2"/><c r="F1"><f>C1*2</f></c>''')
        + '</row></sheetData>' + ('<drawing r:id="d1"/>' if chart else '') + '</worksheet>',
        'xl/worksheets/_rels/sheet1.xml.rels': '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="d1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>''',
        'xl/drawings/drawing1.xml': '''<drawing xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><c:chart r:id="c1"/></drawing>''',
        'xl/drawings/_rels/drawing1.xml.rels': '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="c1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/></Relationships>''',
        'xl/charts/chart1.xml': '''<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart><c:plotArea><c:lineChart><c:ser><c:tx><c:v>Slow</c:v></c:tx><c:cat><c:numRef><c:f>'Замеры'!$B$1</c:f></c:numRef></c:cat><c:val><c:numRef><c:f>'Замеры'!$C$1</c:f></c:numRef></c:val></c:ser></c:lineChart></c:plotArea></c:chart></c:chartSpace>''',
    }
    parts.update(extra_parts or {})
    return zip_bytes(parts)


class SpreadsheetSubmissionTests(unittest.TestCase):
    def test_direct_xlsx_preserves_original_bytes_and_sanitizes_filename(self):
        data = workbook_bytes()
        raw = create_spreadsheet_submission('../report.xlsx', data, 1024 * 1024)
        parsed = parse_spreadsheet_submission(raw, 1024 * 1024)
        self.assertEqual(parsed['filename'], 'report.xlsx')
        self.assertEqual(parsed['data'], data)
        self.assertIn('lineChart', parsed['evidence'])

    def test_rejects_wrong_extension_corrupt_or_oversized_direct_upload(self):
        for name, data, limit in [('report.xls', workbook_bytes(), 100000),
                                  ('report.xlsx', b'not excel', 100000),
                                  ('report.xlsx', workbook_bytes(), 100)]:
            with self.subTest(name=name, limit=limit), self.assertRaises(ValueError):
                create_spreadsheet_submission(name, data, limit)

    @patch('methods.analyze_code_for_ai_usage')
    @patch('methods.generate_text', return_value='5\nЗамеры и диаграмма: 5/5. Сложность и прогноз: 0/5.')
    def test_direct_xlsx_is_graded_independently_without_code_detection(self, generate, analyze):
        from methods import check_task_with_gpt
        task = SimpleNamespace(id=99999, lang='xlsx', points=10, gpt_model='test-model',
                               text=COURSE_RUBRIC_PREFIX + 'Замеры и диаграмма — 5, сложности и прогноз — 5.')
        code = SimpleNamespace(lang='xlsx', code=create_spreadsheet_submission(
            'report.xlsx', workbook_bytes(), 1024 * 1024), check_points=0,
            check_comments=None, check_state=None, gpt_llm_probability=None)
        check_task_with_gpt(task, code)
        messages = generate.call_args.args[0]
        self.assertEqual([message['role'] for message in messages], ['system', 'user'])
        self.assertIn('lineChart', json.loads(messages[1]['content'])['student_answer'])
        self.assertNotIn('Если код не запускается', messages[0]['content'])
        self.assertEqual(code.check_points, 5)
        analyze.assert_not_called()

    def test_reads_cells_formulas_and_reachable_native_charts(self):
        data = json.loads(extract_xlsx_evidence(workbook_bytes()))
        cells = {cell['cell']: cell for cell in data['sheets'][0]['cells']}
        self.assertEqual(cells['A1']['value'], 'Медленный алгоритм')
        self.assertEqual(cells['D1']['value'], 'O(n²)')
        self.assertEqual(cells['C1']['formula'], 'B1*4')
        self.assertEqual(cells['C1']['value'], '8000')
        self.assertIsNone(cells['F1']['value'])
        self.assertNotIn('E1', cells)
        self.assertEqual(len(data['charts']), 1)
        self.assertEqual(data['charts'][0]['sheet'], 'Замеры')
        self.assertIn("'Замеры'!$C$1", data['charts'][0]['definition_xml'])

    def test_orphan_chart_parts_are_not_evidence_of_a_chart_on_a_sheet(self):
        data = json.loads(extract_xlsx_evidence(workbook_bytes(chart=False)))
        self.assertEqual(data['charts'], [])

    def test_external_workbook_links_are_not_fetched(self):
        with patch('requests.get') as get:
            data = json.loads(extract_xlsx_evidence(workbook_bytes(extra_parts={
                'xl/externalLinks/externalLink1.xml': '<unused/>',
            })))
        get.assert_not_called()
        self.assertIn('Внешние ссылки не загружались', data['notice'])

    def test_rejects_xml_entities(self):
        book = workbook_bytes(extra_parts={'xl/sharedStrings.xml': '''<!DOCTYPE sst [<!ENTITY bomb "BAD">]><sst><si>&bomb;</si></sst>'''})
        with self.assertRaises(Exception):
            extract_xlsx_evidence(book)

    def test_enforces_uncompressed_and_cell_limits(self):
        with patch('spreadsheet_submission.MAX_XLSX_UNCOMPRESSED_BYTES', 100):
            with self.assertRaisesRegex(ValueError, 'слишком большой'):
                extract_xlsx_evidence(workbook_bytes())
        with patch('spreadsheet_submission.MAX_XLSX_CELLS', 2):
            with self.assertRaisesRegex(ValueError, 'много заполненных'):
                extract_xlsx_evidence(workbook_bytes())

if __name__ == '__main__':
    unittest.main()
