import os
from dotenv import load_dotenv

load_dotenv()

def env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

LANGS = ['cpp', 'python', 'java', 'cs', 'html', 'css', 'js', 'json', 'xml', 'swift', 'php', 'sql']

# Файлы и папки, которые не несут полезного кода ученика и только шумят
# в просмотре, сравнении решений и GPT-проверке архивов.
IGNORED_PARTS = [
    # IDE/editor metadata
    '.idea', '.qtcreator', '.vscode', '.vs',

    # VCS/service metadata
    '.git', '.github', '.gitignore', '.gitattributes',

    # Python caches/environments
    'venv', '.venv', 'env', '.env', '__pycache__', 'pycache',
    '.mypy_cache', '.pytest_cache', '.ruff_cache', '.tox', '.nox',
    '.coverage', 'htmlcov',

    # Dependencies/vendor dumps
    'node_modules', 'vendor',

    # Build/output folders common for C++, Qt/CMake, Python and other tools
    'build', 'cmake-build-debug', 'cmake-build-release',
    'cmake-build-relwithdebinfo', 'cmake-build-minsizerel',
    'debug', 'release', 'dist', 'out', 'bin', 'obj', 'target',

    # OS artifacts
    '__MACOSX', '.DS_Store', 'Thumbs.db',
]

IGNORED_FILE_SUFFIXES = [
    # Qt Creator / qmake / CMake user-local files
    '.user', '.user.*',

    # Compiled objects, libraries and binaries
    '.o', '.obj', '.a', '.lib', '.so', '.dylib', '.dll',
    '.exe', '.out', '.app', '.class', '.pyc', '.pyo',

    # Debug/runtime/generated files
    '.ilk', '.pdb', '.idb', '.dSYM', '.gcda', '.gcno',
    '.log', '.tmp', '.temp',
]

APP_URL = os.getenv('APP_URL', 'https://paste.geekclass.ru')
SIMILARITY_LEVEL = int(os.getenv('SIMILARITY_LEVEL', 75))
MAX_SIMILAR_CODES = int(os.getenv('MAX_SIMILAR_CODES', 8))
MAX_SIMILARITY_CODE_SIZE = int(os.getenv('MAX_SIMILARITY_CODE_SIZE', 50000))
CONNECTION_STRING = os.getenv('CONNECTION_STRING', 'postgresql+psycopg2://username:password@localhost:5432/mydatabase')
CELERY_BROKER = os.getenv('CELERY_BROKER', 'redis://localhost:6379/0')
DEBUG = env_bool('DEBUG', False)
PORT = int(os.getenv('PORT', 8084))
SECRET = os.getenv('SECRET', 'key')
GEEKCLASS_HOST = os.getenv('GEEKCLASS_HOST', 'https://codingprojects.ru')
JWT_SECRET = os.getenv('JWT_SECRET')
SOLUTIONS_API_KEY = os.getenv('SOLUTIONS_API_KEY')

SUBMIT_URL = GEEKCLASS_HOST + '/api/geekpaste'
AUTH_URL = GEEKCLASS_HOST + '/insider/jwt?redirect_url='
USER_URL = GEEKCLASS_HOST + '/insider/profile/'
TASK_URL = GEEKCLASS_HOST + '/insider/courses/{course_id}/tasks/{task_id}/student/{user_id}'

GPT_MODEL = os.getenv('GPT_MODEL', 'gpt-5-mini')
GPT_KEY = os.getenv('GPT_KEY')
GPT_GATEWAY = os.getenv('GPT_GATEWAY', 'https://gpt-gateway.ai.medsenger.ru:4443/v1/responses')
GPT_MAX_OUTPUT_TOKENS = max(16, int(os.getenv('GPT_MAX_OUTPUT_TOKENS', 1024)))

# GPT Rate Limiting
DEFAULT_GPT_RATE_LIMIT = int(os.getenv('DEFAULT_GPT_RATE_LIMIT', 3))  # посылок в час
REDIS_URL = os.getenv('REDIS_URL', CELERY_BROKER)
