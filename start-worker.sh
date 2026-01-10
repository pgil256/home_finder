#!/bin/bash
set -e

echo "=== Starting Celery Worker ===" >&2

exec celery -A home_finder worker \
    --loglevel=info \
    --concurrency=2
