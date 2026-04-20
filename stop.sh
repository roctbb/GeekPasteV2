#!/bin/bash

pkill -f "gunicorn.*paste_server:app"
pkill -f paste_celery
