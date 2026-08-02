import base64
import binascii
import json
import os


IMAGE_SUBMISSION_VERSION = 1
SUPPORTED_IMAGE_MIME_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')


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


def create_image_submission(filename, data, max_bytes):
    if not data:
        raise ImageSubmissionError('Выберите непустой файл изображения.')
    if len(data) > max_bytes:
        max_megabytes = max_bytes / (1024 * 1024)
        raise ImageSubmissionError(f'Изображение слишком большое. Максимум: {max_megabytes:g} МБ.')

    mime_type = detect_image_mime_type(data)
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ImageSubmissionError('Поддерживаются изображения JPEG, PNG, WebP и GIF.')

    return json.dumps({
        'version': IMAGE_SUBMISSION_VERSION,
        'filename': _safe_filename(filename, mime_type),
        'mime_type': mime_type,
        'data': base64.b64encode(data).decode('ascii'),
    }, ensure_ascii=False, separators=(',', ':'))


def parse_image_submission(raw_value):
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

    return {
        'filename': _safe_filename(payload.get('filename'), mime_type),
        'mime_type': mime_type,
        'data': data,
        'data_url': f"data:{mime_type};base64,{payload['data']}",
    }
