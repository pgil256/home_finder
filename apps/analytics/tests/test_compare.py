import json
import re
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.analytics.models import PropertyListing, TaxDistrictMillage
from apps.analytics.services import tax_estimate
from apps.analytics.services.compare import COMPARE_LIMIT, build_comparison, parse_compare_ids

pytestmark = pytest.mark.django_db

CAPPED_HOME = '36-30-16-78588-003-0060'
BEACH_CONDO = '07-31-15-00000-000-0010'


def _listing(parcel_id, **fields):
    defaults = {
        'address': '1043 61ST AVE N',
        'city': 'St. Petersburg',
        'zip_code': '33703',
        'property_type': 'Single Family Home',
        'market_value': Decimal('282885'),
        'tax_district': 'SP',
        'special_assessment': Decimal('0'),
        'est_tax_current': 678,
        'est_tax_homestead': 4777,
        'est_tax_no_homestead': 5635,
    }
    return PropertyListing.objects.create(parcel_id=parcel_id, **{**defaults, **fields})


@pytest.fixture(autouse=True)
def buying_in_2026():
    with patch.object(tax_estimate, 'buyer_tax_year', return_value=2027):
        yield


@pytest.fixture
def millage(db):
    return TaxDistrictMillage.objects.create(
        district_code='SP',
        tax_year=2025,
        rate_description='2025 Final',
        total_mills=Decimal('19.9197'),
        school_mills=Decimal('6.2930'),
    )


@pytest.fixture
def capped_home(millage):
    return _listing(CAPPED_HOME, building_sqft=1200, year_built=1956, evac_zone='NONE', subsidence=False)


@pytest.fixture
def beach_condo(millage):
    return _listing(
        BEACH_CONDO,
        address='500 GULF BLVD 4',
        city='Indian Rocks Beach',
        property_type='Condominium',
        market_value=Decimal('500000'),
        est_tax_homestead=None,
        est_tax_no_homestead=9960,
        year_built=1984,
        evac_zone='A',
        subsidence=True,
    )


class TestParseCompareIds:
    def test_keeps_order_and_drops_repeats_and_blanks(self):
        assert parse_compare_ids(' b , a,,b ,c') == ['b', 'a', 'c']

    @pytest.mark.parametrize('raw', [None, '', ' , '])
    def test_nothing_to_compare(self, raw):
        assert parse_compare_ids(raw) == []

    def test_ignores_values_too_long_to_be_a_parcel_id(self):
        assert parse_compare_ids(f'{"9" * 51},{CAPPED_HOME}') == [CAPPED_HOME]


class TestBuildComparison:
    def test_homes_come_back_in_the_order_they_were_saved(self, capped_home, beach_condo):
        comparison = build_comparison(f'{BEACH_CONDO},{CAPPED_HOME}')

        assert [home.listing.parcel_id for home in comparison.homes] == [BEACH_CONDO, CAPPED_HOME]
        assert (comparison.missing, comparison.left_out) == (0, 0)

    def test_reuses_the_tax_and_risk_services(self, capped_home, beach_condo):
        condo, house = build_comparison(f'{BEACH_CONDO},{CAPPED_HOME}').homes

        assert (house.tax_outlook.current_owner, house.tax_outlook.homestead) == (678, 4777)
        assert condo.tax_outlook.homestead is None
        assert [flag.title for flag in condo.risk_flags][:2] == ['Subsidence on record', 'Evacuation zone A']
        assert house.has_risk_data

    def test_uses_the_newest_millage_for_each_district(self, capped_home):
        TaxDistrictMillage.objects.create(
            district_code='SP',
            tax_year=2026,
            rate_description='2026 Final',
            total_mills=Decimal('20.0000'),
            school_mills=Decimal('6.0000'),
        )

        (home,) = build_comparison(CAPPED_HOME).homes

        assert home.tax_outlook.millage_description == '2026 Final'

    def test_counts_saved_homes_the_county_no_longer_has(self, capped_home):
        comparison = build_comparison(f'{CAPPED_HOME},00-00-00-00000-000-0000')

        assert len(comparison.homes) == 1
        assert comparison.missing == 1

    def test_shows_only_the_first_six(self, millage):
        ids = [f'15-29-16-00000-000-{n:04d}' for n in range(COMPARE_LIMIT + 2)]
        for parcel_id in ids:
            _listing(parcel_id)

        comparison = build_comparison(','.join(ids))

        assert [home.listing.parcel_id for home in comparison.homes] == ids[:COMPARE_LIMIT]
        assert (comparison.requested, comparison.left_out, comparison.missing) == (COMPARE_LIMIT + 2, 2, 0)

    def test_query_count_does_not_grow_with_the_number_of_homes(
        self, capped_home, beach_condo, django_assert_num_queries
    ):
        with django_assert_num_queries(2):
            build_comparison(f'{BEACH_CONDO},{CAPPED_HOME}')


class TestComparePage:
    def _html(self, client, ids=None):
        response = client.get('/analytics/compare/', {'ids': ids} if ids is not None else {})
        assert response.status_code == 200
        return response.content.decode('utf-8', 'ignore')

    def test_shows_each_home_as_a_column(self, client, capped_home, beach_condo):
        html = self._html(client, f'{CAPPED_HOME},{BEACH_CONDO}')

        assert html.index('1043 61ST AVE N') < html.index('500 GULF BLVD 4')
        for parcel_id in (CAPPED_HOME, BEACH_CONDO):
            assert f'href="/analytics/property/{parcel_id}/"' in html
            assert f'data-unsave="{parcel_id}"' in html
        # The seller's bill next to the buyer's, which is the point of the app.
        assert '$678' in html
        assert '$4,777' in html
        assert "Can't be homesteaded" in html
        assert '$9,960' in html
        assert 'Subsidence on record' in html
        assert 'Not in an evacuation zone' in html
        assert f'/analytics/property/{BEACH_CONDO}/#risks' in html

    def test_seeds_the_calculator_with_one_entry_per_column(self, client, capped_home, beach_condo):
        _listing('15-29-16-00000-000-0001', tax_district='ZZ')

        html = self._html(client, f'{CAPPED_HOME},15-29-16-00000-000-0001,{BEACH_CONDO}')
        match = re.search(r'<script id="affordability-data" type="application/json">(.*?)</script>', html, re.S)
        config = json.loads(match.group(1))

        assert config['homes'] == [
            {'price': 282885.0, 'taxHomestead': 4777, 'taxNoHomestead': 5635},
            None,
            {'price': 500000.0, 'taxHomestead': None, 'taxNoHomestead': 9960},
        ]
        assert config['otherCosts'] == 4000
        assert 'data-compare-home="0" data-compare-output="monthly"' in html
        assert 'data-compare-home="1"' not in html
        assert 'data-compare-home="2" data-compare-output="cashToClose"' in html
        assert 'js/dist/affordability.bundle.js' in html

    def test_no_cost_rows_when_no_home_has_a_tax_estimate(self, client):
        _listing(CAPPED_HOME, tax_district=None)

        html = self._html(client, CAPPED_HOME)

        assert '1043 61ST AVE N' in html
        assert 'Monthly payment' not in html
        assert 'affordability.bundle.js' not in html

    def test_empty_state_lets_the_browser_fill_in_its_saved_homes(self, client):
        html = self._html(client)

        assert 'No saved homes yet' in html
        assert 'data-compare-empty' in html
        assert 'data-compare-url="/analytics/compare/"' in html

    def test_unknown_ids_do_not_bounce_back_to_the_saved_list(self, client):
        html = self._html(client, '00-00-00-00000-000-0000')

        assert 'in the county record any more' in html
        assert 'data-compare-empty' not in html

    def test_says_when_a_saved_home_is_gone_or_left_out(self, client, millage):
        ids = [f'15-29-16-00000-000-{n:04d}' for n in range(COMPARE_LIMIT + 1)]
        for parcel_id in ids[1:]:
            _listing(parcel_id)

        html = self._html(client, ','.join(ids))

        assert '1 saved home isn&#x27;t in the county record any more' in html
        assert f'Showing the first {COMPARE_LIMIT} of {COMPARE_LIMIT + 1} saved homes' in html

    def test_is_kept_out_of_search_engines(self, client, capped_home):
        assert '<meta name="robots" content="noindex, nofollow">' in self._html(client, CAPPED_HOME)
        assert 'Disallow: /analytics/compare/' in client.get('/robots.txt').content.decode()


class TestSavedLinkInTheHeader:
    @pytest.mark.parametrize('url', ['/', '/lookup/', '/analytics/compare/'])
    def test_every_page_links_to_saved_homes(self, client, url):
        html = client.get(url).content.decode('utf-8', 'ignore')

        # Desktop and mobile menus; common.js adds the count and the IDs.
        assert html.count('data-saved-link="/analytics/compare/"') == 2

    def test_save_button_uses_the_shared_saved_list(self, client, capped_home):
        html = client.get(f'/analytics/property/{CAPPED_HOME}/').content.decode('utf-8', 'ignore')

        assert 'HomeFinder.toggleSavedHome' in html
        assert 'localStorage' not in html
