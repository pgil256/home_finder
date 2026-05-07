"""Tests for the WebScraper views.

After the architecture pivot (search → DB query, no Celery), the old
tests for the progress polling routes, task status API, and rate limiter
were deleted. These cover the current behavior:
  - GET /scraper/ renders the form
  - POST /scraper/ translates form fields to dashboard query params and 302s
  - /scraper/dashboard/ filters work and reject bad input gracefully
  - /scraper/download/{excel,pdf}/ are guest-accessible and return real files
"""
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.django_db


class TestSearchForm:
    def test_get_renders_form(self, client):
        response = client.get('/scraper/')
        assert response.status_code == 200

    def test_get_uses_search_template(self, client):
        response = client.get('/scraper/')
        assert 'WebScraper/search.html' in [t.name for t in response.templates]

    def test_post_redirects_to_dashboard_with_filter_params(self, client):
        response = client.post('/scraper/', {
            'city': 'Clearwater',
            'min_price': '100000',
            'max_price': '500000',
        })
        assert response.status_code == 302
        parsed = urlparse(response.url)
        assert parsed.path == '/scraper/dashboard/'
        params = parse_qs(parsed.query)
        assert params['city'] == ['Clearwater']
        assert params['min_price'] == ['100000']
        assert params['max_price'] == ['500000']

    def test_post_preserves_multi_value_property_types(self, client):
        response = client.post('/scraper/', {
            'city': 'St. Petersburg',
            'property_type': ['Single Family', 'Condo'],
        })
        assert response.status_code == 302
        params = parse_qs(urlparse(response.url).query)
        assert sorted(params['property_type']) == ['Condo', 'Single Family']

    def test_post_with_no_fields_still_redirects(self, client):
        response = client.post('/scraper/', {})
        assert response.status_code == 302
        assert urlparse(response.url).path == '/scraper/dashboard/'


class TestExports:
    """Excel + PDF exports are guest-accessible (no login required)."""

    def test_excel_download(self, client, db):
        response = client.get('/scraper/download/excel/')
        assert response.status_code == 200
        assert 'spreadsheetml' in response['Content-Type']

    def test_pdf_download(self, client, sample_property):
        response = client.get('/scraper/download/pdf/')
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'


class TestDashboardFilterValidation:
    """Invalid filter values are handled gracefully (don't 500)."""

    def test_invalid_min_price_ignored(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {'min_price': 'not-a-number'})
        assert response.status_code == 200

    def test_invalid_max_price_ignored(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {'max_price': 'abc'})
        assert response.status_code == 200

    def test_invalid_beds_ignored(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {'beds': 'xyz'})
        assert response.status_code == 200

    def test_valid_filters_apply(self, client, sample_property):
        # sample_property has property_type='Single Family' (residential),
        # which the default residential filter includes — no need for
        # include_all=1 here.
        response = client.get('/scraper/dashboard/', {
            'city': 'Clearwater',
            'min_price': '100000',
            'max_price': '500000',
        })
        assert response.status_code == 200
        assert response.context['total_count'] == 1

    def test_filter_excludes_non_matching(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {
            'min_price': '999999',
        })
        assert response.status_code == 200
        assert response.context['total_count'] == 0
