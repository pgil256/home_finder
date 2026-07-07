from decimal import Decimal
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import openpyxl
import pytest

from apps.analytics.models import PropertyListing

pytestmark = pytest.mark.django_db


class TestFilterBuilder:
    def test_get_renders_filter_builder(self, client):
        response = client.get('/analytics/')
        assert response.status_code == 200
        assert 'analytics/search.html' in [t.name for t in response.templates]
        assert b'Build a Market Analysis' in response.content

    def test_get_prefills_form_from_query_params(self, client):
        response = client.get(
            '/analytics/',
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

    def test_post_redirects_to_insights_with_filter_params(self, client):
        response = client.post(
            '/analytics/',
            {
                'city': 'Clearwater',
                'min_price': '100000',
                'max_price': '500000',
            },
        )
        assert response.status_code == 302
        parsed = urlparse(response.url)
        assert parsed.path == '/insights/'
        params = parse_qs(parsed.query)
        assert params['city'] == ['Clearwater']
        assert params['min_price'] == ['100000']
        assert params['max_price'] == ['500000']

    def test_post_preserves_multi_value_property_types(self, client):
        response = client.post(
            '/analytics/',
            {
                'city': 'St. Petersburg',
                'property_type': ['Single Family', 'Condo'],
            },
        )
        assert response.status_code == 302
        params = parse_qs(urlparse(response.url).query)
        assert sorted(params['property_type']) == ['Condo', 'Single Family']

    def test_post_drops_removed_filter_params(self, client):
        response = client.post(
            '/analytics/',
            {
                'q': 'Main',
                'min_assessed_value': '90000',
                'max_assessed_value': '450000',
                'tax_status': 'Delinquent',
                'min_lot_sqft': '5000',
            },
        )

        params = parse_qs(urlparse(response.url).query)
        assert params['q'] == ['Main']
        assert params['min_lot_sqft'] == ['5000']
        assert 'min_assessed_value' not in params
        assert 'max_assessed_value' not in params
        assert 'tax_status' not in params

    def test_post_with_no_fields_still_redirects(self, client):
        response = client.post('/analytics/', {})
        assert response.status_code == 302
        assert urlparse(response.url).path == '/insights/'


class TestInsightsDashboard:
    def test_root_renders_insights_dashboard(self, client, sample_property):
        response = client.get('/')
        assert response.status_code == 200
        assert 'analytics/market-insights.html' in [t.name for t in response.templates]
        assert b'Pinellas Market Lens' in response.content

    def test_insights_route_renders_dashboard(self, client, sample_property):
        response = client.get('/insights/')
        assert response.status_code == 200
        assert response.context['insights']['brand'] == 'Pinellas Market Lens'
        assert response.context['total_count'] == 1
        assert b'Exact Market KPIs' in response.content
        assert b'market-insights-charts' in response.content

    def test_legacy_dashboard_alias_renders_insights(self, client, sample_property):
        response = client.get('/analytics/dashboard/')
        assert response.status_code == 200
        assert 'analytics/market-insights.html' in [t.name for t in response.templates]
        assert b'Auditable Outliers' in response.content

    def test_invalid_numeric_filters_do_not_500(self, client, sample_property):
        response = client.get(
            '/insights/',
            {
                'min_price': 'not-a-number',
                'max_sqft': 'abc',
                'min_lot_sqft': 'bad',
                'max_tax_amount': 'oops',
            },
        )
        assert response.status_code == 200

    def test_valid_filters_apply_to_insights(self, client, sample_property):
        response = client.get(
            '/insights/',
            {
                'city': 'Clearwater',
                'min_price': '100000',
                'max_price': '500000',
            },
        )
        assert response.status_code == 200
        assert response.context['total_count'] == 1
        assert response.context['insights']['exact']['parcel_count'] == 1

    def test_filter_excludes_non_matching(self, client, sample_property):
        response = client.get('/insights/', {'min_price': '999999'})
        assert response.status_code == 200
        assert response.context['total_count'] == 0
        assert response.context['insights']['takeaways'] == [
            'No parcels match the current filters. Broaden the scope to generate market signals.'
        ]

    def test_insights_links_drop_removed_filter_params(self, client):
        for i in range(13):
            PropertyListing.objects.create(
                parcel_id=f'link-{i:03d}',
                address=f'{100 + i} Oak St',
                city='Clearwater',
                zip_code='33755',
                property_type='Single Family',
                market_value=Decimal('245000.00'),
                assessed_value=Decimal('450000.00'),
                building_sqft=1450,
                year_built=1998,
                lot_sqft=7000,
                tax_amount=Decimal('3125.00'),
                tax_status='Paid',
            )

        response = client.get(
            '/insights/',
            {
                'q': 'Oak',
                'zip_code': '33755',
                'min_lot_sqft': '5000',
                'min_assessed_value': '400000',
                'tax_status': 'Delinquent',
            },
        )

        assert response.status_code == 200
        assert response.context['dashboard_querystring'] == 'q=Oak&zip_code=33755&min_lot_sqft=5000'
        html = response.content.decode()
        assert 'min_assessed_value' not in html
        assert 'tax_status=Delinquent' not in html

    def test_outlier_rows_link_to_parcel_drilldowns(self, client):
        for i, value in enumerate([100000, 110000, 120000, 130000, 900000]):
            PropertyListing.objects.create(
                parcel_id=f'outlier-{i:03d}',
                address=f'{i} Signal St',
                city='Clearwater',
                zip_code='33755',
                property_type='Single Family',
                market_value=Decimal(value),
                assessed_value=Decimal('90000.00'),
                building_sqft=1000 + i,
                tax_amount=Decimal('2500.00'),
            )

        response = client.get('/insights/')
        assert response.status_code == 200
        assert '/analytics/property/outlier-004/' in response.content.decode()


class TestExports:
    def test_excel_download_is_analysis_workbook(self, client, sample_property):
        response = client.get('/analytics/download/excel/')
        assert response.status_code == 200
        assert 'spreadsheetml' in response['Content-Type']
        assert 'PinellasMarketLens_' in response['Content-Disposition']

        workbook = openpyxl.load_workbook(BytesIO(response.content), read_only=True)
        assert workbook.sheetnames == [
            'Overview',
            'City Segments',
            'Property Type Segments',
            'Outliers',
            'Sample Parcels',
            'Methodology',
        ]
        assert workbook['Overview']['A1'].value == 'Pinellas Market Lens'

    def test_pdf_download_is_insight_brief(self, client, sample_property):
        response = client.get('/analytics/download/pdf/')
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert 'PinellasMarketLens_' in response['Content-Disposition']
        assert response.content[:5] == b'%PDF-'

    @pytest.mark.parametrize(
        ('url', 'content_type'),
        [
            ('/analytics/download/excel/', 'spreadsheetml'),
            ('/analytics/download/pdf/', 'application/pdf'),
        ],
    )
    def test_download_ignores_invalid_numeric_filter_params(self, client, sample_property, url, content_type):
        response = client.get(
            url,
            {
                'min_price': 'not-a-number',
                'max_sqft': 'abc',
                'min_lot_sqft': 'bad',
                'max_tax_amount': 'oops',
            },
        )

        assert response.status_code == 200
        assert content_type in response['Content-Type']


class TestExportRateLimit:
    """Exports are unauthenticated and build a workbook/PDF over up to 50k
    rows per hit, so repeat downloads are capped per client IP per format."""

    def test_second_download_within_the_window_is_rate_limited(self, client, sample_property):
        first = client.get('/analytics/download/excel/')
        assert first.status_code == 200

        second = client.get('/analytics/download/excel/')

        assert second.status_code == 302
        assert urlparse(second.url).path == '/insights/'

    def test_rate_limit_is_scoped_per_format(self, client, sample_property):
        excel = client.get('/analytics/download/excel/')
        assert excel.status_code == 200

        # A PDF request right after an Excel download uses a separate bucket.
        pdf = client.get('/analytics/download/pdf/')

        assert pdf.status_code == 200


class TestLegacyScraperRedirect:
    """The app was renamed WebScraper -> analytics; /scraper/ must still resolve."""

    def test_scraper_root_redirects_to_analytics(self, client):
        response = client.get('/scraper/')
        assert response.status_code == 302
        assert urlparse(response.url).path == '/analytics/'

    def test_scraper_subpath_and_query_preserved(self, client):
        response = client.get('/scraper/download/excel/?city=Clearwater')
        assert response.status_code == 302
        parsed = urlparse(response.url)
        assert parsed.path == '/analytics/download/excel/'
        assert parse_qs(parsed.query)['city'] == ['Clearwater']
