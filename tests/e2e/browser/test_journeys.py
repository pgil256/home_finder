"""Browser-driven journey tests via Playwright."""

import re

from playwright.sync_api import Page, expect

SCRAPE_NAV_TIMEOUT_MS = 60_000


def test_B1_form_submit_navigates_to_insights(page: Page, base_url):
    """Filling and submitting the filter builder ends up on the insights dashboard."""
    page.goto(f'{base_url}/scraper/')
    page.locator('select[name="city"]').select_option('Clearwater')

    submit = page.locator('button[type="submit"], input[type="submit"]').first
    with page.expect_navigation(timeout=SCRAPE_NAV_TIMEOUT_MS) as nav:
        submit.click()

    response = nav.value
    assert response, 'expected a navigation response'
    assert '/insights/' in page.url, f'unexpected URL after submit: {page.url}'


def test_B2_form_is_wired_for_loading_state(page: Page, base_url):
    """The compatibility form still has the data-loading-form spinner hook."""
    page.goto(f'{base_url}/scraper/')
    expect(page.locator('form#search-form')).to_have_attribute('data-loading-form', '')


def test_B3_sample_parcel_click_navigates_to_detail(page: Page, base_url):
    """Clicking a sample parcel drilldown navigates to the parcel detail page."""
    page.goto(f'{base_url}/insights/')

    detail_link = page.locator('a[href*="/scraper/property/"]').first
    expect(detail_link).to_be_visible(timeout=5_000)

    href = detail_link.get_attribute('href')
    assert href and '/scraper/property/' in href, f'unexpected href: {href}'

    with page.expect_navigation():
        detail_link.click()

    assert re.search(r'/scraper/property/[^/]+/?$', page.url), f'unexpected URL after drilldown click: {page.url}'


def test_B4_insights_renders_in_mobile_viewport(browser, base_url):
    """At 375px wide, the insights dashboard renders without horizontal scroll."""
    context = browser.new_context(viewport={'width': 375, 'height': 667})
    page = context.new_page()
    try:
        page.goto(f'{base_url}/insights/')
        expect(page.get_by_text('Pinellas Market Lens').first).to_be_visible()

        overflow = page.evaluate('() => document.documentElement.scrollWidth - document.documentElement.clientWidth')
        assert overflow <= 1, f'horizontal overflow detected: {overflow}px'
    finally:
        context.close()


def test_B5_empty_insights_has_no_javascript_errors(page: Page, base_url):
    """An empty analysis scope should not crash chart JavaScript."""
    errors = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))

    page.goto(f'{base_url}/insights/?city=NotARealCity12345')
    expect(page.get_by_text('No parcels match the current filters')).to_be_visible(timeout=5_000)

    assert errors == []
