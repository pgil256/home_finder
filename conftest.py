import pytest
from django.test import Client


@pytest.fixture(autouse=True)
def use_simple_staticfiles_storage(settings):
    """Use simple static files storage for tests (no manifest required)."""
    settings.STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'


@pytest.fixture
def client():
    return Client()


@pytest.fixture(scope='session')
def celery_config():
    return {
        'broker_url': 'memory://',
        'result_backend': 'cache+memory://',
        'task_always_eager': True,
        'task_eager_propagates': True,
    }


@pytest.fixture
def celery_eager(settings):
    """Configure Celery to run tasks synchronously."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture
def api_client():
    from django.test import Client
    return Client(content_type='application/json')


@pytest.fixture
def sample_search_criteria():
    return {
        'city': 'Clearwater',
        'zip_code': '33755',
        'property_type': 'Single Family',
        'min_price': 100000,
        'max_price': 500000,
    }
