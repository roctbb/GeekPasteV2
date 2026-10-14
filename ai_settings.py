"""Shared, encrypted AI configuration for web processes and Celery workers."""
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, has_app_context
from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import config
from models import AISettings, db


class AISettingsError(ValueError):
    """A configuration error safe to display without credentials."""


PUBLIC_FIELDS = ('provider', 'model', 'max_output_tokens', 'timeout',
                 'gateway_url', 'openai_url')
SECRET_FIELDS = ('gateway_key', 'openai_key', 'gateway_proxy', 'openai_proxy')


def environment_settings():
    return {
        'provider': config.AI_PROVIDER,
        'model': config.GPT_MODEL,
        'max_output_tokens': config.GPT_MAX_OUTPUT_TOKENS,
        'timeout': config.AI_TIMEOUT,
        'gateway_url': config.GPT_GATEWAY,
        'gateway_key': config.GPT_KEY or '',
        'gateway_proxy': config.GPT_PROXY,
        'openai_url': config.OPENAI_RESPONSES_URL,
        'openai_key': config.OPENAI_API_KEY,
        'openai_proxy': config.OPENAI_PROXY,
    }


def _cipher():
    key = config.AI_SETTINGS_ENCRYPTION_KEY
    if not key:
        secret = str(current_app.config.get('SECRET_KEY') or '')
        if len(secret) < 32:
            raise AISettingsError(
                'Для сохранения настроек задайте AI_SETTINGS_ENCRYPTION_KEY '
                'или постоянный SECRET длиной не менее 32 символов на сервере.')
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    try:
        return Fernet(key)
    except (ValueError, TypeError):
        raise AISettingsError('Некорректный AI_SETTINGS_ENCRYPTION_KEY на сервере.') from None


def _decode(value):
    if not value:
        return {}
    try:
        data = json.loads(_cipher().decrypt(value.encode()))
        if not isinstance(data, dict) or set(data) - set(PUBLIC_FIELDS + SECRET_FIELDS):
            raise ValueError
        return data
    except (InvalidToken, ValueError, TypeError, UnicodeError):
        raise AISettingsError(
            'Не удалось прочитать настройки ИИ. Проверьте ключ шифрования сервера.') from None


def _overrides():
    if not has_app_context():
        return {}, False
    # Use a fresh connection: grading may already have an ORM transaction open.
    # No process cache, so long-lived workers see changes on their next request.
    with db.engine.connect() as connection:
        if not inspect(connection).has_table(AISettings.__tablename__):
            return {}, False
        value = connection.execute(select(AISettings.encrypted_config).where(
            AISettings.id == 1)).scalar_one_or_none()
    return _decode(value), True


def load_ai_settings():
    overrides, _ = _overrides()
    return validate_settings(environment_settings() | overrides)


def settings_view():
    overrides, available = _overrides()
    values = environment_settings() | overrides
    # An old environment URL may embed credentials. Never echo it into HTML.
    for key in ('gateway_url', 'openai_url'):
        try:
            _url(values[key])
        except AISettingsError:
            values[key] = ''
    return {
        'fields': {key: values[key] for key in PUBLIC_FIELDS},
        'secrets': {key: {
            'configured': bool(values[key]),
            'source': 'database' if key in overrides else 'environment',
        } for key in SECRET_FIELDS},
        'overridden': bool(overrides),
        'available': available,
    }


def _url(value, *, proxy=False):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        raise AISettingsError('Некорректный адрес прокси.' if proxy else 'Некорректный URL API.')
    if proxy and not value:
        return value
    try:
        parsed = urlsplit(value)
        port = parsed.port
        allowed = {'http', 'https', 'socks5', 'socks5h'} if proxy else {'http', 'https'}
        if (parsed.scheme not in allowed or not parsed.hostname or
                parsed.query or parsed.fragment or '\\' in value or
                (port is not None and not 1 <= port <= 65535) or
                (proxy and parsed.path not in ('', '/')) or
                (not proxy and (parsed.username is not None or parsed.password is not None))):
            raise ValueError
    except ValueError:
        raise AISettingsError(
            'Прокси: укажите HTTP(S) или SOCKS5 URL без пути и параметров.' if proxy else
            'Укажите полный HTTP(S) URL Responses API без логина, пароля и параметров.') from None
    return value


def validate_settings(values):
    values = dict(values)
    if values.get('provider') not in ('gateway', 'openai'):
        raise AISettingsError('Выберите шлюз или OpenAI API.')
    if not isinstance(values.get('model'), str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}', values['model']):
        raise AISettingsError('Укажите корректное имя модели.')
    for key, low, high, label in (
        ('max_output_tokens', 16, 128000, 'Лимит токенов'),
        ('timeout', 1, 600, 'Таймаут'),
    ):
        try:
            value = int(values[key])
            if not low <= value <= high:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise AISettingsError(f'{label}: целое число от {low} до {high}.') from None
        values[key] = value
    for provider in ('gateway', 'openai'):
        values[f'{provider}_url'] = _url(values.get(f'{provider}_url'))
        values[f'{provider}_proxy'] = _url(values.get(f'{provider}_proxy'), proxy=True)
        key = values.get(f'{provider}_key')
        if not isinstance(key, str) or len(key) > 4096 or any(c.isspace() for c in key):
            raise AISettingsError('Ключ API должен быть без пробелов и переносов строк.')
    return values


def save_ai_settings(form, user_id):
    cipher = _cipher()
    table = AISettings.__table__
    with db.engine.begin() as connection:
        if not inspect(connection).has_table(table.name):
            raise AISettingsError('Перед сохранением выполните миграции базы данных.')
        insert = sqlite_insert if connection.dialect.name == 'sqlite' else pg_insert
        connection.execute(insert(table).values(id=1, encrypted_config='').on_conflict_do_nothing())
        previous = connection.execute(select(table.c.encrypted_config).where(
            table.c.id == 1).with_for_update()).scalar_one()
        overrides = _decode(previous)
        for key in PUBLIC_FIELDS:
            overrides[key] = (form.get(key) or '').strip()
        for key in SECRET_FIELDS:
            action = form.get(f'{key}_action', 'keep')
            value = (form.get(key) or '').strip()
            if action == 'inherit':
                overrides.pop(key, None)
            elif action == 'clear':
                overrides[key] = ''
            elif action == 'keep':
                # Entering a value replaces it; an empty input keeps the old one.
                if value:
                    overrides[key] = value
            else:
                raise AISettingsError('Некорректное действие для ключа или прокси.')
        values = validate_settings(environment_settings() | overrides)
        if not values[f"{values['provider']}_key"]:
            raise AISettingsError('Укажите ключ API для выбранного подключения.')
        for key in PUBLIC_FIELDS:
            overrides[key] = values[key]
        encrypted = cipher.encrypt(json.dumps(overrides).encode()).decode()
        connection.execute(table.update().where(table.c.id == 1).values(
            encrypted_config=encrypted, updated_by=user_id,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None)))


def reset_ai_settings():
    # Reset also works when the encryption key has been lost.
    with db.engine.begin() as connection:
        if inspect(connection).has_table(AISettings.__tablename__):
            connection.execute(AISettings.__table__.delete().where(AISettings.id == 1))
