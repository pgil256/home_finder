"""Pages that are the same for every visitor must be cacheable by the CDN.

Vercel's edge only stores a response that asks for it with s-maxage, sets no
cookie and doesn't vary on the Cookie header. A session write or a rendered
CSRF token breaks that silently, so these tests pin it down per page.
"""

from unittest.mock import patch

import pytest
from django.contrib import messages
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.utils.cache import has_vary_header

from apps.analytics.models import PropertyListing
from apps.analytics.tests.factories import PropertyListingFactory
from home_finder.caching import cdn_cache
from home_finder.middleware import PrivateWhenPersonalMiddleware

pytestmark = pytest.mark.django_db

PARCEL_ID = '15-29-15-12345-000-0010'

CACHED_URLS = [
    '/',
    '/about/',
    '/help',
    '/robots.txt',
    '/lookup/',
    '/lookup/?q=no+such+street',
    '/lookup/suggest/?q=no+such+street',
    '/insights/',
    '/insights/?city=Clearwater&sort=city',
    f'/analytics/property/{PARCEL_ID}/',
    '/analytics/compare/',
    f'/analytics/compare/?ids={PARCEL_ID}',
]


@pytest.fixture
def parcel():
    return PropertyListingFactory(parcel_id=PARCEL_ID, city='Clearwater')


def assert_cdn_cacheable(response):
    cache_control = response['Cache-Control']
    assert 'public' in cache_control
    assert 's-maxage=86400' in cache_control
    assert 'stale-while-revalidate=604800' in cache_control
    assert 'max-age=0' in cache_control
    assert not response.cookies
    assert not has_vary_header(response, 'Cookie')


def assert_not_cdn_cacheable(response):
    cache_control = response.get('Cache-Control', '')
    assert 'public' not in cache_control
    assert 's-maxage' not in cache_control


class TestPublicPagesAreCdnCacheable:
    @pytest.mark.parametrize('url', CACHED_URLS)
    def test_page_can_be_stored_by_the_cdn(self, client, parcel, url):
        response = client.get(url)

        assert response.status_code == 200
        assert_cdn_cacheable(response)

    def test_lookup_redirect_to_the_only_match_is_cacheable(self, client, parcel):
        response = client.get('/lookup/', {'q': PARCEL_ID})

        assert response.status_code == 302
        assert_cdn_cacheable(response)

    def test_returning_visitor_with_old_cookies_gets_the_same_cacheable_page(self, parcel):
        """Cookies from before this change must not make the page personal again."""
        client = Client()
        client.get('/analytics/')  # the filter builder still sets a CSRF cookie
        assert 'csrftoken' in client.cookies

        response = client.get(f'/analytics/property/{PARCEL_ID}/')

        assert_cdn_cacheable(response)

    def test_parcel_page_has_no_csrf_token_in_its_html(self, client, parcel):
        html = client.get(f'/analytics/property/{PARCEL_ID}/').content.decode()

        assert 'csrfmiddlewaretoken' not in html
        assert 'data-csrf-url="/analytics/csrf/"' in html

    def test_missing_parcel_is_not_cached(self, client):
        response = client.get('/analytics/property/00-00-00-00000-000-0000/')

        assert response.status_code == 404
        assert_not_cdn_cacheable(response)


class TestPersonalResponsesStayOutOfTheCdn:
    def test_filter_builder_is_not_cached(self, client):
        """It renders a CSRF token for its POST form."""
        assert_not_cdn_cacheable(client.get('/analytics/'))

    def test_csrf_endpoint_is_never_cached_and_sets_the_cookie(self, client):
        response = client.get('/analytics/csrf/')

        assert response.status_code == 200
        assert response.json()['csrfToken']
        assert 'csrftoken' in response.cookies
        assert 'no-store' in response['Cache-Control']

    def test_exports_are_not_cached(self, client, parcel):
        assert_not_cdn_cacheable(client.get('/analytics/download/excel/'))

    def test_page_showing_a_flash_message_is_private(self, parcel):
        """Rendering `messages` consumes them, so that copy is for one visitor only."""
        client = Client(enforce_csrf_checks=True)
        token = client.get('/analytics/csrf/').json()['csrfToken']
        with patch('apps.analytics.tasks.scrape_data.refresh_one_parcel'):
            redirect = client.post(f'/analytics/property/{PARCEL_ID}/refresh/', {'csrfmiddlewaretoken': token})

        response = client.get(redirect.url)

        assert b'Property data refreshed' in response.content
        assert response['Cache-Control'] == 'private, no-store'

        # The message is gone, so the next view is the shared copy again.
        assert_cdn_cacheable(client.get(redirect.url))


class TestRefreshWithoutAnInlineToken:
    def test_refresh_without_a_token_is_rejected(self, parcel):
        client = Client(enforce_csrf_checks=True)

        response = client.post(f'/analytics/property/{PARCEL_ID}/refresh/')

        assert response.status_code == 403

    def test_refresh_lands_on_a_url_the_cdn_has_not_cached(self, client, parcel):
        with patch('apps.analytics.tasks.scrape_data.refresh_one_parcel'), patch('time.time', return_value=1760000000):
            response = client.post(f'/analytics/property/{PARCEL_ID}/refresh/')

        assert response.status_code == 302
        assert response.url == f'/analytics/property/{PARCEL_ID}/?refreshed=1760000000'

    def test_rate_limited_refresh_also_lands_on_an_uncached_url(self, client, parcel):
        with patch('apps.analytics.tasks.scrape_data.refresh_one_parcel'):
            client.post(f'/analytics/property/{PARCEL_ID}/refresh/')
            response = client.post(f'/analytics/property/{PARCEL_ID}/refresh/')

        assert '?refreshed=' in response.url
        assert b'just refreshed' in client.get(response.url).content

    def test_rate_limited_export_lands_on_an_uncached_url(self, client, parcel):
        client.get('/analytics/download/excel/')
        response = client.get('/analytics/download/excel/')

        assert response.status_code == 302
        assert response.url.startswith('/insights/?rate_limited=')
        page = client.get(response.url)
        assert b'Please wait' in page.content
        assert page['Cache-Control'] == 'private, no-store'
        assert PropertyListing.objects.count() == 1


class TestPrivateWhenPersonalMiddleware:
    """The safety net, independent of which views happen to set cookies today."""

    @staticmethod
    def respond(view):
        return PrivateWhenPersonalMiddleware(cdn_cache(view))(RequestFactory().get('/'))

    def test_leaves_a_shared_response_public(self):
        response = self.respond(lambda request: HttpResponse('same for everyone'))

        assert 's-maxage=86400' in response['Cache-Control']

    def test_withdraws_caching_when_a_cookie_is_set(self):
        def view(request):
            response = HttpResponse('hello, you')
            response.set_cookie('sessionid', 'abc')
            return response

        assert self.respond(view)['Cache-Control'] == 'private, no-store'

    def test_withdraws_caching_when_the_response_varies_on_cookie(self):
        def view(request):
            response = HttpResponse('depends who asks')
            response['Vary'] = 'Accept-Encoding, Cookie'
            return response

        assert self.respond(view)['Cache-Control'] == 'private, no-store'

    def test_leaves_uncached_responses_alone(self):
        def view(request):
            response = HttpResponse('plain')
            response.set_cookie('a', 'b')
            return response

        response = PrivateWhenPersonalMiddleware(view)(RequestFactory().get('/'))

        assert 'Cache-Control' not in response


def test_messages_template_does_not_touch_the_session(client, parcel):
    """base.html renders `messages` on every page; with none queued that must stay cookie-free."""
    response = client.get('/about/')

    assert list(messages.get_messages(response.wsgi_request)) == []
    assert not response.wsgi_request.session.accessed
