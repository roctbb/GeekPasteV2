#!/bin/bash
nohup python3 paste_server.py > /dev/null 2>&1 &
nohup python3 -m celery -A paste_celery.celery worker --loglevel=info > /dev/null 2>&1 &