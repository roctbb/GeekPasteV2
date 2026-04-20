#!/bin/bash
nohup gunicorn --bind 0.0.0.0:8084 --worker-class gthread --threads 8 --workers 1 --timeout 120 paste_server:app > /dev/null 2>&1 &
nohup python3 -m celery -A paste_celery.celery worker --loglevel=info > /dev/null 2>&1 &
