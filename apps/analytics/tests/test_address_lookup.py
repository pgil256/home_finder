from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import Q
from django.test import RequestFactory

from apps.analytics.models import PropertyListing
from apps.analytics.services.address_lookup import (
    SUGGEST_LIMIT,
    address_candidates,
    address_q,
    keyword_q,
    lookup_parcels,
    normalize_address_query,
    parcel_id_from_query,
    suggest_parcels,
)
from apps.analytics.services.filtering import apply_filters


def make_parcel(n: int, address: str, **extra) -> PropertyListing:
    defaults = {
        'city': 'Clearwater',
        'zip_code': '33767',
        'property_type': 'Single Family Home',
        'market_value': Decimal('400000.00'),
    }
    defaults.update(extra)
    return PropertyListing.objects.create(parcel_id=f'05-29-15-54666-005-{n:04d}', address=address, **defaults)


class TestNormalizeAddressQuery:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('1700 gulf', '1700 GULF'),
            ('  1700   Gulf  Blvd. ', '1700 GULF BLVD'),
            ('1029 Charles St, Clearwater, FL 33755', '1029 CHARLES ST'),
            ('1029 Charles St Clearwater FL 33755', '1029 CHARLES ST'),
            ('832 8th Ave S St. Petersburg', '832 8TH AVE S'),
            ('701 Mirror Lake Dr N #307', '701 MIRROR LAKE DR N # 307'),
            ('701 Mirror Lake Dr N # 307', '701 MIRROR LAKE DR N # 307'),
            ('701 mirror lake dr n apt 307', '701 MIRROR LAKE DR N # 307'),
            ('701 Mirror Lake Dr N, Unit 307, St Petersburg, FL', '701 MIRROR LAKE DR N # 307'),
            ("100 O'Brien Rd", '100 O BRIEN RD'),
            ('', ''),
            (None, ''),
            (' , ', ''),
        ],
    )
    def test_reduces_to_the_county_form(self, raw, expected):
        assert normalize_address_query(raw) == expected

    @pytest.mark.parametrize('raw', ['Clearwater', '33755', '123 Largo', '100 Unit Rd'])
    def test_leaves_queries_that_only_look_like_extras(self, raw):
        assert normalize_address_query(raw) == raw.upper()

    def test_abbreviated_candidate_follows_the_typed_one(self):
        assert address_candidates('1700 Gulf Boulevard North') == ['1700 GULF BOULEVARD NORTH', '1700 GULF BLVD N']
        assert address_candidates('24862 US Hwy 19 N') == ['24862 US HWY 19 N', '24862 US HIGHWAY 19 N']

    def test_no_second_candidate_when_nothing_to_abbreviate(self):
        assert address_candidates('1700 Gulf Blvd') == ['1700 GULF BLVD']


class TestParcelIdFromQuery:
    @pytest.mark.parametrize(
        'raw',
        ['05-29-15-54666-005-0080', '052915546660050080', ' 05 29 15 54666 005 0080 '],
    )
    def test_accepts_dashed_spaced_or_bare_digits(self, raw):
        assert parcel_id_from_query(raw) == '05-29-15-54666-005-0080'

    @pytest.mark.parametrize(
        'raw', ['1700 Gulf Blvd', '33755', '05-29-15-54666-005-008', '05-29-15-54666-005-0080a', '']
    )
    def test_rejects_everything_else(self, raw):
        assert parcel_id_from_query(raw) is None


@pytest.mark.django_db
class TestLookupParcels:
    def test_prefix_match_returns_sorted_parcels(self):
        make_parcel(1, '1700 GULF BLVD # 2')
        make_parcel(2, '1700 GULF BLVD # 1')
        make_parcel(3, '1701 GULF BLVD')

        result = lookup_parcels('1700 Gulf')

        assert [p.address for p in result.parcels] == ['1700 GULF BLVD # 1', '1700 GULF BLVD # 2']
        assert result.truncated is False

    def test_full_listing_address_finds_the_parcel(self):
        make_parcel(1, '828 ELDORADO AVE')
        result = lookup_parcels('828 Eldorado Avenue, Clearwater, FL 33767')
        assert [p.address for p in result.parcels] == ['828 ELDORADO AVE']

    def test_street_name_without_number_falls_back_to_substring(self):
        make_parcel(1, '1700 GULF BLVD')
        make_parcel(2, '900 MANDALAY AVE')
        result = lookup_parcels('gulf blvd')
        assert [p.address for p in result.parcels] == ['1700 GULF BLVD']

    def test_short_query_without_prefix_match_does_not_scan(self):
        make_parcel(1, '1700 GULF BLVD')
        assert address_q('gulf') is None
        assert lookup_parcels('gulf').parcels == []

    def test_prefix_match_skips_the_substring_scan(self):
        make_parcel(1, '1700 GULF BLVD')
        assert address_q('1700 gulf blvd') == Q(address__startswith='1700 GULF BLVD')

    def test_caps_results_and_flags_truncation(self):
        for n in range(4):
            make_parcel(n, f'1700 GULF BLVD # {n}')
        result = lookup_parcels('1700 gulf', limit=3)
        assert len(result.parcels) == 3
        assert result.truncated is True

    def test_parcel_id_query_resolves_only_when_it_exists(self):
        parcel = make_parcel(80, '828 ELDORADO AVE')
        assert lookup_parcels(parcel.parcel_id.replace('-', '')).parcel_id == parcel.parcel_id
        missing = lookup_parcels('00-00-00-00000-000-0000')
        assert missing.parcel_id is None
        assert missing.parcels == []

    def test_blank_query_runs_no_queries(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert lookup_parcels('   ').parcels == []

    def test_index_is_declared_for_prefix_matching(self):
        index = next(i for i in PropertyListing._meta.indexes if i.name == 'idx_address_prefix')
        assert index.fields == ['address']
        assert index.opclasses == ['varchar_pattern_ops']
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, PropertyListing._meta.db_table)
        assert 'idx_address_prefix' in constraints


@pytest.mark.django_db
class TestKeywordFilter:
    def test_zip_and_city_keywords_keep_working(self):
        assert keyword_q('33767') == Q(zip_code='33767')
        assert keyword_q('st petersburg') == Q(city__iexact='St. Petersburg')
        assert keyword_q('  ') is None

    def test_dashboard_keyword_uses_address_matching(self):
        match = make_parcel(1, '1700 GULF BLVD')
        make_parcel(2, '900 MANDALAY AVE')
        request = RequestFactory().get('/insights/', {'q': '1700 Gulf Boulevard', 'include_all': '1'})
        properties, _, _ = apply_filters(request)
        assert list(properties) == [match]

    def test_dashboard_keyword_with_no_possible_match_is_empty(self):
        make_parcel(1, '1700 GULF BLVD')
        request = RequestFactory().get('/insights/', {'q': 'zzz', 'include_all': '1'})
        properties, _, _ = apply_filters(request)
        assert properties.count() == 0


@pytest.mark.django_db
class TestLookupView:
    def test_empty_form_renders(self, client):
        response = client.get('/lookup/')
        assert response.status_code == 200
        assert 'analytics/lookup.html' in [t.name for t in response.templates]
        assert b'name="q"' in response.content
        assert b'No match' not in response.content

    def test_results_link_to_parcel_pages_with_value_and_tax(self, client):
        parcel = make_parcel(1, '1700 GULF BLVD', est_tax_homestead=6123, est_tax_no_homestead=7450)
        make_parcel(2, '1700 GULF BLVD # 2', est_tax_homestead=None, est_tax_no_homestead=5210)

        response = client.get('/lookup/', {'q': '1700 gulf'})
        html = response.content.decode()

        assert response.status_code == 200
        assert f'/analytics/property/{parcel.parcel_id}/' in html
        assert '$400,000' in html
        assert '$6,123/yr' in html
        assert '$5,210/yr' in html
        assert '$7,450' not in html
        assert '2 matches' in html

    def test_no_match_shows_the_hint(self, client):
        response = client.get('/lookup/', {'q': '99999 Nowhere Lane'})
        assert response.status_code == 200
        assert b'No match for' in response.content
        assert b'house number and street name' in response.content

    def test_query_is_escaped(self, client):
        response = client.get('/lookup/', {'q': '<script>alert(1)</script>'})
        assert b'<script>alert(1)</script>' not in response.content

    def test_parcel_id_redirects_to_the_parcel_page(self, client):
        parcel = make_parcel(80, '828 ELDORADO AVE')
        response = client.get('/lookup/', {'q': parcel.parcel_id})
        assert response.status_code == 302
        assert response['Location'] == f'/analytics/property/{parcel.parcel_id}/'

    def test_lookup_sets_no_cookies(self, client):
        make_parcel(1, '1700 GULF BLVD')
        response = client.get('/lookup/', {'q': '1700 gulf'})
        assert not response.cookies


@pytest.mark.django_db
class TestSuggestParcels:
    def test_prefix_matches_come_back_sorted(self):
        make_parcel(2, '1029 CHAUCER RD')
        make_parcel(1, '1029 CHARLES ST')
        make_parcel(3, '2000 CHARLES ST')

        rows = suggest_parcels('1029 cha')

        assert [row['address'] for row in rows] == ['1029 CHARLES ST', '1029 CHAUCER RD']
        assert set(rows[0]) == {'parcel_id', 'address', 'city', 'market_value'}

    def test_caps_the_list(self):
        for n in range(SUGGEST_LIMIT + 4):
            make_parcel(n, f'1700 GULF BLVD # {n}')
        assert len(suggest_parcels('1700 gulf')) == SUGGEST_LIMIT

    def test_spelled_out_street_type_falls_back_to_the_county_abbreviation(self):
        make_parcel(1, '1029 CHARLES ST')
        assert [row['address'] for row in suggest_parcels('1029 Charles Street')] == ['1029 CHARLES ST']

    def test_too_short_to_suggest_runs_no_queries(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert suggest_parcels('10') == []
            assert suggest_parcels('') == []
            assert suggest_parcels(None) == []

    def test_never_scans_for_a_substring(self, django_assert_num_queries):
        make_parcel(1, '1029 CHARLES ST')
        with django_assert_num_queries(1):
            assert suggest_parcels('charles') == []


@pytest.mark.django_db
class TestSuggestView:
    def test_returns_matches_as_json_with_parcel_urls(self, client):
        parcel = make_parcel(1, '1029 CHARLES ST', market_value=Decimal('1032109.00'))
        other = make_parcel(2, '1029 CHAUCER RD', market_value=None)

        response = client.get('/lookup/suggest/', {'q': '1029 cha'})

        assert response.status_code == 200
        assert response.json() == {
            'results': [
                {
                    'parcel_id': parcel.parcel_id,
                    'address': '1029 CHARLES ST',
                    'city': 'Clearwater',
                    'market_value': 1032109,
                    'url': f'/analytics/property/{parcel.parcel_id}/',
                },
                {
                    'parcel_id': other.parcel_id,
                    'address': '1029 CHAUCER RD',
                    'city': 'Clearwater',
                    'market_value': None,
                    'url': f'/analytics/property/{other.parcel_id}/',
                },
            ]
        }

    def test_short_or_missing_query_is_an_empty_list(self, client):
        assert client.get('/lookup/suggest/').json() == {'results': []}
        assert client.get('/lookup/suggest/', {'q': '10'}).json() == {'results': []}

    def test_is_cacheable_and_sets_no_cookies(self, client):
        make_parcel(1, '1029 CHARLES ST')
        response = client.get('/lookup/suggest/', {'q': '1029 cha'})
        assert 's-maxage=86400' in response['Cache-Control']
        assert not response.cookies

    def test_only_answers_get(self, client):
        assert client.post('/lookup/suggest/', {'q': '1029 cha'}).status_code == 405

    def test_crawlers_are_kept_off_it(self, client):
        assert b'Disallow: /lookup/suggest/' in client.get('/robots.txt').content


@pytest.mark.django_db
class TestLookupFormMarkup:
    @pytest.mark.parametrize('url', ['/', '/lookup/'])
    def test_form_is_wired_for_suggestions(self, client, url):
        html = client.get(url).content.decode()
        assert 'data-lookup-suggest="/lookup/suggest/"' in html
        assert 'role="listbox"' in html
        assert 'lookup.bundle.js' in html
        assert '1700 Gulf' not in html
