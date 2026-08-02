import base64
import json
import unittest

from image_submission import (
    ImageSubmissionError,
    create_image_submission,
    detect_image_mime_type,
    parse_image_submission,
)


class ImageSubmissionTests(unittest.TestCase):
    def test_detects_supported_image_types_by_content(self):
        self.assertEqual(detect_image_mime_type(b'\xff\xd8\xff\xe0data'), 'image/jpeg')
        self.assertEqual(detect_image_mime_type(b'\x89PNG\r\n\x1a\ndata'), 'image/png')
        self.assertEqual(detect_image_mime_type(b'RIFF1234WEBPdata'), 'image/webp')
        self.assertEqual(detect_image_mime_type(b'GIF89adata'), 'image/gif')

    def test_round_trip_uses_detected_type_and_safe_filename(self):
        image = b'\x89PNG\r\n\x1a\nimage-data'

        raw_value = create_image_submission('../solution.png', image, max_bytes=1024)
        parsed = parse_image_submission(raw_value)

        self.assertEqual(parsed['filename'], 'solution.png')
        self.assertEqual(parsed['mime_type'], 'image/png')
        self.assertEqual(parsed['data'], image)
        self.assertEqual(parsed['data_url'], 'data:image/png;base64,' + base64.b64encode(image).decode('ascii'))

    def test_rejects_non_image_and_oversized_files(self):
        with self.assertRaisesRegex(ImageSubmissionError, 'JPEG'):
            create_image_submission('answer.txt', b'not an image', max_bytes=1024)

        with self.assertRaisesRegex(ImageSubmissionError, 'Максимум'):
            create_image_submission('answer.jpg', b'\xff\xd8\xff' + b'x' * 20, max_bytes=10)

    def test_rejects_payload_with_mime_mismatch(self):
        raw_value = json.dumps({
            'version': 1,
            'filename': 'answer.png',
            'mime_type': 'image/png',
            'data': base64.b64encode(b'\xff\xd8\xffimage').decode('ascii'),
        })

        with self.assertRaisesRegex(ImageSubmissionError, 'не соответствует'):
            parse_image_submission(raw_value)


if __name__ == '__main__':
    unittest.main()
