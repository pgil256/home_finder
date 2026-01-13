#!/bin/bash
set -e

echo "=== Starting application ===" >&2
echo "PORT is: ${PORT:-8000}" >&2

# Log database configuration for debugging
echo "=== Database Configuration ===" >&2
if [ -n "$DATABASE_URL" ]; then
    echo "DATABASE_URL is set (using PostgreSQL)" >&2
else
    echo "WARNING: DATABASE_URL not set, using SQLite (data may not persist!)" >&2
fi

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
