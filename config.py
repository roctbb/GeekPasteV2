import os
from dotenv import load_dotenv

load_dotenv()

LANGS = ['cpp', 'python', 'java', 'cs', 'html', 'css', 'js', 'json', 'xml', 'swift', 'php']

APP_URL = os.getenv('APP_URL', 'https://paste.geekclass.ru')
SIMILARITY_LEVEL = int(os.getenv('SIMILARITY_LEVEL', 75))
MAX_SIMILAR_CODES = int(os.getenv('MAX_SIMILAR_CODES', 8))
CONNECTION_STRING = os.getenv('CONNECTION_STRING', 'postgresql+psycopg2://username:password@localhost:5432/mydatabase')
CELERY_BROKER = os.getenv('CELERY_BROKER', 'redis://localhost:6379/0')
PASSWORD = os.getenv('PASSWORD', '134')
LOGIN = os.getenv('LOGIN', 'John')
DEBUG = bool(os.getenv('DEBUG', False))
PORT = int(os.getenv('PORT', 8084))
SECRET = os.getenv('SECRET', 'key')
AUTH_URL = os.getenv('AUTH_URL', 'https://codingprojects.ru/insider/jwt?redirect_url=') + APP_URL
JWT_SECRET = os.getenv('JWT_SECRET')