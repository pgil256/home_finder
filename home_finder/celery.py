from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'home_finder.settings')

app = Celery('home_finder')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

app.conf.update(
    task_send_sent_event=True,
    worker_send_task_events=True,
    result_persistent=True,
    task_soft_time_limit=300,
    task_time_limit=360,
    worker_max_tasks_per_child=50,
)
