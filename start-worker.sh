#!/bin/bash
set -e

echo "=== Starting Celery Worker ===" >&2

# Log database configuration for debugging
echo "=== Database Configuration ===" >&2
if [ -n "$DATABASE_URL" ]; then
    echo "DATABASE_URL is set (using PostgreSQL)" >&2
else
    echo "WARNING: DATABASE_URL not set, using SQLite (data may not persist!)" >&2
fi

# Log media directory configuration
echo "=== Media Directory ===" >&2
echo "MEDIA_ROOT: /app/media" >&2
mkdir -p /app/media/reports
ls -la /app/media/ 2>/dev/null || echo "Media directory empty or not accessible" >&2

echo "=== Running migrations ===" >&2
python manage.py migrate

# Show database connection info
echo "=== Database Connection Test ===" >&2
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'home_finder.settings')
import django
django.setup()
from django.db import connection
print(f'Database engine: {connection.vendor}')
print(f'Database name: {connection.settings_dict.get(\"NAME\", \"unknown\")}')
"

echo "=== Starting Celery ===" >&2
exec celery -A home_finder worker \
    --loglevel=info \
    --concurrency=2
