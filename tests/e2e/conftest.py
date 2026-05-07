"""Fixtures for E2E tests against a deployed app.

Set E2E_BASE_URL to point at a different deploy (preview, local). Defaults to production.
"""
import os
import re

import pytest
import requests

DEFAULT_BASE_URL = "https://homefinder.patbuilds.dev"
DEFAULT_TIMEOUT = 15


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
