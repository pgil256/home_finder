#!/bin/bash
set -e

echo "=== Starting application ===" >&2
echo "PORT is: ${PORT:-8000}" >&2

echo "=== Running migrations ===" >&2
python manage.py migrate

echo "=== Migrations complete! ===" >&2

echo "=== Starting gunicorn on port ${PORT:-8000} ===" >&2

exec gunicorn home_finder.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 1 \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile -
