"""Tests for the WebScraper views.

After the architecture pivot (search → DB query, no Celery), the old
tests for the progress polling routes, task status API, and rate limiter
were deleted. These cover the current behavior:
  - GET /scraper/ renders the form
  - POST /scraper/ translates form fields to dashboard query params and 302s
  - /scraper/dashboard/ filters work and reject bad input gracefully
  - /scraper/download/{excel,pdf}/ are guest-accessible and return real files
"""

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from apps.WebScraper.models import PropertyListing

pytestmark = pytest.mark.django_db


class TestSearchForm:
    def test_get_renders_form(self, client):
        response = client.get('/scraper/')
        assert response.status_code == 200

    def test_get_uses_search_template(self, client):
        response = client.get('/scraper/')
        assert 'WebScraper/search.html' in [t.name for t in response.templates]

    def test_get_prefills_form_from_query_params(self, client):
        response = client.get(
            '/scraper/',
            {
                'q': 'Main',
                'city': 'Clearwater',
                'zip_code': '33755',
                'property_type': ['Single Family', 'Condo'],
                'min_price': '100000',
                'max_price': '500000',
                'year_built': '1980',
                'min_sqft': '1000',
                'max_sqft': '2200',
                'min_lot_sqft': '5000',
                'max_lot_sqft': '9000',
                'min_tax_amount': '1000',
                'max_tax_amount': '4500',
            },
        )

        values = response.context['search_values']
        assert values['q'] == 'Main'
        assert values['city'] == 'Clearwater'
        assert values['zip_code'] == '33755'
        assert values['property_type'] == ['Single Family', 'Condo']
        assert values['min_price'] == '100000'
        assert values['max_price'] == '500000'
        assert values['year_built'] == '1980'
        assert values['min_sqft'] == '1000'
        assert values['max_sqft'] == '2200'
        assert values['min_lot_sqft'] == '5000'
        assert values['max_lot_sqft'] == '9000'
        assert values['min_tax_amount'] == '1000'
        assert values['max_tax_amount'] == '4500'

    def test_get_prefills_form_from_last_search_session(self, client):
        client.post(
            '/scraper/',
            {
                'city': 'Clearwater',
                'zip_code': '33755',
                'property_type': ['Single Family'],
                'min_price': '100000',
                'max_price': '500000',
                'min_lot_sqft': '5000',
            },
        )

        response = client.get('/scraper/')

        values = response.context['search_values']
        assert values['city'] == 'Clearwater'
        assert values['zip_code'] == '33755'
        assert values['property_type'] == ['Single Family']
        assert values['min_price'] == '100000'
        assert values['max_price'] == '500000'
        assert values['min_lot_sqft'] == '5000'

    def test_post_redirects_to_dashboard_with_filter_params(self, client):
        response = client.post(
            '/scraper/',
            {
                'city': 'Clearwater',
                'min_price': '100000',
                'max_price': '500000',
            },
        )
        assert response.status_code == 302
        parsed = urlparse(response.url)
        assert parsed.path == '/scraper/dashboard/'
        params = parse_qs(parsed.query)
        assert params['city'] == ['Clearwater']
        assert params['min_price'] == ['100000']
        assert params['max_price'] == ['500000']

    def test_post_preserves_multi_value_property_types(self, client):
        response = client.post(
            '/scraper/',
            {
                'city': 'St. Petersburg',
                'property_type': ['Single Family', 'Condo'],
            },
        )
        assert response.status_code == 302
        params = parse_qs(urlparse(response.url).query)
        assert sorted(params['property_type']) == ['Condo', 'Single Family']

    def test_post_preserves_pcpao_backed_filter_params(self, client):
        response = client.post(
            '/scraper/',
            {
                'q': 'Main',
                'zip_code': '33755',
                'min_lot_sqft': '5000',
                'max_lot_sqft': '9000',
                'min_tax_amount': '1000',
                'max_tax_amount': '4500',
            },
        )

        assert response.status_code == 302
        params = parse_qs(urlparse(response.url).query)
        assert params['q'] == ['Main']
        assert params['zip_code'] == ['33755']
        assert params['min_lot_sqft'] == ['5000']
        assert params['max_lot_sqft'] == ['9000']
        assert params['min_tax_amount'] == ['1000']
        assert params['max_tax_amount'] == ['4500']

    def test_post_drops_non_buyer_filter_params(self, client):
        response = client.post(
            '/scraper/',
            {
                'q': 'Main',
                'min_assessed_value': '90000',
                'max_assessed_value': '450000',
                'tax_status': 'Delinquent',
                'min_lot_sqft': '5000',
            },
        )

        assert response.status_code == 302
        params = parse_qs(urlparse(response.url).query)
        assert params['q'] == ['Main']
        assert params['min_lot_sqft'] == ['5000']
        assert 'min_assessed_value' not in params
        assert 'max_assessed_value' not in params
        assert 'tax_status' not in params

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
        response = client.get(
            '/scraper/dashboard/',
            {
                'city': 'Clearwater',
                'min_price': '100000',
                'max_price': '500000',
            },
        )
        assert response.status_code == 200
        assert response.context['total_count'] == 1

    def test_filter_excludes_non_matching(self, client, sample_property):
        response = client.get(
            '/scraper/dashboard/',
            {
                'min_price': '999999',
            },
        )
        assert response.status_code == 200
        assert response.context['total_count'] == 0

    def test_dashboard_filters_by_pcpao_backed_fields(self, client):
        matching = PropertyListing.objects.create(
            parcel_id='match-001',
            address='100 Main St',
            city='Clearwater',
            zip_code='33755',
            owner_name='Main Owner',
            property_type='Single Family',
            market_value=Decimal('245000.00'),
            assessed_value=Decimal('220500.00'),
            building_sqft=1450,
            year_built=1998,
            lot_sqft=7000,
            tax_amount=Decimal('3125.00'),
            tax_status='From PCPAO',
        )
        PropertyListing.objects.create(
            parcel_id='skip-001',
            address='200 Main St',
            city='Clearwater',
            zip_code='33755',
            owner_name='Main Owner',
            property_type='Single Family',
            market_value=Decimal('245000.00'),
            assessed_value=Decimal('320500.00'),
            building_sqft=1450,
            year_built=1998,
            lot_sqft=12000,
            tax_amount=Decimal('6125.00'),
            tax_status='From PCPAO',
        )

        response = client.get(
            '/scraper/dashboard/',
            {
                'q': 'Main',
                'zip_code': '33755',
                'min_lot_sqft': '5000',
                'max_lot_sqft': '9000',
                'min_tax_amount': '2000',
                'max_tax_amount': '4000',
            },
        )

        assert response.status_code == 200
        assert response.context['total_count'] == 1
        assert list(response.context['properties'].object_list) == [matching]

    def test_dashboard_ignores_non_buyer_filter_params(self, client):
        PropertyListing.objects.create(
            parcel_id='buyer-001',
            address='100 Main St',
            city='Clearwater',
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal('245000.00'),
            assessed_value=Decimal('100000.00'),
            building_sqft=1450,
            year_built=1998,
            lot_sqft=7000,
            tax_amount=Decimal('3125.00'),
            tax_status='Paid',
        )
        PropertyListing.objects.create(
            parcel_id='buyer-002',
            address='200 Main St',
            city='Clearwater',
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal('245000.00'),
            assessed_value=Decimal('450000.00'),
            building_sqft=1450,
            year_built=1998,
            lot_sqft=7000,
            tax_amount=Decimal('3125.00'),
            tax_status='Delinquent',
        )

        response = client.get(
            '/scraper/dashboard/',
            {
                'q': 'Main',
                'min_assessed_value': '400000',
                'tax_status': 'Delinquent',
            },
        )

        assert response.status_code == 200
        assert response.context['total_count'] == 2
        chip_labels = [chip['label'] for chip in response.context['active_filter_chips']]
        assert not any('Assessed' in label for label in chip_labels)
        assert not any('Tax:' in label for label in chip_labels)

    def test_modify_search_url_preserves_current_dashboard_filters(self, client, sample_property):
        response = client.get(
            '/scraper/dashboard/',
            {
                'city': 'Clearwater',
                'property_type': ['Single Family', 'Condo'],
                'min_price': '100000',
                'min_tax_amount': '1000',
            },
        )

        parsed = urlparse(response.context['modify_search_url'])
        params = parse_qs(parsed.query)
        assert parsed.path == '/scraper/'
        assert params['city'] == ['Clearwater']
        assert sorted(params['property_type']) == ['Condo', 'Single Family']
        assert params['min_price'] == ['100000']
        assert params['min_tax_amount'] == ['1000']
