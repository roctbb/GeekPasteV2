import base64
import binascii
from io import BytesIO
import json
import os
import warnings

from PIL import Image, UnidentifiedImageError


IMAGE_SUBMISSION_VERSION = 1
SUPPORTED_IMAGE_MIME_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')
MAX_DECODED_IMAGE_PIXELS = 24_000_000
MAX_IMAGE_SIDE = 12_000
PIL_FORMAT_MIME_TYPES = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'WEBP': 'image/webp',
    'GIF': 'image/gif',
}


class ImageSubmissionError(ValueError):
    pass


def detect_image_mime_type(data):
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if len(data) >= 12 and data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    return None


def _safe_filename(filename, mime_type):
    fallback_extensions = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
        'image/gif': '.gif',
    }
    name = os.path.basename((filename or '').replace('\\', '/')).strip()
    name = ''.join(char for char in name if char.isprintable() and char not in '/\\')
    if not name:
        return 'solution' + fallback_extensions[mime_type]
    return name[:255]


def _inspect_image(data, expected_mime_type):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)

            with Image.open(BytesIO(data)) as image:
                mime_type = PIL_FORMAT_MIME_TYPES.get(image.format)
                width, height = image.size

                if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
                    raise ImageSubmissionError(
                        'Поддерживаются изображения JPEG, PNG, WebP и GIF.'
                    )
                if mime_type != expected_mime_type:
                    raise ImageSubmissionError(
                        'Содержимое изображения не соответствует его типу.'
                    )
                if width <= 0 or height <= 0:
                    raise ImageSubmissionError(
                        'Изображение должно иметь ненулевые размеры.'
                    )
                if (
                    width > MAX_IMAGE_SIDE
                    or height > MAX_IMAGE_SIDE
                    or width * height > MAX_DECODED_IMAGE_PIXELS
                ):
                    raise ImageSubmissionError(
                        'Изображение имеет слишком большие размеры.'
                    )
                if getattr(image, 'n_frames', 1) != 1:
                    raise ImageSubmissionError(
                        'Анимированные изображения не поддерживаются.'
                    )

                image.verify()

            # verify() checks the container structure without decoding pixels.
            # Reopen and load it to ensure Pillow can decode the actual image.
            with Image.open(BytesIO(data)) as decoded_image:
                decoded_mime_type = PIL_FORMAT_MIME_TYPES.get(decoded_image.format)
                if decoded_mime_type != expected_mime_type:
                    raise ImageSubmissionError(
                        'Содержимое изображения не соответствует его типу.'
                    )
                if decoded_image.size != (width, height):
                    raise ImageSubmissionError(
                        'Повреждены данные изображения.'
                    )
                if getattr(decoded_image, 'n_frames', 1) != 1:
                    raise ImageSubmissionError(
                        'Анимированные изображения не поддерживаются.'
                    )
                decoded_image.load()
    except ImageSubmissionError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageSubmissionError(
            'Изображение имеет слишком большие размеры.'
        ) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageSubmissionError(
            'Не удалось прочитать изображение.'
        ) from exc

    return {
        'mime_type': expected_mime_type,
        'width': width,
        'height': height,
    }


def create_image_submission(filename, data, max_bytes):
    if not data:
        raise ImageSubmissionError('Выберите непустой файл изображения.')
    if len(data) > max_bytes:
        max_megabytes = max_bytes / (1024 * 1024)
        raise ImageSubmissionError(f'Изображение слишком большое. Максимум: {max_megabytes:g} МБ.')

    mime_type = detect_image_mime_type(data)
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ImageSubmissionError('Поддерживаются изображения JPEG, PNG, WebP и GIF.')

    _inspect_image(data, mime_type)

    return json.dumps({
        'version': IMAGE_SUBMISSION_VERSION,
        'filename': _safe_filename(filename, mime_type),
        'mime_type': mime_type,
        'data': base64.b64encode(data).decode('ascii'),
    }, ensure_ascii=False, separators=(',', ':'))


def parse_image_submission(raw_value, max_bytes):
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError) as exc:
        raise ImageSubmissionError('Повреждены данные изображения.') from exc

    if not isinstance(payload, dict) or payload.get('version') != IMAGE_SUBMISSION_VERSION:
        raise ImageSubmissionError('Неизвестный формат данных изображения.')

    mime_type = payload.get('mime_type')
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ImageSubmissionError('Неподдерживаемый тип изображения.')

    try:
        data = base64.b64decode(payload.get('data', ''), validate=True)
    except (TypeError, ValueError, binascii.Error) as exc:
        raise ImageSubmissionError('Повреждены данные изображения.') from exc

    if not data or detect_image_mime_type(data) != mime_type:
        raise ImageSubmissionError('Содержимое изображения не соответствует его типу.')
    if len(data) > max_bytes:
        max_megabytes = max_bytes / (1024 * 1024)
        raise ImageSubmissionError(
            f'Изображение слишком большое. Максимум: {max_megabytes:g} МБ.'
        )

    metadata = _inspect_image(data, mime_type)

    return {
        'filename': _safe_filename(payload.get('filename'), mime_type),
        'mime_type': mime_type,
        'width': metadata['width'],
        'height': metadata['height'],
        'data': data,
        'data_url': f"data:{mime_type};base64,{payload['data']}",
    }
