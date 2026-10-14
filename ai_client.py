"""One Responses transport for native submissions and the external grading API."""
import requests

from ai_settings import AISettingsError, load_ai_settings


class AIRequestError(RuntimeError):
    """Safe error text: never include upstream bodies, URLs or credentials."""


class _ConfiguredAuth(requests.auth.AuthBase):
    def __call__(self, request):
        # Prevent Requests from replacing the chosen Authorization with .netrc.
        return request


def _response_text(data, *, gateway):
    if not isinstance(data, dict) or data.get('error'):
        raise AIRequestError('Сервис ИИ вернул ошибку.')
    if gateway:
        data = data.get('result')
    if not isinstance(data, dict) or data.get('error'):
        raise AIRequestError('Сервис ИИ вернул некорректный ответ.')
    if data.get('status') not in (None, 'completed') or data.get('incomplete_details'):
        raise AIRequestError('Ответ ИИ не завершён. Проверьте лимит токенов и модель.')
    output = data.get('output')
    if not isinstance(output, list):
        raise AIRequestError('В ответе ИИ нет текста проверки.')
    parts = []
    for item in output:
        if not isinstance(item, dict) or item.get('type') != 'message':
            continue
        if item.get('status') not in (None, 'completed'):
            raise AIRequestError('Сообщение ИИ не завершено.')
        content = item.get('content')
        if not isinstance(content, list):
            raise AIRequestError('Некорректный формат сообщения ИИ.')
        for part in content:
            if not isinstance(part, dict):
                raise AIRequestError('Некорректный формат сообщения ИИ.')
            if part.get('type') == 'refusal':
                raise AIRequestError('ИИ отказался проверить решение.')
            if part.get('type') == 'output_text' or (gateway and 'type' not in part):
                text = part.get('text')
                if not isinstance(text, str):
                    raise AIRequestError('Некорректный текст ответа ИИ.')
                parts.append(text)
    text = '\n'.join(parts).strip()
    if not text:
        raise AIRequestError('В ответе ИИ нет текста проверки.')
    return text


def generate_text(input_messages, *, model=None):
    try:
        settings = load_ai_settings()
    except AISettingsError:
        raise
    except Exception:
        raise AISettingsError('Не удалось загрузить настройки ИИ из базы данных.') from None
    provider = settings['provider']
    key = settings[f'{provider}_key']
    if not key:
        raise AISettingsError('Не задан ключ выбранного API. Обратитесь к администратору.')
    payload = {'model': model or settings['model'], 'input': input_messages}
    headers = {}
    if provider == 'gateway':
        payload.update(token=key, params={'max_output_tokens': settings['max_output_tokens']})
    else:
        headers['Authorization'] = f'Bearer {key}'
        payload.update(max_output_tokens=settings['max_output_tokens'], store=False)
    proxy = settings[f'{provider}_proxy']
    try:
        response = requests.post(
            settings[f'{provider}_url'], json=payload, headers=headers,
            timeout=settings['timeout'], allow_redirects=False,
            proxies={'http': proxy, 'https': proxy},
            auth=_ConfiguredAuth(),
        )
    except requests.Timeout:
        raise requests.Timeout('Сервис ИИ не ответил за отведённое время.') from None
    except requests.ConnectionError:
        raise requests.ConnectionError('Не удалось подключиться к сервису ИИ.') from None
    except Exception:
        raise AIRequestError('Не удалось отправить запрос к сервису ИИ.') from None
    if not 200 <= response.status_code < 300:
        raise AIRequestError(f'Сервис ИИ вернул HTTP {response.status_code}. Проверьте настройки подключения.')
    try:
        data = response.json()
    except (ValueError, TypeError):
        raise AIRequestError('Сервис ИИ вернул ответ в неверном формате.') from None
    return _response_text(data, gateway=provider == 'gateway')
