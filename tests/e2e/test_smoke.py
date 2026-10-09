"""Smoke tests against the deployed app. Read-only — safe to run on production.

Run with: make e2e-smoke
Override target: E2E_BASE_URL=https://preview.example.com make e2e-smoke

Tests marked `heavy` build a full export (workbook or PDF) over the filtered
table on the server. They are excluded from the daily scheduled run because
that read is the app's largest source of database egress; run them explicitly
with `-m heavy` or via the workflow's run_exports input.
"""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

import pytest

TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# The county file has about 437,000 parcels and is re-imported monthly.
MIN_PARCELS = 400_000
MAX_DATA_AGE = timedelta(days=45)


def assert_ok(response, expected: int = 200) -> None:
    """Assert a status code, naming a database outage explicitly when it happens.

    The app returns 503 when it can't reach its database. Without this the
    failure reads as a bare `assert 503 == 200`, which looks like an app bug
    and sends you into the code instead of into the database dashboard.
    """
    if response.status_code == 503:
        pytest.fail(
            f'{response.url} returned 503: the app is up but its database is unreachable. '
            'Check the database provider for an outage, a suspended instance, or an '
            'exceeded storage/data-transfer quota before looking at application code.'
        )
    assert response.status_code == expected


def test_S0_has_data(client, base_url):
    """The host is serving the full county dataset, and it isn't stale.

    First on purpose: when the database behind a host is empty or the wrong
    one, every later failure is a symptom of this one.
    """
    r = client.get(f'{base_url}/api/status/', timeout=TIMEOUT)
    assert_ok(r)
    status = r.json()

    total = status['total_properties']
    assert total >= MIN_PARCELS, (
        f'{base_url} reports {total:,} parcels, expected at least {MIN_PARCELS:,}. '
        'This host is pointed at an empty or wrong database, or the data was wiped.'
    )

    assert status['last_updated'], f'{base_url} has no last_updated timestamp'
    age = datetime.now(UTC) - datetime.fromisoformat(status['last_updated'])
    assert age <= MAX_DATA_AGE, (
        f'{base_url} data was last updated {age.days} days ago; the monthly refresh has stopped running.'
    )


def test_S0b_cdn_serves_html(client, base_url):
    """Behind Cloudflare, a repeat view of a page comes from Cloudflare's cache.

    Cloudflare does not cache HTML unless a Cache Rule tells it to, so without
    one the s-maxage the app sends is ignored there. Hosts that are not behind
    Cloudflare (the Vercel URL, a local server) are skipped.
    """
    first = client.get(f'{base_url}/', timeout=TIMEOUT)
    assert_ok(first)
    if 'cf-cache-status' not in first.headers:
        pytest.skip(f'{base_url} is not served through Cloudflare')

    second = client.get(f'{base_url}/', timeout=TIMEOUT)
    assert_ok(second)
    status = second.headers.get('cf-cache-status')
    # The first request can land just as the cached copy expires; either of
    # these means Cloudflare answered from its cache.
    assert status in {'HIT', 'REVALIDATED', 'UPDATING', 'STALE'}, (
        f'{base_url}/ returned cf-cache-status: {status} on a repeat request. '
        'Cloudflare is not caching HTML: check that the Cache Rule for this host exists '
        '(cache eligible, respect origin TTL) and is not bypassed for cookie-less requests.'
    )


def test_S1_home_loads(client, base_url):
    """Home page returns 200 and looks like the right app."""
    r = client.get(f'{base_url}/', timeout=TIMEOUT)
    assert_ok(r)
    assert 'Pinellas Market Lens' in r.text
    assert 'What will this home really cost me' in r.text
    assert 'action="/lookup/"' in r.text
    assert 'Find Your Perfect Home' not in r.text
    assert 'fonts.googleapis.com' not in r.text
    assert 'fonts.gstatic.com' not in r.text


def test_S1b_address_lookup_finds_a_parcel(client, base_url, known_parcel_id):
    """Looking up a real parcel's address lists it, quickly."""
    detail = client.get(f'{base_url}/analytics/property/{known_parcel_id}/', timeout=TIMEOUT)
    assert_ok(detail)
    match = re.search(r'openstreetmap\.org/search\?query=(\d+%20[A-Z0-9]+)', detail.text)
    if not match:
        pytest.skip('Known parcel has no house-number address to look up')
    query = unquote(match.group(1))

    r = client.get(f'{base_url}/lookup/', params={'q': query}, timeout=TIMEOUT)
    assert_ok(r)
    assert f'/analytics/property/{known_parcel_id}/' in r.text or 'First 25 matches' in r.text
    assert r.elapsed.total_seconds() < 3, f'lookup took {r.elapsed.total_seconds():.1f}s'


def test_S1c_address_lookup_no_match(client, base_url):
    """A lookup that matches nothing explains how to search, without erroring."""
    r = client.get(f'{base_url}/lookup/', params={'q': '99999 Nowhere Ln'}, timeout=TIMEOUT)
    assert_ok(r)
    assert 'No match for' in r.text


def test_S1e_mistyped_street_is_corrected(client, base_url):
    """A typo in the street finds the address anyway, and says what it searched for."""
    r = client.get(f'{base_url}/lookup/', params={'q': '1029 Charels St'}, timeout=TIMEOUT)
    assert_ok(r)
    assert 'Showing results for' in r.text, (
        'No spelling correction. If the lookup page otherwise works, the street-name table is '
        'probably empty: run the "Database guard" workflow, which fills it.'
    )
    assert 'CHARLES' in r.text


def test_S1d_address_suggestions(client, base_url):
    """Typing the start of an address lists the parcel, fast enough to feel instant."""
    r = client.get(f'{base_url}/lookup/suggest/', params={'q': '1029 cha'}, timeout=TIMEOUT)
    assert_ok(r)
    addresses = [row['address'] for row in r.json()['results']]
    assert '1029 CHARLES ST' in addresses
    assert r.elapsed.total_seconds() < 1, f'suggestions took {r.elapsed.total_seconds():.1f}s'


def test_S2_old_filter_builder_redirects_to_the_market_page(client, base_url):
    """/analytics/ was a separate filter form; old links land on the market page, filters intact."""
    r = client.get(f'{base_url}/analytics/', params={'city': 'Dunedin'}, timeout=TIMEOUT)
    assert_ok(r)
    assert [hop.status_code for hop in r.history] == [301]
    assert r.url.endswith('/insights/?city=Dunedin')
    assert 'name="city"' in r.text
    assert 'name="property_type"' in r.text
    # The monthly-budget search moved here with the filters.
    assert 'id="budget-monthly"' in r.text


def test_S3_insights_dashboard_renders(client, base_url):
    """Insights dashboard returns 200 and renders market analysis sections."""
    r = client.get(f'{base_url}/insights/', timeout=TIMEOUT)
    assert_ok(r)
    assert 'The market at a glance' in r.text
    assert 'Homes that stand out, and why' in r.text
    assert 'Public records EDA' not in r.text
    assert 'market-insights-charts' in r.text


def test_S4_property_detail_loads(client, base_url, known_parcel_id):
    """Detail page for a real parcel returns 200 and shows the parcel ID."""
    r = client.get(f'{base_url}/analytics/property/{known_parcel_id}/', timeout=TIMEOUT)
    assert_ok(r)
    assert known_parcel_id in r.text
    assert 'maps.googleapis.com' not in r.text
    assert 'google.com/maps' not in r.text
    assert 'https://www.openstreetmap.org/search?query=' in r.text


def test_S4b_paid_street_view_route_is_gone(client, base_url, known_parcel_id):
    """The retired paid image endpoint stays unavailable."""
    r = client.get(f'{base_url}/analytics/property/{known_parcel_id}/streetview/', timeout=TIMEOUT)
    assert_ok(r, 404)


def test_S5_invalid_parcel_returns_404(client, base_url):
    """Detail page for a nonexistent parcel returns 404."""
    r = client.get(f'{base_url}/analytics/property/00-00-00-00000-000-0000/', timeout=TIMEOUT)
    assert_ok(r, 404)
    # A styled page with a way forward, not a bare "Not Found".
    assert 'Pinellas Market Lens' in r.text
    assert 'action="/lookup/"' in r.text


@pytest.mark.heavy
def test_S6_excel_download(client, base_url):
    """Excel download returns a valid .xlsx file."""
    r = client.get(f'{base_url}/analytics/download/excel/', timeout=DOWNLOAD_TIMEOUT)
    assert_ok(r)
    assert 'spreadsheetml' in r.headers.get('Content-Type', '')
    # xlsx is a zip; check magic bytes
    assert r.content[:2] == b'PK'


@pytest.mark.heavy
def test_S7_pdf_download(client, base_url):
    """PDF download returns a valid PDF file."""
    r = client.get(f'{base_url}/analytics/download/pdf/', timeout=DOWNLOAD_TIMEOUT)
    assert_ok(r)
    assert r.headers.get('Content-Type', '').startswith('application/pdf')
    assert r.content[:5] == b'%PDF-'


def test_S8_admin_login_loads(client, base_url):
    """Django admin login page loads."""
    r = client.get(f'{base_url}/admin/login/', timeout=TIMEOUT)
    assert_ok(r)
    assert 'username' in r.text.lower()


def test_S9_security_headers_present(client, base_url):
    """Site is HTTPS-only with HSTS and nosniff."""
    if base_url.startswith('http://'):
        pytest.skip('HTTPS/HSTS assertions only apply to deployed HTTPS targets')

    r = client.get(f'{base_url}/insights/', timeout=TIMEOUT)
    assert r.url.startswith('https://'), 'must be served over HTTPS'
    hsts = r.headers.get('Strict-Transport-Security', '')
    assert 'max-age' in hsts, f'missing HSTS, got: {hsts!r}'
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
