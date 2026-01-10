#!/bin/bash
set -e

echo "=== Starting Celery Worker ===" >&2

echo "=== Running migrations ===" >&2
python manage.py migrate

echo "=== Starting Celery ===" >&2
exec celery -A home_finder worker \
    --loglevel=info \
    --concurrency=2
