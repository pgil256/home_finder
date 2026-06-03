#!/bin/bash
export SECRET_KEY="${SECRET_KEY:-build-only-static-secret}"
pip install -r requirements.txt
python manage.py collectstatic --noinput
