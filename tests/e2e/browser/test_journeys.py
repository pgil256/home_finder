"""Browser-driven journey tests via Playwright."""

import re

from playwright.sync_api import Page, expect

SCRAPE_NAV_TIMEOUT_MS = 60_000


def test_B1_filter_panel_submit_filters_the_market_page(page: Page, base_url):
    """Choosing a city in the filter panel and submitting reloads insights with it applied."""
    page.goto(f'{base_url}/insights/')
    page.locator('select[name="city"]').select_option('Clearwater')

    with page.expect_navigation(timeout=SCRAPE_NAV_TIMEOUT_MS) as nav:
        page.get_by_role('button', name='Show results').click()

    assert nav.value, 'expected a navigation response'
    assert '/insights/' in page.url and 'city=Clearwater' in page.url, f'unexpected URL after submit: {page.url}'


def test_B2_monthly_budget_fills_the_maximum_value(page: Page, base_url):
    """Typing a monthly budget writes a maximum market value into the filter form."""
    page.goto(f'{base_url}/insights/')
    page.locator('#budget-monthly').fill('2800')

    expect(page.locator('#max_value')).not_to_have_value('')
    expect(page.locator('#budget-result')).to_contain_text('About $')


def test_B3_sample_parcel_click_navigates_to_detail(page: Page, base_url):
    """Clicking a sample parcel drilldown navigates to the parcel detail page."""
    page.goto(f'{base_url}/insights/')

    detail_link = page.locator('a[href*="/analytics/property/"]').first
    expect(detail_link).to_be_visible(timeout=5_000)

    href = detail_link.get_attribute('href')
    assert href and '/analytics/property/' in href, f'unexpected href: {href}'

    with page.expect_navigation():
        detail_link.click()

    assert re.search(r'/analytics/property/[^/]+/?$', page.url), f'unexpected URL after drilldown click: {page.url}'


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
    expect(page.get_by_text('No properties match these filters').first).to_be_visible(timeout=5_000)

    assert errors == []
