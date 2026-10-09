from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import openpyxl
import pytest

from apps.analytics.models import PropertyListing, TaxDistrictMillage, ZipFloodHistory
from apps.analytics.services import tax_estimate

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
    def test_root_renders_product_intro(self, client, sample_property):
        response = client.get('/')
        assert response.status_code == 200
        assert 'Pages/home.html' in [t.name for t in response.templates]
        assert b'Pinellas Market Lens' in response.content
        assert b'Exact Market KPIs' not in response.content

    def test_insights_route_renders_dashboard(self, client, sample_property):
        response = client.get('/insights/')
        assert response.status_code == 200
        assert response.context['insights']['brand'] == 'Pinellas Market Lens'
        assert response.context['total_count'] == 1
        assert b'Exact Market KPIs' in response.content
        assert b'market-insights-charts' in response.content
        assert b'data-kpi-value="Total market value"' in response.content
        assert b'whitespace-nowrap' in response.content

    def test_legacy_dashboard_alias_redirects_to_insights(self, client, sample_property):
        response = client.get('/analytics/dashboard/?city=Clearwater')
        assert response.status_code == 302
        parsed = urlparse(response.url)
        assert parsed.path == '/insights/'
        assert parse_qs(parsed.query)['city'] == ['Clearwater']

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


class TestGoogleIndependence:
    def test_paid_street_view_endpoint_is_gone(self, client, sample_property):
        response = client.get(f'/analytics/property/{sample_property.parcel_id}/streetview/')

        assert response.status_code == 404

    def test_detail_page_has_no_google_requests_and_uses_openstreetmap(self, client, sample_property):
        response = client.get(f'/analytics/property/{sample_property.parcel_id}/')
        html = response.content.decode('utf-8', 'ignore')

        assert '/streetview/' not in html
        assert 'googleapis.com' not in html
        assert 'gstatic.com' not in html
        assert 'google.com/maps' not in html
        assert 'GOOGLE_STREET_VIEW_API_KEY' not in html
        assert 'https://www.openstreetmap.org/search?query=' in html

    def test_detail_page_uses_county_property_photo_when_available(self, client, sample_property):
        sample_property.image_url = 'https://www.pcpao.gov/property-photo/example.jpg'
        sample_property.save(update_fields=['image_url'])

        response = client.get(f'/analytics/property/{sample_property.parcel_id}/')
        html = response.content.decode('utf-8', 'ignore')

        assert sample_property.image_url in html
        assert f'County property record photo for {sample_property.address}' in html

    def test_detail_page_suppresses_historical_external_photo_urls(self, client, sample_property):
        sample_property.image_url = 'https://maps.googleapis.com/maps/api/streetview?key=historical-key'
        sample_property.save(update_fields=['image_url'])

        html = client.get(f'/analytics/property/{sample_property.parcel_id}/').content.decode('utf-8', 'ignore')

        assert sample_property.image_url not in html
        assert 'historical-key' not in html

    def test_base_page_does_not_load_google_fonts(self, client):
        html = client.get('/').content.decode('utf-8', 'ignore')

        assert 'fonts.googleapis.com' not in html
        assert 'fonts.gstatic.com' not in html


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


class TestSessionsStayOutOfTheDatabase:
    def test_filtered_insights_request_writes_no_session_row(self, client, sample_property):
        from django.contrib.sessions.models import Session

        response = client.get('/insights/', {'city': 'Clearwater'})

        assert response.status_code == 200
        assert Session.objects.count() == 0

    def test_insights_hands_its_filters_to_the_browser_to_remember(self, client, sample_property):
        """The last search is kept in localStorage, not in a session cookie."""
        response = client.get('/insights/', {'city': 'Clearwater', 'min_price': '100000', 'sort': 'city'})

        assert 'data-remember-search="city=Clearwater&amp;min_price=100000"' in response.content.decode()
        assert not response.cookies

    def test_filter_builder_asks_the_browser_for_the_last_search(self, client, sample_property):
        client.get('/insights/', {'city': 'Clearwater', 'min_price': '100000'})

        html = client.get('/analytics/').content.decode()

        assert 'data-restore-search="/analytics/"' in html
        assert 'value="100000"' not in html


class TestCrawlerHygiene:
    def test_robots_txt_keeps_crawlers_off_expensive_urls(self, client):
        response = client.get('/robots.txt')
        body = response.content.decode()

        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/plain')
        assert 'Disallow: /insights/?' in body
        assert 'Disallow: /analytics/download/' in body

    def test_filtered_insights_are_not_indexed(self, client, sample_property):
        filtered = client.get('/insights/', {'city': 'Clearwater'}).content.decode()
        default = client.get('/insights/').content.decode()

        assert '<meta name="robots" content="noindex, nofollow">' in filtered
        assert 'noindex' not in default

    def test_export_links_are_nofollow(self, client, sample_property):
        html = client.get('/insights/').content.decode()

        for url in ('/analytics/download/excel/', '/analytics/download/pdf/'):
            start = html.index(f'href="{url}')
            assert 'rel="nofollow"' in html[start : html.index('>', start)]


class TestNearbyHomesCard:
    """The subject is a $245,000 single family home in Clearwater."""

    def _home(self, n, value, neighborhood='N100', **extra):
        fields = {
            'parcel_id': f'15-29-16-12345-000-{n:04d}',
            'address': f'{n} Nearby Way',
            'city': 'Clearwater',
            'zip_code': '33755',
            'property_type': 'Single Family',
            'market_value': Decimal(value),
            'building_sqft': 1500,
            'year_built': 1990,
            'neighborhood_code': neighborhood,
        }
        fields.update(extra)
        return PropertyListing.objects.create(**fields)

    def _shown(self, client, parcel):
        response = client.get(f'/analytics/property/{parcel.parcel_id}/')
        return [home.address for home in response.context['nearby_homes']]

    @pytest.fixture
    def subject(self, sample_property):
        sample_property.neighborhood_code = 'N100'
        sample_property.save()
        return sample_property

    def test_shows_the_four_nearest_in_value_from_the_same_neighborhood(self, client, subject):
        self._home(101, 150000)
        self._home(102, 240000)
        self._home(103, 251000)
        self._home(104, 400000)
        self._home(105, 230000)
        self._home(106, 262000)
        # Closer in value than any of them, but somewhere else or something else.
        self._home(201, 245000, neighborhood='N999')
        self._home(202, 245500, property_type='Condominium')

        assert self._shown(client, subject) == [
            '102 Nearby Way',
            '103 Nearby Way',
            '105 Nearby Way',
            '106 Nearby Way',
        ]

    def test_small_neighborhood_is_filled_from_the_city_nearest_in_value_first(self, client, subject):
        self._home(101, 400000)
        self._home(201, 290000, neighborhood='N999')
        self._home(202, 244000, neighborhood='N999')
        self._home(203, 255000, neighborhood='N999')
        self._home(204, 210000, neighborhood='N999')
        # Out of the 20% band, another city, another type.
        self._home(301, 500000, neighborhood='N999')
        self._home(302, 245000, neighborhood='N999', city='Largo')
        self._home(303, 245000, neighborhood='N999', property_type='Condominium')

        assert self._shown(client, subject) == [
            '101 Nearby Way',
            '202 Nearby Way',
            '203 Nearby Way',
            '204 Nearby Way',
        ]

    def test_parcel_without_a_neighborhood_uses_the_city(self, client, sample_property):
        self._home(201, 250000)
        assert self._shown(client, sample_property) == ['201 Nearby Way']

    def test_parcel_without_a_value_shows_no_card(self, client, subject):
        self._home(101, 240000)
        subject.market_value = None
        subject.save()

        response = client.get(f'/analytics/property/{subject.parcel_id}/')

        assert response.context['nearby_homes'] == []
        assert 'Nearby homes the county values alike' not in response.content.decode()

    def test_cards_show_size_year_and_value_and_say_they_are_not_sales(self, client, subject):
        self._home(101, 250000, bedrooms=3, bathrooms=Decimal('2.0'))

        html = client.get(f'/analytics/property/{subject.parcel_id}/').content.decode()

        assert 'Nearby homes the county values alike' in html
        assert 'These are not sales' in html
        assert 'Similar Properties' not in html
        card = html[html.index('101 Nearby Way') :]
        assert '1,500 sqft' in card
        assert 'Built 1990' in card
        assert '$250,000' in html
        assert '3 bd' not in html
        assert '2 ba' not in html

    def test_full_neighborhood_costs_one_query(self, subject, django_assert_num_queries):
        from apps.analytics.services.nearby_homes import nearby_homes

        for n in range(101, 106):
            self._home(n, 240000 + n)
        with django_assert_num_queries(1):
            assert len(nearby_homes(subject)) == 4


class TestTaxEstimateCard:
    """1043 61st Ave N, St. Petersburg: the owner's Save Our Homes cap holds
    a $282,885 home at a $77,124 assessment. Hand-worked figures are in
    test_tax_estimate.py."""

    @pytest.fixture(autouse=True)
    def buying_in_2026(self):
        # Patched rather than frozen: freezegun can crash pandas' first import.
        with patch.object(tax_estimate, 'buyer_tax_year', return_value=2027):
            yield

    @pytest.fixture
    def capped_home(self, db):
        TaxDistrictMillage.objects.create(
            district_code='SP',
            tax_year=2025,
            rate_description='2025 Final',
            total_mills=Decimal('19.9197'),
            school_mills=Decimal('6.2930'),
        )
        return PropertyListing.objects.create(
            parcel_id='36-30-16-78588-003-0060',
            address='1043 61ST AVE N',
            city='St. Petersburg',
            zip_code='33703',
            property_type='Single Family Home',
            market_value=Decimal('282885'),
            assessed_value=Decimal('77124'),
            tax_amount=Decimal('5540'),
            tax_status='From PCPAO',
            roll_year=2026,
            tax_district='SP',
            special_assessment=Decimal('0'),
            homestead_cap=True,
            est_tax_current=678,
            est_tax_homestead=4777,
            est_tax_no_homestead=5635,
        )

    def _html(self, client, listing):
        return client.get(f'/analytics/property/{listing.parcel_id}/').content.decode('utf-8', 'ignore')

    def test_compares_current_owner_with_new_owner(self, client, capped_home):
        html = self._html(client, capped_home)

        assert 'Your Property Taxes If You Buy' in html
        assert '$678' in html
        assert '$4,777' in html
        assert '$4,099 more than today' in html
        assert '$5,635' in html
        assert 'Est. taxes if you buy: $4,777/yr' in html
        assert 'by March 1' in html
        assert 'Estimated 2027 bill' in html
        assert 'using 2025 final <a href="/help#term-millage"' in html
        assert 'millage</a> for tax district SP (19.9197 mills)' in html

    def test_shows_amendment_3_scenario_while_vote_is_pending(self, client, capped_home):
        html = self._html(client, capped_home)

        assert 'If Amendment 3 passes on November 3' in html
        assert '$3,434' in html

    def test_amendment_3_passed_flips_main_and_alternative_estimates(self, client, capped_home):
        with patch.object(tax_estimate, 'AMENDMENT_3_STATUS', 'passed'):
            html = self._html(client, capped_home)

        assert 'Est. taxes if you buy: $3,434/yr' in html
        assert 'If you move to Florida after January 1, 2027' in html
        assert 'If Amendment 3 passes' not in html

    def test_amendment_3_failed_hides_alternative(self, client, capped_home):
        with patch.object(tax_estimate, 'AMENDMENT_3_STATUS', 'failed'):
            html = self._html(client, capped_home)

        assert 'Amendment 3' not in html
        assert 'Est. taxes if you buy: $4,777/yr' in html

    def test_recomputes_from_refreshed_just_value(self, client, capped_home):
        """A per-parcel refresh changes market_value without rerunning the import."""
        capped_home.market_value = Decimal('300000')
        capped_home.save(update_fields=['market_value'])

        html = self._html(client, capped_home)

        assert '$5,118' in html  # homestead, current law
        assert '$5,976' in html  # no homestead

    def test_buying_from_an_investor_can_lower_the_bill(self, client, capped_home):
        capped_home.homestead_cap = False
        capped_home.est_tax_current = 5635
        capped_home.save(update_fields=['homestead_cap', 'est_tax_current'])

        assert '$858 less than today' in self._html(client, capped_home)

    def test_parcels_that_cannot_be_homesteaded_show_one_estimate(self, client, capped_home):
        capped_home.est_tax_homestead = None
        capped_home.save(update_fields=['est_tax_homestead'])

        html = self._html(client, capped_home)

        assert 'You, living here' not in html
        assert 'A new owner' in html
        assert 'Amendment 3' not in html
        assert 'Est. taxes if you buy: $5,635/yr' in html

    def test_no_card_without_millage(self, client, capped_home):
        TaxDistrictMillage.objects.all().delete()

        response = client.get(f'/analytics/property/{capped_home.parcel_id}/')

        assert response.status_code == 200
        assert 'Your Property Taxes If You Buy' not in response.content.decode()

    def test_county_tax_figure_is_labeled_before_exemptions(self, client, capped_home):
        html = self._html(client, capped_home)

        assert 'Tax Before Exemptions' in html
        assert 'Annual Tax' not in html


class TestRiskFlagsCard:
    def test_parcel_page_lists_flags_most_serious_first(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(
            evac_zone='A', waterfront=True, frontage='Gulf', seawall=True, subsidence=True
        )

        html = client.get(f'/analytics/property/{sample_property.parcel_id}/').content.decode()

        assert 'What to Check Before You Buy' in html
        for title in ('Subsidence on record', 'Evacuation zone A', 'Waterfront: Gulf', 'Seawall'):
            assert title in html
        assert html.index('Subsidence on record') < html.index('Waterfront: Gulf')
        assert 'Built in 1987, before the 2002 Florida Building Code' in html
        assert 'Check first' in html

    def test_nothing_flagged_is_not_called_a_clean_bill_of_health(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(
            year_built=2015, subsidence=False, contamination=False, waterfront=False
        )

        html = client.get(f'/analytics/property/{sample_property.parcel_id}/').content.decode()

        assert 'Nothing is flagged in the county' in html
        assert 'still get a home inspection' in html

    def test_no_card_before_the_risk_columns_are_imported(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(year_built=2015)

        html = client.get(f'/analytics/property/{sample_property.parcel_id}/').content.decode()

        assert 'What to Check Before You Buy' not in html


class TestMapOnParcelPage:
    def _html(self, client, listing):
        return client.get(f'/analytics/property/{listing.parcel_id}/').content.decode()

    def test_map_card_gets_the_county_map_point(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(latitude='27.965853', longitude='-82.800103')

        response = client.get(f'/analytics/property/{sample_property.parcel_id}/')
        html = response.content.decode()

        assert response.context['parcel_map'] == {'lat': 27.965853, 'lng': -82.800103}
        assert 'id="parcel-map"' in html
        assert '{"lat": 27.965853, "lng": -82.800103}' in html
        assert 'js/dist/parcelMap.bundle.js' in html
        assert 'mlat=27.965853&amp;mlon=-82.800103' in html

    def test_map_credits_its_sources(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(latitude='27.965853', longitude='-82.800103')

        html = self._html(client, sample_property)

        assert 'OpenStreetMap contributors' in html
        assert 'https://openfreemap.org' in html
        assert 'https://maplibre.org' in html

    def test_map_library_is_not_loaded_with_the_page(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(latitude='27.965853', longitude='-82.800103')

        html = self._html(client, sample_property)

        assert 'maplibre-gl' not in html
        assert 'tiles.openfreemap.org' not in html

    def test_no_map_without_coordinates(self, client, sample_property):
        html = self._html(client, sample_property)

        assert 'id="parcel-map"' not in html
        assert 'parcelMap.bundle.js' not in html


class TestFloodOnParcelPage:
    def _html(self, client, listing):
        return client.get(f'/analytics/property/{listing.parcel_id}/').content.decode()

    def test_flood_zone_flag_and_fema_map_link(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(flood_zone='AE', static_bfe='10.0')

        html = self._html(client, sample_property)

        assert 'FEMA flood zone AE' in html
        assert 'base flood elevation is 10 feet' in html
        assert "and FEMA's flood map" in html
        assert 'https://msc.fema.gov/portal/search?AddressQuery=' in html

    def test_zip_claim_history_is_shown_as_neighborhood_context(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(flood_zone='X')
        ZipFloodHistory.objects.create(
            zip_code=sample_property.zip_code, claim_count=7626, recent_claim_count=5012, median_paid=41250
        )

        html = self._html(client, sample_property)

        assert f'Flood insurance claims in ZIP code {sample_property.zip_code}: 7,626 since 1978' in html
        assert '5,012 of them since 2020' in html
        assert 'The typical paid claim was $41,250.' in html
        assert 'says nothing about this home' in html

    def test_nothing_about_flooding_before_the_first_flood_refresh(self, client, sample_property):
        html = self._html(client, sample_property)

        assert 'id="flood"' not in html
        assert 'FEMA' not in html


class TestRiskFilterPlumbing:
    PARAMS = {'exclude_evac': 'B', 'exclude_subsidence': '1', 'outside_sfha': '1', 'max_est_tax': '6000'}

    def test_insights_filters_and_shows_removable_chips(self, client, sample_property):
        PropertyListing.objects.filter(pk=sample_property.pk).update(evac_zone='A', est_tax_homestead=3000)

        response = client.get('/insights/', self.PARAMS)
        html = response.content.decode()

        assert response.context['total_count'] == 0
        for label in (
            'Outside evacuation zones A-B',
            'No subsidence on record',
            'Outside FEMA high-risk flood zones',
            'New-owner tax up to $6000',
        ):
            assert label in html

    def test_filters_survive_the_trip_through_the_search_form(self, client):
        response = client.post('/analytics/', self.PARAMS)

        assert response.status_code == 302
        query = parse_qs(urlparse(response['Location']).query)
        assert query == {key: [value] for key, value in self.PARAMS.items()}

    def test_search_form_prefills_the_risk_filters(self, client):
        html = client.get('/analytics/', self.PARAMS).content.decode()

        assert '<option value="B" selected>Outside evacuation zones A-B</option>' in html
        assert 'name="max_est_tax"' in html and 'value="6000"' in html
        assert 'name="exclude_subsidence" value="1" checked' in html
        assert 'name="outside_sfha" value="1" checked' in html

    def test_export_summary_names_the_risk_filters(self, client, sample_property):
        response = client.get('/analytics/download/excel/', {'include_all': '1', **self.PARAMS})

        workbook = openpyxl.load_workbook(BytesIO(response.content))
        text = ' '.join(str(cell) for sheet in workbook for row in sheet.iter_rows(values_only=True) for cell in row)
        assert 'Outside evacuation zones A-B' in text
        assert 'None on record' in text
        assert 'Outside FEMA high-risk zones' in text
