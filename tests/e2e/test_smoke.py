"""Smoke tests against the deployed app. Read-only — safe to run on production.

Run with: make e2e-smoke
Override target: E2E_BASE_URL=https://preview.example.com make e2e-smoke
"""

TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30


def test_S1_home_loads(client, base_url):
    """Home page returns 200 and looks like the right app."""
    r = client.get(f'{base_url}/', timeout=TIMEOUT)
    assert r.status_code == 200
    assert 'Pinellas Market Lens' in r.text
    assert 'Find Your Perfect Home' not in r.text


def test_S2_scraper_form_loads(client, base_url):
    """Filter builder renders with city + property type fields."""
    r = client.get(f'{base_url}/scraper/', timeout=TIMEOUT)
    assert r.status_code == 200
    assert 'name="city"' in r.text
    assert 'name="property_type"' in r.text
    assert 'Build a Market Analysis' in r.text


def test_S3_insights_dashboard_renders(client, base_url):
    """Insights dashboard returns 200 and renders market analysis sections."""
    r = client.get(f'{base_url}/insights/', timeout=TIMEOUT)
    assert r.status_code == 200
    assert 'Exact Market KPIs' in r.text
    assert 'Auditable Outliers' in r.text
    assert 'market-insights-charts' in r.text


def test_S4_property_detail_loads(client, base_url, known_parcel_id):
    """Detail page for a real parcel returns 200 and shows the parcel ID."""
    r = client.get(f'{base_url}/scraper/property/{known_parcel_id}/', timeout=TIMEOUT)
    assert r.status_code == 200
    assert known_parcel_id in r.text


def test_S5_invalid_parcel_returns_404(client, base_url):
    """Detail page for a nonexistent parcel returns 404."""
    r = client.get(f'{base_url}/scraper/property/00-00-00-00000-000-0000/', timeout=TIMEOUT)
    assert r.status_code == 404


def test_S6_excel_download(client, base_url):
    """Excel download returns a valid .xlsx file."""
    r = client.get(f'{base_url}/scraper/download/excel/', timeout=DOWNLOAD_TIMEOUT)
    assert r.status_code == 200
    assert 'spreadsheetml' in r.headers.get('Content-Type', '')
    # xlsx is a zip; check magic bytes
    assert r.content[:2] == b'PK'


def test_S7_pdf_download(client, base_url):
    """PDF download returns a valid PDF file."""
    r = client.get(f'{base_url}/scraper/download/pdf/', timeout=DOWNLOAD_TIMEOUT)
    assert r.status_code == 200
    assert r.headers.get('Content-Type', '').startswith('application/pdf')
    assert r.content[:5] == b'%PDF-'


def test_S8_admin_login_loads(client, base_url):
    """Django admin login page loads."""
    r = client.get(f'{base_url}/admin/login/', timeout=TIMEOUT)
    assert r.status_code == 200
    assert 'username' in r.text.lower()


def test_S9_security_headers_present(client, base_url):
    """Site is HTTPS-only with HSTS and nosniff."""
    if base_url.startswith('http://'):
        import pytest

        pytest.skip('HTTPS/HSTS assertions only apply to deployed HTTPS targets')

    r = client.get(f'{base_url}/insights/', timeout=TIMEOUT)
    assert r.url.startswith('https://'), 'must be served over HTTPS'
    hsts = r.headers.get('Strict-Transport-Security', '')
    assert 'max-age' in hsts, f'missing HSTS, got: {hsts!r}'
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
