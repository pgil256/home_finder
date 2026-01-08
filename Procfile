web: python manage.py migrate && python manage.py collectstatic --noinput && gunicorn home_finder.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120
worker: celery -A home_finder worker --loglevel=info
