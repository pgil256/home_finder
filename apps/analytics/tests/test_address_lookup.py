from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.db.models import Q
from django.test import RequestFactory

from apps.analytics.models import PropertyListing, StreetName
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
from apps.analytics.services.street_names import (
    nearest_streets,
    rebuild_street_names,
    split_address,
    street_of,
    trigram_similarity,
)


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


class TestStreetOfAddress:
    @pytest.mark.parametrize(
        ('address', 'expected'),
        [
            ('1700 GULF BLVD', ('1700', 'GULF BLVD')),
            ('1700 GULF BLVD # 2', ('1700', 'GULF BLVD')),
            ('701 MIRROR LAKE DR N # 307', ('701', 'MIRROR LAKE DR N')),
            ('832 8TH AVE S', ('832', '8TH AVE S')),
            ('100A MAIN ST', ('100A', 'MAIN ST')),
            ('17TH AVE N', ('', '17TH AVE N')),
            ('MIRROR LAKE', ('', 'MIRROR LAKE')),
            ('', ('', '')),
        ],
    )
    def test_splits_house_number_from_street_and_drops_the_unit(self, address, expected):
        assert split_address(address) == expected
        assert street_of(address) == expected[1]

    def test_similarity_matches_pg_trgm(self):
        """Values checked against Postgres: select similarity('GULF BLVD', 'GULF BVLD')."""
        assert trigram_similarity('GULF BLVD', 'GULF BLVD') == 1
        assert trigram_similarity('GULF BLVD', 'gulf bvld') == pytest.approx(0.428571, abs=1e-6)
        assert trigram_similarity('MIRROR LAKE DR N', 'MIRRER LAKE') == pytest.approx(0.45)
        assert trigram_similarity('GULF BLVD', 'MANDALAY AVE') == 0
        assert trigram_similarity('', 'GULF BLVD') == 0


@pytest.fixture
def county_streets(db):
    """A few parcels and the street-name table built from them."""
    make_parcel(1, '1700 GULF BLVD')
    make_parcel(2, '1700 GULF BLVD # 2')
    make_parcel(3, '1702 GULF BLVD', city='Belleair Beach')
    make_parcel(4, '701 MIRROR LAKE DR N # 307', city='St. Petersburg')
    make_parcel(5, '900 MANDALAY AVE')
    make_parcel(6, '832 8TH AVE S', city='St. Petersburg')
    rebuild_street_names()


@pytest.mark.django_db
class TestRebuildStreetNames:
    def test_one_row_per_street_and_city_with_its_parcel_count(self, county_streets):
        rows = set(StreetName.objects.values_list('name', 'city', 'parcel_count'))

        assert rows == {
            ('GULF BLVD', 'Clearwater', 2),
            ('GULF BLVD', 'Belleair Beach', 1),
            ('MIRROR LAKE DR N', 'St. Petersburg', 1),
            ('MANDALAY AVE', 'Clearwater', 1),
            ('8TH AVE S', 'St. Petersburg', 1),
        }

    def test_rebuild_replaces_what_was_there(self, county_streets):
        PropertyListing.objects.filter(address__startswith='900 MANDALAY').delete()

        assert rebuild_street_names() == 4
        assert not StreetName.objects.filter(name='MANDALAY AVE').exists()

    def test_command_reports_the_count(self, county_streets, capsys):
        call_command('rebuild_street_names')
        assert 'Street names rebuilt: 5 rows' in capsys.readouterr().out

    def test_the_import_rebuilds_them(self):
        call_command('import_pcpao_data', file='apps/analytics/fixtures/sample_pcpao_data.csv', quiet=True)

        assert StreetName.objects.filter(name='CHARLES ST', city='Clearwater').exists()
        assert StreetName.objects.filter(name='MIRROR LAKE DR N').exists()


@pytest.mark.django_db
class TestNearestStreets:
    def test_finds_the_street_behind_a_typo(self, county_streets):
        assert [street.name for street in nearest_streets('GULF BVLD')] == ['GULF BLVD']

    def test_same_name_in_two_cities_is_one_suggestion_from_the_bigger_one(self, county_streets):
        (street,) = nearest_streets('GULF BLVD')
        assert (street.name, street.city, street.similarity) == ('GULF BLVD', 'Clearwater', 1)

    def test_a_stray_spelling_on_one_parcel_does_not_outrank_the_real_street(self, county_streets):
        """'GULF BLV' is closer to 'GULF BVLD' than 'GULF BLVD' is (0.46 against 0.43)."""
        make_parcel(7, '1800 GULF BLV')
        rebuild_street_names()

        assert [street.name for street in nearest_streets('GULF BVLD')] == ['GULF BLVD', 'GULF BLV']

    def test_a_clearly_better_spelling_still_wins_over_a_bigger_street(self, county_streets):
        for n in range(10, 16):
            make_parcel(n, f'{n} MANDALAY AVE')
        make_parcel(20, '5 MANDALAY PT')
        rebuild_street_names()

        assert nearest_streets('MANDALAY PT')[0].name == 'MANDALAY PT'

    def test_partial_and_misspelled_name(self, county_streets):
        assert [street.name for street in nearest_streets('MIRRER LAKE')] == ['MIRROR LAKE DR N']

    def test_nothing_close_enough(self, county_streets):
        assert nearest_streets('ZZYZX RD') == []

    def test_too_short_to_match_runs_no_query(self, county_streets, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert nearest_streets('GU') == []

    def test_missing_table_is_no_suggestions_not_an_error(self, county_streets):
        reader = '_nearest_in_postgres' if connection.vendor == 'postgresql' else '_nearest_in_python'
        with patch(f'apps.analytics.services.street_names.{reader}', side_effect=DatabaseError('no table')):
            assert nearest_streets('GULF BVLD') == []

    @pytest.mark.skipif(connection.vendor != 'postgresql', reason='pg_trgm is Postgres-only')
    def test_postgres_has_the_trigram_index(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, StreetName._meta.db_table)
        assert constraints['idx_street_name_trgm']['columns'] == ['name']

    def test_rebuilding_twice_gives_the_same_rows(self, county_streets):
        before = set(StreetName.objects.values_list('name', 'city', 'parcel_count'))

        assert rebuild_street_names() == len(before)
        assert set(StreetName.objects.values_list('name', 'city', 'parcel_count')) == before


@pytest.mark.django_db
class TestTypoTolerantLookup:
    def test_mistyped_street_type_finds_the_address(self, county_streets):
        result = lookup_parcels('1700 Gulf Bvld')

        assert [p.address for p in result.parcels] == ['1700 GULF BLVD', '1700 GULF BLVD # 2']
        assert result.corrected == '1700 GULF BLVD'
        assert result.nearby_streets == []

    def test_mistyped_street_name_without_a_house_number(self, county_streets):
        result = lookup_parcels('Mirrer Lake')

        assert [p.address for p in result.parcels] == ['701 MIRROR LAKE DR N # 307']
        assert result.corrected == 'MIRROR LAKE DR N'

    def test_mistyped_street_with_house_number_and_unit(self, county_streets):
        result = lookup_parcels('701 Miror Lake Dr N Apt 307')

        assert [p.address for p in result.parcels] == ['701 MIRROR LAKE DR N # 307']
        assert result.corrected == '701 MIRROR LAKE DR N'

    def test_correct_spelling_is_not_reported_as_a_correction(self, county_streets):
        result = lookup_parcels('1700 Gulf Blvd')

        assert len(result.parcels) == 2
        assert result.corrected == ''

    def test_exact_skips_the_retry_but_still_offers_the_streets(self, county_streets):
        result = lookup_parcels('1700 Gulf Bvld', exact=True)

        assert result.parcels == []
        assert result.corrected == ''
        assert [street.name for street in result.nearby_streets] == ['GULF BLVD']

    def test_right_street_wrong_number_offers_the_street(self, county_streets):
        result = lookup_parcels('99999 Gulf Blvd')

        assert result.parcels == []
        assert result.corrected == ''
        assert [street.name for street in result.nearby_streets] == ['GULF BLVD']

    def test_a_match_as_typed_never_reads_the_street_names(self, county_streets, django_assert_num_queries):
        # One EXISTS for the prefix, one read of the matches.
        with django_assert_num_queries(2):
            lookup_parcels('1700 gulf')

    def test_before_the_table_is_filled_lookup_behaves_as_before(self):
        make_parcel(1, '1700 GULF BLVD')

        result = lookup_parcels('1700 Gulf Bvld')

        assert result.parcels == []
        assert result.nearby_streets == []


@pytest.mark.django_db
class TestTypoTolerantLookupView:
    def test_says_what_it_searched_for_and_links_the_literal_search(self, client, county_streets):
        response = client.get('/lookup/', {'q': '1700 Gulf Bvld'})
        html = response.content.decode()

        assert response.status_code == 200
        assert 'Showing results for <span class="font-semibold text-charcoal-800">1700 GULF BLVD</span>' in html
        assert 'href="/lookup/?q=1700%20Gulf%20Bvld&amp;exact=1"' in html
        assert '2 matches for &ldquo;1700 GULF BLVD&rdquo;' in html
        assert 'No match' not in html

    def test_literal_search_shows_no_match_with_similar_streets(self, client, county_streets):
        html = client.get('/lookup/', {'q': '1700 Gulf Bvld', 'exact': '1'}).content.decode()

        assert 'No match for' in html
        assert 'Streets with a similar name' in html
        assert 'href="/lookup/?q=GULF%20BLVD"' in html

    def test_no_similar_streets_shows_only_the_hint(self, client, county_streets):
        html = client.get('/lookup/', {'q': '99999 Zzyzx Rd'}).content.decode()

        assert 'No match for' in html
        assert 'Streets with a similar name' not in html

    def test_corrected_results_stay_cacheable(self, client, county_streets):
        response = client.get('/lookup/', {'q': '1700 Gulf Bvld'})
        assert 's-maxage=86400' in response['Cache-Control']
        assert not response.cookies
