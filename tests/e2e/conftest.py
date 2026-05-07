"""Fixtures for E2E tests against a deployed app.

Set E2E_BASE_URL to point at a different deploy (preview, local). Defaults to production.
Set E2E_DATABASE_URL to enable functional tests that need to reset cache state between runs.
"""
import os
import re

import pytest
import requests

DEFAULT_BASE_URL = "https://homefinder.patbuilds.dev"
DEFAULT_TIMEOUT = 15
SCRAPE_TIMEOUT = 60
CSRF_RE = re.compile(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"')


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("E2E_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture
def client():
    session = requests.Session()
    session.headers.update({"User-Agent": "homefinder-e2e/1.0"})
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def known_parcel_id(base_url: str) -> str:
    """Pull a real parcel ID off the dashboard for use in detail-page tests.

    Avoids hardcoding a parcel that might disappear from the DB.
    """
    resp = requests.get(f"{base_url}/scraper/dashboard/", timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    match = re.search(r"/scraper/property/([0-9-]{20,})/", resp.text)
    if not match:
        pytest.skip("Dashboard has no property cards to use for detail-page tests")
    return match.group(1)


@pytest.fixture(autouse=True)
def use_simple_staticfiles_storage():
    """Override the Django-aware autouse fixture from the project's root conftest.

    E2E tests don't import Django; they only hit URLs over HTTP, so the
    settings-mutating parent fixture would crash if it tried to run.
    """
    yield


def _fetch_csrf(session: requests.Session, base_url: str) -> str:
    r = session.get(f"{base_url}/scraper/", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    match = CSRF_RE.search(r.text)
    assert match, "CSRF token not found on /scraper/ page"
    return match.group(1)


@pytest.fixture
def csrf_session(base_url):
    """Return (session, csrf_token) — session has the csrftoken cookie set."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "homefinder-e2e/1.0",
            "Referer": f"{base_url}/scraper/",
        }
    )
    csrf = _fetch_csrf(session, base_url)
    try:
        yield session, csrf
    finally:
        session.close()


@pytest.fixture
def reset_rate_limit():
    """Clear scrape rate-limit cache entries before the test.

    Required for functional tests that submit POSTs against an instance that
    enforces a 60s/IP rate limit. Skips the test if no DB access is configured.
    """
    db_url = os.environ.get("E2E_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip(
            "E2E_DATABASE_URL not set — cannot reset rate-limit cache between tests"
        )
    import psycopg2

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as c:
            c.execute(
                "DELETE FROM cache_table WHERE cache_key LIKE %s",
                ("%scrape_rate%",),
            )
            conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture
def db_query():
    """Yield a callable that runs a read-only query against the e2e DB."""
    db_url = os.environ.get("E2E_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("E2E_DATABASE_URL not set — cannot make DB-side assertions")
    import psycopg2

    conn = psycopg2.connect(db_url)

    def query(sql: str, params: tuple = ()):
        with conn.cursor() as c:
            c.execute(sql, params)
            return c.fetchall()

    try:
        yield query
    finally:
        conn.close()
