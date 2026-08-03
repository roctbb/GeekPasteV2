import base64
from io import BytesIO
import json
import unittest
from unittest.mock import patch

from PIL import Image

from image_submission import (
    ImageSubmissionError,
    create_image_submission,
    detect_image_mime_type,
    parse_image_submission,
)


def make_image(image_format='PNG', size=(2, 3)):
    output = BytesIO()
    Image.new('RGB', size, color=(20, 40, 60)).save(
        output,
        format=image_format,
    )
    return output.getvalue()


class ImageSubmissionTests(unittest.TestCase):
    def test_detects_supported_image_types_by_content(self):
        self.assertEqual(detect_image_mime_type(b'\xff\xd8\xff\xe0data'), 'image/jpeg')
        self.assertEqual(detect_image_mime_type(b'\x89PNG\r\n\x1a\ndata'), 'image/png')
        self.assertEqual(detect_image_mime_type(b'RIFF1234WEBPdata'), 'image/webp')
        self.assertEqual(detect_image_mime_type(b'GIF89adata'), 'image/gif')

    def test_round_trip_uses_detected_type_and_safe_filename(self):
        image = make_image(size=(2, 3))

        raw_value = create_image_submission('../solution.png', image, max_bytes=1024)
        parsed = parse_image_submission(raw_value, max_bytes=1024)

        self.assertEqual(parsed['filename'], 'solution.png')
        self.assertEqual(parsed['mime_type'], 'image/png')
        self.assertEqual(parsed['width'], 2)
        self.assertEqual(parsed['height'], 3)
        self.assertEqual(parsed['data'], image)
        self.assertEqual(parsed['data_url'], 'data:image/png;base64,' + base64.b64encode(image).decode('ascii'))

    def test_preserves_all_supported_pillow_formats(self):
        for image_format, mime_type in (
            ('JPEG', 'image/jpeg'),
            ('PNG', 'image/png'),
            ('WEBP', 'image/webp'),
            ('GIF', 'image/gif'),
        ):
            with self.subTest(image_format=image_format):
                image = make_image(image_format=image_format)
                raw_value = create_image_submission(
                    f'answer.{image_format.lower()}',
                    image,
                    max_bytes=4096,
                )
                parsed = parse_image_submission(raw_value, max_bytes=4096)

                self.assertEqual(parsed['mime_type'], mime_type)
                self.assertEqual((parsed['width'], parsed['height']), (2, 3))

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
            'data': base64.b64encode(make_image('JPEG')).decode('ascii'),
        })

        with self.assertRaisesRegex(ImageSubmissionError, 'не соответствует'):
            parse_image_submission(raw_value, max_bytes=4096)

    def test_rejects_fake_image_with_matching_magic_bytes(self):
        fake_image = b'\x89PNG\r\n\x1a\nnot-a-real-image'

        with self.assertRaisesRegex(ImageSubmissionError, 'прочитать'):
            create_image_submission(
                'answer.png',
                fake_image,
                max_bytes=4096,
            )

        raw_value = json.dumps({
            'version': 1,
            'filename': 'answer.png',
            'mime_type': 'image/png',
            'data': base64.b64encode(fake_image).decode('ascii'),
        })

        with self.assertRaisesRegex(ImageSubmissionError, 'прочитать'):
            parse_image_submission(raw_value, max_bytes=4096)

    def test_revalidates_decoded_payload_size(self):
        image = make_image()
        raw_value = create_image_submission(
            'answer.png',
            image,
            max_bytes=len(image),
        )

        with self.assertRaisesRegex(ImageSubmissionError, 'Максимум'):
            parse_image_submission(raw_value, max_bytes=len(image) - 1)

    def test_rejects_images_with_unsafe_dimensions(self):
        image = make_image(size=(2, 2))
        raw_value = create_image_submission(
            'answer.png',
            image,
            max_bytes=4096,
        )

        with patch.object(Image, 'MAX_IMAGE_PIXELS', 1):
            with self.assertRaisesRegex(ImageSubmissionError, 'слишком большие размеры'):
                parse_image_submission(raw_value, max_bytes=4096)

    def test_applies_a_stricter_decoded_pixel_budget_than_pillow_default(self):
        image = make_image(size=(20, 20))
        raw_value = create_image_submission(
            'answer.png',
            image,
            max_bytes=4096,
        )

        with patch('image_submission.MAX_DECODED_IMAGE_PIXELS', 399):
            with self.assertRaisesRegex(ImageSubmissionError, 'слишком большие размеры'):
                parse_image_submission(raw_value, max_bytes=4096)

    def test_rejects_animated_images(self):
        output = BytesIO()
        first = Image.new('RGB', (2, 2), color=(20, 40, 60))
        second = Image.new('RGB', (2, 2), color=(60, 40, 20))
        first.save(
            output,
            format='GIF',
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0,
        )

        with self.assertRaisesRegex(ImageSubmissionError, 'Анимированные'):
            create_image_submission(
                'answer.gif',
                output.getvalue(),
                max_bytes=4096,
            )


if __name__ == '__main__':
    unittest.main()
