import pytest
from django.test import Client


@pytest.fixture(autouse=True)
def use_simple_staticfiles_storage(settings):
    """Use simple static files storage for tests (no manifest required)."""
    settings.STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'


@pytest.fixture
def client():
    return Client()


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
