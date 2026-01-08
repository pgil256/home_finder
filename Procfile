web: python manage.py migrate && python manage.py collectstatic --noinput && gunicorn home_finder.wsgi
worker: celery -A home_finder worker --loglevel=info
