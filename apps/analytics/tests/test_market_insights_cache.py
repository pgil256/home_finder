"""Regression tests for the market insight cache and the DB-outage 503 path.

Context: the insight payload is built from a scan of up to MAX_ANALYSIS_ROWS
rows and three endpoints request it (dashboard, Excel export, PDF export). On a
metered Postgres that read was the app's dominant source of data transfer, and
an unthrottled scheduled monitor exhausted the provider's transfer quota, which
took production down. These tests pin the two behaviours that prevent a repeat:
the payload is cached per filter set, and a database connection failure reports
as 503 rather than masquerading as an application error.
"""

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import connection
from django.db.utils import InterfaceError, OperationalError, ProgrammingError
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.analytics.models import PropertyListing
from apps.analytics.services import market_insights as mi
from apps.analytics.services.market_insights import build_market_insights, insights_cache_key
from home_finder.middleware import RETRY_AFTER_SECONDS, DatabaseUnavailableMiddleware

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts from an empty cache; entries otherwise leak between tests."""
    cache.clear()
    yield
    cache.clear()


def _make_parcels(count: int = 5) -> None:
    for idx in range(count):
        PropertyListing.objects.create(
            parcel_id=f'cache-{idx:03d}',
            address=f'{idx} Cache Ct',
            city='Clearwater',
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal(200000 + idx * 1000),
            assessed_value=Decimal(180000 + idx * 1000),
            building_sqft=1200,
            year_built=1990 + idx,
            tax_amount=Decimal(2500),
        )


def _listing_reads(queries) -> list[str]:
    table = PropertyListing._meta.db_table
    return [q['sql'] for q in queries if table in q['sql'] and q['sql'].lstrip().upper().startswith('SELECT')]


class TestInsightsCacheKey:
    def test_none_request_has_a_stable_key(self):
        assert insights_cache_key(None) == insights_cache_key(None)

    def test_multi_value_param_order_does_not_matter(self):
        factory = RequestFactory()
        a = factory.get('/insights/', {'property_type': ['Condo', 'Single Family']})
        b = factory.get('/insights/', {'property_type': ['Single Family', 'Condo']})

        assert insights_cache_key(a) == insights_cache_key(b)

    def test_irrelevant_params_do_not_split_the_cache(self):
        """Tracking/pagination params don't reach the queryset, so they share a key."""
        factory = RequestFactory()
        plain = factory.get('/insights/', {'city': 'Clearwater'})
        noisy = factory.get('/insights/', {'city': 'Clearwater', 'utm_source': 'email', 'page': '3'})

        assert insights_cache_key(plain) == insights_cache_key(noisy)

    def test_different_filters_get_different_keys(self):
        factory = RequestFactory()
        clearwater = factory.get('/insights/', {'city': 'Clearwater'})
        largo = factory.get('/insights/', {'city': 'Largo'})

        assert insights_cache_key(clearwater) != insights_cache_key(largo)

    def test_empty_values_are_ignored(self):
        factory = RequestFactory()
        bare = factory.get('/insights/')
        blank = factory.get('/insights/', {'city': '   ', 'q': ''})

        assert insights_cache_key(bare) == insights_cache_key(blank)


class TestInsightsCaching:
    def test_second_call_does_not_re_read_the_table(self):
        _make_parcels()

        build_market_insights(None)
        with CaptureQueriesContext(connection) as ctx:
            build_market_insights(None)

        assert _listing_reads(ctx.captured_queries) == [], (
            'cached call still scanned the property table — the cache is not being hit'
        )

    def test_cached_payload_matches_a_fresh_computation(self):
        _make_parcels()

        fresh = build_market_insights(None, use_cache=False)
        build_market_insights(None)
        cached = build_market_insights(None)

        assert cached['exact']['parcel_count'] == fresh['exact']['parcel_count']
        assert cached['city_segments'] == fresh['city_segments']

    def test_different_filters_do_not_share_a_payload(self):
        _make_parcels()
        PropertyListing.objects.create(
            parcel_id='cache-largo',
            address='1 Largo Ln',
            city='Largo',
            zip_code='33770',
            property_type='Single Family',
            market_value=Decimal(400000),
            assessed_value=Decimal(380000),
            building_sqft=2000,
            year_built=2001,
            tax_amount=Decimal(5000),
        )
        factory = RequestFactory()

        clearwater = build_market_insights(factory.get('/insights/', {'city': 'Clearwater'}))
        largo = build_market_insights(factory.get('/insights/', {'city': 'Largo'}))

        assert clearwater['exact']['parcel_count'] == 5
        assert largo['exact']['parcel_count'] == 1

    def test_use_cache_false_always_recomputes(self):
        _make_parcels()

        build_market_insights(None)
        with CaptureQueriesContext(connection) as ctx:
            build_market_insights(None, use_cache=False)

        assert _listing_reads(ctx.captured_queries), 'use_cache=False should have hit the database'

    def test_ttl_of_zero_disables_caching(self, monkeypatch):
        _make_parcels()
        monkeypatch.setattr(mi, 'MARKET_INSIGHTS_CACHE_TTL', 0)

        build_market_insights(None)
        with CaptureQueriesContext(connection) as ctx:
            build_market_insights(None)

        assert _listing_reads(ctx.captured_queries), 'TTL=0 should bypass the cache entirely'

    def test_cache_read_failure_falls_back_to_computing(self, monkeypatch):
        """A broken cache backend must degrade to a slow page, not an error page."""
        _make_parcels()

        def _boom(*args, **kwargs):
            raise OperationalError('cache table unavailable')

        monkeypatch.setattr(mi.cache, 'get', _boom)
        monkeypatch.setattr(mi.cache, 'set', _boom)

        payload = build_market_insights(None)

        assert payload['exact']['parcel_count'] == 5


class TestDatabaseUnavailableMiddleware:
    @pytest.fixture
    def middleware(self):
        return DatabaseUnavailableMiddleware(lambda request: HttpResponse('ok'))

    @pytest.mark.parametrize('exception', [OperationalError('connection refused'), InterfaceError('connection closed')])
    def test_connection_errors_become_503(self, middleware, exception):
        request = RequestFactory().get('/insights/')

        response = middleware.process_exception(request, exception)

        assert response is not None
        assert response.status_code == 503
        assert response['Retry-After'] == str(RETRY_AFTER_SECONDS)

    def test_quota_exhaustion_becomes_503(self, middleware):
        """The exact failure that took production down: provider rejects the connection."""
        request = RequestFactory().get('/insights/')
        exception = OperationalError('ERROR: Your project has exceeded the data transfer quota.')

        response = middleware.process_exception(request, exception)

        assert response is not None
        assert response.status_code == 503

    @pytest.mark.parametrize('exception', [ProgrammingError('column does not exist'), ValueError('bad input')])
    def test_real_bugs_still_surface_as_errors(self, middleware, exception):
        """Schema and logic bugs must not be disguised as an outage."""
        request = RequestFactory().get('/insights/')

        assert middleware.process_exception(request, exception) is None

    def test_normal_requests_pass_through_untouched(self):
        middleware = DatabaseUnavailableMiddleware(lambda request: HttpResponse('ok', status=200))

        response = middleware(RequestFactory().get('/insights/'))

        assert response.status_code == 200
        assert response.content == b'ok'
