"""Functional tests against deployed search/filter paths."""

from .conftest import DEFAULT_TIMEOUT


def test_F1_old_filter_builder_link_redirects_with_filters(client, base_url):
    """A bookmarked filter-builder URL 301s to insights with its params in the URL."""
    r = client.get(
        f'{base_url}/analytics/',
        params={'city': 'Clearwater', 'min_price': '100000', 'max_price': '500000'},
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=False,
    )
    assert r.status_code == 301, f'expected 301, got {r.status_code}'
    location = r.headers.get('Location', '')
    assert '/insights/' in location, f'unexpected redirect: {location}'
    assert 'city=Clearwater' in location
    assert 'min_price=100000' in location
    assert 'max_price=500000' in location


def test_F2_insights_keeps_repeated_property_types(client, base_url):
    """Multi-value property_type fields filter together."""
    r = client.get(
        f'{base_url}/insights/',
        params=[('city', 'St. Petersburg'), ('property_type', 'Single Family'), ('property_type', 'Condo')],
        timeout=DEFAULT_TIMEOUT,
    )
    assert r.status_code == 200
    assert 'Type: Single Family, Condo' in r.text


def test_F4_insights_with_bogus_city_does_not_500(client, base_url):
    """A city that isn't in the dropdown renders an empty result, not an error."""
    r = client.get(f'{base_url}/insights/', params={'city': 'NotARealCity12345'}, timeout=DEFAULT_TIMEOUT)
    assert r.status_code == 200
    assert 'No properties match these filters' in r.text


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
    r = client.get(f'{base_url}/analytics/dashboard/', timeout=DEFAULT_TIMEOUT)
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
    assert 'The market at a glance' in r.text
    assert 'A few of these homes' in r.text
    assert 'No properties match these filters' not in r.text
