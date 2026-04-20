import os
from dotenv import load_dotenv

load_dotenv()

def env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

LANGS = ['cpp', 'python', 'java', 'cs', 'html', 'css', 'js', 'json', 'xml', 'swift', 'php', 'sql']
IGNORED_PARTS = ['.idea', 'venv', 'pycache', '.replit', 'node_modules', 'vendor', '.git', 'build', '.pro.user', '__MACOSX', '.DS_Store']

APP_URL = os.getenv('APP_URL', 'https://paste.geekclass.ru')
SIMILARITY_LEVEL = int(os.getenv('SIMILARITY_LEVEL', 75))
MAX_SIMILAR_CODES = int(os.getenv('MAX_SIMILAR_CODES', 8))
CONNECTION_STRING = os.getenv('CONNECTION_STRING', 'postgresql+psycopg2://username:password@localhost:5432/mydatabase')
CELERY_BROKER = os.getenv('CELERY_BROKER', 'redis://localhost:6379/0')
DEBUG = env_bool('DEBUG', False)
PORT = int(os.getenv('PORT', 8084))
SECRET = os.getenv('SECRET', 'key')
GEEKCLASS_HOST = os.getenv('GEEKCLASS_HOST', 'https://codingprojects.ru')
JWT_SECRET = os.getenv('JWT_SECRET')

SUBMIT_URL = GEEKCLASS_HOST + '/api/geekpaste'
AUTH_URL = GEEKCLASS_HOST + '/insider/jwt?redirect_url='
USER_URL = GEEKCLASS_HOST + '/insider/profile/'
TASK_URL = GEEKCLASS_HOST + '/insider/courses/{course_id}/tasks/{task_id}/student/{user_id}'

GPT_MODEL = os.getenv('GPT_MODEL', 'gpt-5-mini')
GPT_KEY = os.getenv('GPT_KEY')
GPT_GATEWAY = os.getenv('GPT_GATEWAY', 'https://gpt-gateway.ai.medsenger.ru:4443/v1/responses')

# GPT Rate Limiting
DEFAULT_GPT_RATE_LIMIT = int(os.getenv('DEFAULT_GPT_RATE_LIMIT', 3))  # посылок в час
REDIS_URL = os.getenv('REDIS_URL', CELERY_BROKER)
