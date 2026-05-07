"""Functional tests — exercise write paths against the deployed app.

These tests POST real searches that hit PCPAO and write to Neon. Use small limits
(1-2 properties) to keep runs fast and minimize DB pollution.

Requires E2E_DATABASE_URL for rate-limit reset between tests. Without it,
tests that need a clean rate-limit slot are skipped.
"""
import re
import time

import pytest
import requests

from .conftest import CSRF_RE, DEFAULT_TIMEOUT, SCRAPE_TIMEOUT


def _fresh_csrf(session: requests.Session, base_url: str) -> str:
    r = session.get(f"{base_url}/scraper/", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return CSRF_RE.search(r.text).group(1)


def test_F1_basic_scrape_redirects_to_dashboard(csrf_session, base_url, reset_rate_limit):
    """POST with city + small limit returns 302 to dashboard with city filter applied."""
    session, csrf = csrf_session
    started = time.time()
    r = session.post(
        f"{base_url}/scraper/",
        data={
            "csrfmiddlewaretoken": csrf,
            "city": "Clearwater",
            "limit": "1",
        },
        timeout=SCRAPE_TIMEOUT,
        allow_redirects=False,
    )
    elapsed = time.time() - started
    assert r.status_code == 302, f"expected 302 redirect, got {r.status_code}: {r.text[:200]}"
    location = r.headers.get("Location", "")
    assert "/scraper/dashboard/" in location, f"unexpected redirect target: {location}"
    assert "city=Clearwater" in location, f"city filter missing from redirect: {location}"
    assert elapsed < SCRAPE_TIMEOUT, f"scrape took {elapsed:.1f}s, should be well under {SCRAPE_TIMEOUT}s"


def test_F2_rate_limit_blocks_rapid_second_submission(csrf_session, base_url, reset_rate_limit):
    """Two POSTs in quick succession: first 302s, second renders form with rate-limit error."""
    session, csrf = csrf_session
    r1 = session.post(
        f"{base_url}/scraper/",
        data={"csrfmiddlewaretoken": csrf, "city": "Clearwater", "limit": "1"},
        timeout=SCRAPE_TIMEOUT,
        allow_redirects=False,
    )
    assert r1.status_code == 302, f"first POST should succeed, got {r1.status_code}"

    csrf2 = _fresh_csrf(session, base_url)
    r2 = session.post(
        f"{base_url}/scraper/",
        data={"csrfmiddlewaretoken": csrf2, "city": "Clearwater", "limit": "1"},
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=False,
    )
    assert r2.status_code == 200, f"rate-limited POST should re-render form, got {r2.status_code}"
    assert re.search(r"please wait \d+ seconds", r2.text, re.I), \
        "expected rate-limit error message in response body"


def test_F3_oversized_limit_does_not_blow_timeout(csrf_session, base_url, reset_rate_limit):
    """Submitting limit=999 still completes — the view caps it at 25."""
    session, csrf = csrf_session
    started = time.time()
    r = session.post(
        f"{base_url}/scraper/",
        data={"csrfmiddlewaretoken": csrf, "city": "Clearwater", "limit": "999"},
        timeout=SCRAPE_TIMEOUT,
        allow_redirects=False,
    )
    elapsed = time.time() - started
    assert r.status_code == 302, f"expected 302, got {r.status_code}"
    assert elapsed < SCRAPE_TIMEOUT, \
        f"scrape took {elapsed:.1f}s — limit cap may not be working"


def test_F4_submit_with_no_filters_does_not_crash(csrf_session, base_url, reset_rate_limit):
    """POST with only limit (no city, no type) still 302s, doesn't 500."""
    session, csrf = csrf_session
    r = session.post(
        f"{base_url}/scraper/",
        data={"csrfmiddlewaretoken": csrf, "limit": "1"},
        timeout=SCRAPE_TIMEOUT,
        allow_redirects=False,
    )
    assert r.status_code == 302, f"expected 302, got {r.status_code}"


def test_F5_bogus_city_does_not_500(csrf_session, base_url, reset_rate_limit):
    """POST with a city that doesn't exist still 302s — empty result is OK, crash is not."""
    session, csrf = csrf_session
    r = session.post(
        f"{base_url}/scraper/",
        data={"csrfmiddlewaretoken": csrf, "city": "NotARealCity12345", "limit": "1"},
        timeout=SCRAPE_TIMEOUT,
        allow_redirects=False,
    )
    assert r.status_code == 302, f"bogus city should still redirect cleanly, got {r.status_code}"


def test_F6_dashboard_filters_chain_via_query_string(client, base_url):
    """Dashboard accepts city + property_types together without crashing."""
    r = client.get(
        f"{base_url}/scraper/dashboard/",
        params={"city": "Clearwater", "property_types": "Single Family"},
        timeout=DEFAULT_TIMEOUT,
    )
    assert r.status_code == 200
    # Page should reflect the filter state — selected city should appear in form
    assert "Clearwater" in r.text


def test_F7_dashboard_pagination_does_not_500(client, base_url):
    """Page 2 of dashboard returns 200 even if dataset is small."""
    r = client.get(
        f"{base_url}/scraper/dashboard/",
        params={"page": "2"},
        timeout=DEFAULT_TIMEOUT,
    )
    assert r.status_code == 200
