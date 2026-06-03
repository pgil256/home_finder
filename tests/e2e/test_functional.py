"""Functional tests against deployed search/filter paths."""

import requests

from .conftest import CSRF_RE, DEFAULT_TIMEOUT


def _fresh_csrf(session: requests.Session, base_url: str) -> str:
    r = session.get(f'{base_url}/scraper/', timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return CSRF_RE.search(r.text).group(1)


def test_F1_search_redirects_with_filters_in_query(csrf_session, base_url):
    """POST with city + value range 302s to insights with those params in the URL."""
    session, csrf = csrf_session
    r = session.post(
        f'{base_url}/scraper/',
        data={
            'csrfmiddlewaretoken': csrf,
            'city': 'Clearwater',
            'min_price': '100000',
            'max_price': '500000',
        },
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=False,
    )
    assert r.status_code == 302, f'expected 302, got {r.status_code}'
    location = r.headers.get('Location', '')
    assert '/insights/' in location, f'unexpected redirect: {location}'
    assert 'city=Clearwater' in location
    assert 'min_price=100000' in location
    assert 'max_price=500000' in location


def test_F2_search_with_property_type_passes_through(csrf_session, base_url):
    """Multi-value property_type fields are preserved in the redirect URL."""
    session, csrf = csrf_session
    r = session.post(
        f'{base_url}/scraper/',
        data=[
            ('csrfmiddlewaretoken', csrf),
            ('city', 'St. Petersburg'),
            ('property_type', 'Single Family'),
            ('property_type', 'Condo'),
        ],
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=False,
    )
    assert r.status_code == 302
    location = r.headers['Location']
    assert location.count('property_type=') == 2, f'missing property_type repetition: {location}'


def test_F3_search_with_no_filters_redirects_to_insights(csrf_session, base_url):
    """Empty form still redirects to the unfiltered insights dashboard."""
    session, csrf = csrf_session
    r = session.post(
        f'{base_url}/scraper/',
        data={'csrfmiddlewaretoken': csrf},
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=False,
    )
    assert r.status_code == 302
    assert '/insights/' in r.headers['Location']


def test_F4_search_with_bogus_city_does_not_500(csrf_session, base_url):
    """A city that isn't in the dropdown still 302s; insights handles 0 results."""
    session, csrf = csrf_session
    r = session.post(
        f'{base_url}/scraper/',
        data={'csrfmiddlewaretoken': csrf, 'city': 'NotARealCity12345'},
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=False,
    )
    assert r.status_code == 302


def test_F5_insights_filters_chain_via_query_string(client, base_url):
    """Insights accepts city + property_types together without crashing."""
    r = client.get(
        f'{base_url}/insights/',
        params={'city': 'Clearwater', 'property_type': 'Single Family'},
        timeout=DEFAULT_TIMEOUT,
    )
    assert r.status_code == 200
    assert 'Clearwater' in r.text


def test_F6_legacy_dashboard_alias_does_not_500(client, base_url):
    """Legacy dashboard URL still returns 200 for compatibility."""
    r = client.get(f'{base_url}/scraper/dashboard/', timeout=DEFAULT_TIMEOUT)
    assert r.status_code == 200
    assert 'Pinellas Market Lens' in r.text


def test_F7_real_st_petersburg_analysis_returns_signals(client, base_url):
    """The original St. Petersburg slice should return market insight sections."""
    r = client.get(
        f'{base_url}/insights/',
        params={
            'city': 'St. Petersburg',
            'min_price': '4000',
            'max_price': '600000',
        },
        timeout=DEFAULT_TIMEOUT,
    )
    assert r.status_code == 200
    assert 'Exact Market KPIs' in r.text
    assert 'Sample Parcels' in r.text
    assert 'No parcels match the current filters' not in r.text
