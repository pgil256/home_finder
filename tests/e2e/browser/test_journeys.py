"""Browser-driven journey tests via Playwright.

Tests JS-driven UI state and visual behavior that HTTP tests can't see.

Run headed (visible browser) for debugging: pytest tests/e2e/browser/ --headed
"""
import re

import pytest
from playwright.sync_api import Page, expect


SCRAPE_NAV_TIMEOUT_MS = 60_000


def test_B1_form_submit_navigates_to_dashboard(page: Page, base_url, reset_rate_limit):
    """Filling and submitting the search form ends up on the dashboard."""
    page.goto(f"{base_url}/scraper/")

    # Pick a city and a tiny limit to keep the scrape fast
    page.locator('select[name="city"]').select_option("Clearwater")
    page.locator('select[name="limit"]').select_option(index=0)

    submit = page.locator('button[type="submit"], input[type="submit"]').first

    # Capture the navigation triggered by submission
    with page.expect_navigation(timeout=SCRAPE_NAV_TIMEOUT_MS) as nav:
        submit.click()

    response = nav.value
    assert response, "expected a navigation response"
    assert "/scraper/dashboard/" in page.url, f"unexpected URL after submit: {page.url}"


def test_B2_form_is_wired_for_loading_state(page: Page, base_url):
    """The form has the data-loading-form attribute that triggers the spinner on submit.

    Catches regressions where the wiring is removed. Doesn't try to race the in-flight
    spinner against form navigation — that's timing-fragile in a deployed environment.
    """
    page.goto(f"{base_url}/scraper/")
    expect(page.locator("form#search-form")).to_have_attribute("data-loading-form", "")


def test_B3_property_card_click_navigates_to_detail(page: Page, base_url):
    """Clicking a property card on the dashboard navigates to its detail page."""
    page.goto(f"{base_url}/scraper/dashboard/")

    # Find the first link into a property detail page
    detail_link = page.locator('a[href*="/scraper/property/"]').first
    expect(detail_link).to_be_visible(timeout=5_000)

    href = detail_link.get_attribute("href")
    assert href and "/scraper/property/" in href, f"unexpected href: {href}"

    with page.expect_navigation():
        detail_link.click()

    assert re.search(r"/scraper/property/[\d-]+/?$", page.url), \
        f"unexpected URL after card click: {page.url}"


def test_B4_form_renders_in_mobile_viewport(browser, base_url):
    """At 375px wide (iPhone SE), the search form renders without horizontal scroll."""
    context = browser.new_context(viewport={"width": 375, "height": 667})
    page = context.new_page()
    try:
        page.goto(f"{base_url}/scraper/")

        # Form should be visible
        expect(page.locator("form#search-form")).to_be_visible()

        # No horizontal scroll: scrollWidth should not exceed clientWidth by a meaningful margin
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 1, f"horizontal overflow detected: {overflow}px"
    finally:
        context.close()


def test_B5_empty_dashboard_has_no_javascript_errors(page: Page, base_url):
    """An empty results page should not crash dashboard JavaScript."""
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(f"{base_url}/scraper/dashboard/?city=NotARealCity12345")
    expect(page.get_by_text("No Properties Found")).to_be_visible(timeout=5_000)

    assert errors == []
