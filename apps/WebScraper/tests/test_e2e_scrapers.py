"""
End-to-End Tests for Web Scraping Utilities

These tests verify the complete scraping workflow using HTML fixtures
to test the actual BeautifulSoup parsing logic without requiring
live browser automation.
"""

import os
import pytest
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime

from bs4 import BeautifulSoup

from apps.WebScraper.models import PropertyListing

pytestmark = [pytest.mark.django_db]

FIXTURES_DIR = Path(__file__).parent / 'fixtures'


def load_fixture(filename: str) -> str:
    """Load HTML fixture file content."""
    with open(FIXTURES_DIR / filename, 'r') as f:
        return f.read()


@pytest.fixture(autouse=True)
def mock_time_sleep():
    """Auto-mock time.sleep for all tests to prevent delays."""
    with patch('apps.WebScraper.tasks.pcpao_scraper.time.sleep'):
        with patch('apps.WebScraper.tasks.tax_collector_scraper.time.sleep'):
            yield


@pytest.fixture
def mock_chrome_paths():
    """Mock Chrome binary path checks to always use webdriver-manager."""
    with patch('apps.WebScraper.tasks.pcpao_scraper.os.path.exists', return_value=False):
        with patch('apps.WebScraper.tasks.tax_collector_scraper.os.path.exists', return_value=False):
            yield


class TestPCPAOScraperHTMLParsing:
    """Test PCPAO scraper HTML parsing with real HTML fixtures."""

    def test_extract_parcels_from_search_results(self, mock_chrome_paths):
        """Test parcel extraction from search results page."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        mock_driver = MagicMock()
        mock_driver.page_source = load_fixture('pcpao_search_results.html')
        scraper.driver = mock_driver

        existing_ids = set()
        parcels = scraper._extract_parcels_from_page(existing_ids)

        assert len(parcels) == 4
        assert parcels[0]['parcel_id'] == '14-31-15-91961-004-0110'
        assert parcels[1]['parcel_id'] == '14-31-15-91961-004-0120'
        assert parcels[2]['parcel_id'] == '14-31-15-91961-004-0130'
        assert parcels[3]['parcel_id'] == '14-31-15-91961-004-0140'

    def test_extract_parcels_deduplicates(self, mock_chrome_paths):
        """Test that existing parcel IDs are not re-extracted."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        mock_driver = MagicMock()
        mock_driver.page_source = load_fixture('pcpao_search_results.html')
        scraper.driver = mock_driver

        existing_ids = {'14-31-15-91961-004-0110', '14-31-15-91961-004-0120'}
        parcels = scraper._extract_parcels_from_page(existing_ids)

        assert len(parcels) == 2
        parcel_ids = [p['parcel_id'] for p in parcels]
        assert '14-31-15-91961-004-0110' not in parcel_ids
        assert '14-31-15-91961-004-0120' not in parcel_ids
        assert '14-31-15-91961-004-0130' in parcel_ids
        assert '14-31-15-91961-004-0140' in parcel_ids

    def test_extract_parcels_builds_correct_urls(self, mock_chrome_paths):
        """Test that detail URLs are correctly constructed."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        mock_driver = MagicMock()
        mock_driver.page_source = load_fixture('pcpao_search_results.html')
        scraper.driver = mock_driver

        existing_ids = set()
        parcels = scraper._extract_parcels_from_page(existing_ids)

        # Relative URL should be converted to absolute
        assert parcels[0]['detail_url'].startswith('https://www.pcpao.gov/')
        assert 'property-details' in parcels[0]['detail_url']

        # Absolute URL should be kept as-is
        assert parcels[3]['detail_url'] == 'https://www.pcpao.gov/property-details?strap=143115919610040140'

    def test_extract_parcels_from_empty_results(self, mock_chrome_paths):
        """Test parcel extraction from empty search results."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        mock_driver = MagicMock()
        mock_driver.page_source = load_fixture('pcpao_empty_results.html')
        scraper.driver = mock_driver

        existing_ids = set()
        parcels = scraper._extract_parcels_from_page(existing_ids)

        assert len(parcels) == 0

    def test_extract_parcel_ids_legacy_method(self, mock_chrome_paths):
        """Test legacy method returns only parcel IDs."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        mock_driver = MagicMock()
        mock_driver.page_source = load_fixture('pcpao_search_results.html')
        scraper.driver = mock_driver

        existing_ids = set()
        parcel_ids = scraper._extract_parcel_ids_from_page(existing_ids)

        assert len(parcel_ids) == 4
        assert all(isinstance(pid, str) for pid in parcel_ids)
        assert parcel_ids[0] == '14-31-15-91961-004-0110'


class TestPCPAOScraperDetailParsing:
    """Test PCPAO property detail parsing."""

    def test_get_h2_value_extracts_living_sf(self, mock_chrome_paths):
        """Test _get_h2_value extracts Living SF correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_h2_value(soup, 'Living SF')
        assert value == '1,450'

    def test_get_h2_value_extracts_gross_sf(self, mock_chrome_paths):
        """Test _get_h2_value extracts Gross SF correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_h2_value(soup, 'Gross SF')
        assert value == '1,650'

    def test_get_h2_value_extracts_buildings(self, mock_chrome_paths):
        """Test _get_h2_value extracts Buildings count correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_h2_value(soup, 'Buildings')
        assert value == '1'

    def test_get_h2_value_returns_none_for_missing(self, mock_chrome_paths):
        """Test _get_h2_value returns None for non-existent label."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_h2_value(soup, 'Nonexistent Field')
        assert value is None

    def test_get_sibling_value_extracts_owner_name(self, mock_chrome_paths):
        """Test _get_sibling_value extracts Owner Name correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_sibling_value(soup, 'Owner Name')
        assert value == 'SmithJohnMore'

    def test_get_sibling_value_extracts_year_built(self, mock_chrome_paths):
        """Test _get_sibling_value extracts Year Built correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_sibling_value(soup, 'Year Built')
        assert value == '1987'

    def test_get_sibling_value_extracts_property_use(self, mock_chrome_paths):
        """Test _get_sibling_value extracts Property Use correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_sibling_value(soup, 'Property Use')
        assert value == 'Single Family Residential'

    def test_get_sibling_value_returns_none_for_missing(self, mock_chrome_paths):
        """Test _get_sibling_value returns None for non-existent label."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_sibling_value(soup, 'Nonexistent Field')
        assert value is None

    def test_get_address_parts_extracts_full_address(self, mock_chrome_paths):
        """Test _get_address_parts extracts address, city, and zip."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        address_parts = scraper._get_address_parts(soup)

        assert address_parts.get('address') == '123 MAIN ST'
        assert address_parts.get('city') == 'Clearwater'
        assert address_parts.get('zip_code') == '33755'

    def test_get_parcel_from_page(self, mock_chrome_paths):
        """Test _get_parcel_from_page extracts parcel ID from h2."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        parcel_id = scraper._get_parcel_from_page(soup)
        assert parcel_id == '14-31-15-91961-004-0110'

    def test_get_valuation_data_extracts_market_value(self, mock_chrome_paths):
        """Test _get_valuation_data extracts market value."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        valuation = scraper._get_valuation_data(soup)

        assert valuation.get('market_value') == 245000.0
        assert valuation.get('assessed_value') == 220500.0

    def test_extract_property_image_finds_image(self, mock_chrome_paths):
        """Test _extract_property_image extracts image URL from detail page."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = load_fixture('pcpao_property_details.html')
        soup = BeautifulSoup(html, 'html.parser')

        image_url = scraper._extract_property_image(soup)

        assert image_url is not None
        assert image_url.endswith('/images/properties/14311591961.jpg')
        assert image_url.startswith('https://www.pcpao.gov')

    def test_extract_property_image_handles_various_selectors(self, mock_chrome_paths):
        """Test _extract_property_image tries multiple CSS selectors."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()

        # Test with img.property-image selector
        html = '<html><body><img class="property-image" src="/photo.jpg"></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        image_url = scraper._extract_property_image(soup)
        assert image_url == 'https://www.pcpao.gov/photo.jpg'

        # Test with alt attribute selector
        html = '<html><body><img alt="Property view" src="https://example.com/img.jpg"></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        image_url = scraper._extract_property_image(soup)
        assert image_url == 'https://example.com/img.jpg'

    def test_extract_property_image_handles_protocol_relative_urls(self, mock_chrome_paths):
        """Test _extract_property_image handles //example.com style URLs."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = '<html><body><img class="property-image" src="//cdn.example.com/photo.jpg"></body></html>'
        soup = BeautifulSoup(html, 'html.parser')

        image_url = scraper._extract_property_image(soup)

        assert image_url == 'https://cdn.example.com/photo.jpg'

    def test_extract_property_image_returns_none_when_no_image(self, mock_chrome_paths):
        """Test _extract_property_image returns None when no suitable image found."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = '<html><body><img src="/logo.png" alt="Logo" width="50" height="50"></body></html>'
        soup = BeautifulSoup(html, 'html.parser')

        image_url = scraper._extract_property_image(soup)

        assert image_url is None

    def test_extract_property_image_skips_small_icons(self, mock_chrome_paths):
        """Test _extract_property_image skips small images like icons."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        html = '''<html><body>
            <img src="/icon.png" width="16" height="16">
            <img src="/button.gif" alt="button">
            <img src="/logo.png" alt="company logo">
        </body></html>'''
        soup = BeautifulSoup(html, 'html.parser')

        image_url = scraper._extract_property_image(soup)

        # Should skip all these images
        assert image_url is None


class TestPCPAOScraperFullWorkflow:
    """Test complete PCPAO scraping workflow with mocked WebDriver."""

    def test_scrape_property_details_full_extraction(self, mock_chrome_paths):
        """Test scrape_property_details extracts all fields correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        import apps.WebScraper.tasks.pcpao_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            mock_driver.page_source = load_fixture('pcpao_property_details.html')
            mock_driver.current_url = 'https://www.pcpao.gov/property-details?strap=143115919610040110'

            scraper = PCPAOScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()

            result = scraper.scrape_property_details(
                '14-31-15-91961-004-0110',
                detail_url='https://www.pcpao.gov/property-details?strap=143115919610040110'
            )

            assert result['parcel_id'] == '14-31-15-91961-004-0110'
            assert result['address'] == '123 MAIN ST'
            assert result['city'] == 'Clearwater'
            assert result['zip_code'] == '33755'
            assert result['year_built'] == 1987
            assert result['building_sqft'] == 1450
            assert result['gross_sqft'] == 1650
            assert result['property_type'] == 'Single Family Residential'
            assert result['market_value'] == 245000.0
            assert result['assessed_value'] == 220500.0
            assert result['appraiser_url'] == 'https://www.pcpao.gov/property-details?strap=143115919610040110'
            assert result['image_url'] == 'https://www.pcpao.gov/images/properties/14311591961.jpg'

    def test_scrape_property_details_cleans_owner_name(self, mock_chrome_paths):
        """Test that owner name is cleaned (More suffix removed, spaces added)."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        import apps.WebScraper.tasks.pcpao_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            mock_driver.page_source = load_fixture('pcpao_property_details.html')
            mock_driver.current_url = 'https://www.pcpao.gov/property-details'

            scraper = PCPAOScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()

            result = scraper.scrape_property_details('14-31-15-91961-004-0110', detail_url='http://test')

            # Owner name should have "More" removed and space added between names
            assert result['owner_name'] == 'Smith John'

    def test_search_properties_with_urls_pagination_simulation(self, mock_chrome_paths):
        """Test search handles multiple pages of results."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.common.by import By
        import apps.WebScraper.tasks.pcpao_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver

            # First page has results
            page1_html = load_fixture('pcpao_search_results.html')
            # Second page has empty results (simulating end of pagination)
            page2_html = load_fixture('pcpao_empty_results.html')

            page_sources = [page1_html, page2_html, page2_html, page2_html]
            page_index = [0]

            def get_page_source():
                idx = min(page_index[0], len(page_sources) - 1)
                return page_sources[idx]

            type(mock_driver).page_source = PropertyMock(side_effect=get_page_source)

            mock_search_input = MagicMock()
            mock_next_button = MagicMock()

            click_count = [0]

            def find_element_side_effect(by, selector):
                if by == By.ID and selector == 'txtKeyWord':
                    return mock_search_input
                if by == By.CSS_SELECTOR and 'paginate_button.next' in selector:
                    click_count[0] += 1
                    if click_count[0] <= 3:
                        page_index[0] += 1
                        return mock_next_button
                    raise NoSuchElementException()
                raise NoSuchElementException()

            mock_driver.find_element.side_effect = find_element_side_effect

            scraper = PCPAOScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()
            scraper.wait.until = MagicMock(return_value=mock_search_input)

            results = scraper.search_properties_with_urls({'city': 'Clearwater'})

            # Should have found the 4 parcels from page 1
            assert len(results) == 4
            mock_driver.get.assert_called()

    def test_scrape_by_criteria_full_workflow(self, mock_chrome_paths):
        """Test scrape_by_criteria orchestrates the full scraping workflow.

        Note: With parallel scraping, setup_driver/close_driver are called multiple times:
        once for the initial search, and once per worker thread.
        """
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        with patch.object(PCPAOScraper, 'setup_driver') as mock_setup:
            with patch.object(PCPAOScraper, 'close_driver') as mock_close:
                with patch.object(PCPAOScraper, 'search_properties_with_urls') as mock_search:
                    with patch.object(PCPAOScraper, 'scrape_property_details') as mock_details:
                        mock_search.return_value = [
                            {'parcel_id': '14-31-15-91961-004-0110', 'detail_url': 'http://test1'},
                            {'parcel_id': '14-31-15-91961-004-0120', 'detail_url': 'http://test2'},
                            {'parcel_id': '14-31-15-91961-004-0130', 'detail_url': 'http://test3'},
                        ]
                        mock_details.side_effect = [
                            {'parcel_id': '14-31-15-91961-004-0110', 'address': '123 Main St', 'market_value': 245000},
                            {'parcel_id': '14-31-15-91961-004-0120', 'address': '456 Oak Ave', 'market_value': 320000},
                            {'parcel_id': '14-31-15-91961-004-0130', 'address': '789 Beach Dr', 'market_value': 185000},
                        ]

                        scraper = PCPAOScraper()
                        results = scraper.scrape_by_criteria({'city': 'Clearwater'})

                        # setup_driver called once for search + once per worker (parallel scraping)
                        assert mock_setup.call_count >= 1
                        mock_search.assert_called_once_with({'city': 'Clearwater'})
                        assert mock_details.call_count == 3
                        # close_driver called once for search + once per worker
                        assert mock_close.call_count >= 1
                        assert len(results) == 3
                        assert results[0]['market_value'] == 245000
                        assert results[1]['market_value'] == 320000
                        assert results[2]['market_value'] == 185000

    def test_scrape_by_criteria_with_limit(self, mock_chrome_paths):
        """Test scrape_by_criteria respects the limit parameter."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        with patch.object(PCPAOScraper, 'setup_driver'):
            with patch.object(PCPAOScraper, 'close_driver'):
                with patch.object(PCPAOScraper, 'search_properties_with_urls') as mock_search:
                    with patch.object(PCPAOScraper, 'scrape_property_details') as mock_details:
                        mock_search.return_value = [
                            {'parcel_id': f'14-31-15-91961-004-{i:04d}', 'detail_url': f'http://test{i}'}
                            for i in range(10)
                        ]
                        mock_details.return_value = {'parcel_id': 'test', 'address': 'Test'}

                        scraper = PCPAOScraper()
                        results = scraper.scrape_by_criteria({'city': 'Clearwater'}, limit=3)

                        assert mock_details.call_count == 3
                        assert len(results) == 3

    def test_scrape_by_criteria_closes_driver_on_error(self, mock_chrome_paths):
        """Test that driver is closed even when an error occurs."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        with patch.object(PCPAOScraper, 'setup_driver'):
            with patch.object(PCPAOScraper, 'close_driver') as mock_close:
                with patch.object(PCPAOScraper, 'search_properties_with_urls') as mock_search:
                    mock_search.side_effect = Exception("Network error")

                    scraper = PCPAOScraper()

                    with pytest.raises(Exception, match="Network error"):
                        scraper.scrape_by_criteria({'city': 'Clearwater'})

                    # Driver should still be closed via finally block
                    mock_close.assert_called_once()


class TestTaxCollectorScraperHTMLParsing:
    """Test Tax Collector scraper HTML parsing with real HTML fixtures."""

    def test_get_table_value_extracts_tax_amount(self, mock_chrome_paths):
        """Test _get_table_value extracts Total Tax correctly."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        html = load_fixture('tax_collector_results.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_table_value(soup, 'Total Tax')
        assert value == '$3,125.50'

    def test_get_table_value_extracts_status(self, mock_chrome_paths):
        """Test _get_table_value extracts Status correctly."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        html = load_fixture('tax_collector_results.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_table_value(soup, 'Status')
        assert value == 'PAID'

    def test_get_table_value_extracts_tax_year(self, mock_chrome_paths):
        """Test _get_table_value extracts Tax Year correctly."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        html = load_fixture('tax_collector_results.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_table_value(soup, 'Tax Year')
        assert value == '2024'

    def test_get_table_value_returns_none_for_missing(self, mock_chrome_paths):
        """Test _get_table_value returns None for non-existent label."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        html = load_fixture('tax_collector_results.html')
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_table_value(soup, 'Nonexistent Field')
        assert value is None


class TestTaxCollectorScraperFullWorkflow:
    """Test complete Tax Collector scraping workflow with mocked WebDriver."""

    def test_scrape_tax_info_paid_status(self, mock_chrome_paths):
        """Test scrape_tax_info correctly parses paid status."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        import apps.WebScraper.tasks.tax_collector_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            mock_driver.page_source = load_fixture('tax_collector_results.html')
            mock_driver.current_url = 'https://pinellastaxcollector.gov/search-results/?search=14-31-15-91961-004-0110'

            scraper = TaxCollectorScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()

            result = scraper.scrape_tax_info('14-31-15-91961-004-0110')

            assert result['parcel_id'] == '14-31-15-91961-004-0110'
            assert result['tax_amount'] == 3125.50
            assert result['tax_year'] == 2024
            assert result['tax_status'] == 'Paid'
            assert result['delinquent'] is False

    def test_scrape_tax_info_delinquent_status(self, mock_chrome_paths):
        """Test scrape_tax_info correctly parses delinquent status."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        import apps.WebScraper.tasks.tax_collector_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            mock_driver.page_source = load_fixture('tax_collector_delinquent.html')
            mock_driver.current_url = 'https://pinellastaxcollector.gov/search-results/?search=14-31-15-91961-004-0120'

            scraper = TaxCollectorScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()

            result = scraper.scrape_tax_info('14-31-15-91961-004-0120')

            assert result['parcel_id'] == '14-31-15-91961-004-0120'
            assert result['tax_amount'] == 4567.89
            assert result['tax_status'] == 'Delinquent'
            assert result['delinquent'] is True

    def test_scrape_tax_info_no_results(self, mock_chrome_paths):
        """Test scrape_tax_info handles no results gracefully."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        import apps.WebScraper.tasks.tax_collector_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            mock_driver.page_source = load_fixture('tax_collector_no_results.html')
            mock_driver.current_url = 'https://pinellastaxcollector.gov/search-results/'

            scraper = TaxCollectorScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()

            result = scraper.scrape_tax_info('invalid-parcel-id')

            assert result['parcel_id'] == 'invalid-parcel-id'
            assert result['tax_status'] == 'Not Found'
            assert result['delinquent'] is False

    def test_scrape_batch_processes_multiple_parcels(self, mock_chrome_paths):
        """Test scrape_batch processes a list of parcel IDs."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        with patch.object(TaxCollectorScraper, 'setup_driver') as mock_setup:
            with patch.object(TaxCollectorScraper, 'close_driver') as mock_close:
                with patch.object(TaxCollectorScraper, 'scrape_tax_info') as mock_scrape:
                    mock_scrape.side_effect = [
                        {'parcel_id': 'p1', 'tax_amount': 1000, 'tax_status': 'Paid', 'delinquent': False},
                        {'parcel_id': 'p2', 'tax_amount': 2000, 'tax_status': 'Unpaid', 'delinquent': False},
                        {'parcel_id': 'p3', 'tax_amount': 3000, 'tax_status': 'Delinquent', 'delinquent': True},
                    ]

                    scraper = TaxCollectorScraper()
                    results = scraper.scrape_batch(['p1', 'p2', 'p3'])

                    mock_setup.assert_called_once()
                    assert mock_scrape.call_count == 3
                    mock_close.assert_called_once()

                    assert len(results) == 3
                    assert results[0]['tax_amount'] == 1000
                    assert results[1]['tax_status'] == 'Unpaid'
                    assert results[2]['delinquent'] is True

    def test_scrape_batch_closes_driver_on_error(self, mock_chrome_paths):
        """Test scrape_batch closes driver even when error occurs."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        with patch.object(TaxCollectorScraper, 'setup_driver'):
            with patch.object(TaxCollectorScraper, 'close_driver') as mock_close:
                with patch.object(TaxCollectorScraper, 'scrape_tax_info') as mock_scrape:
                    mock_scrape.side_effect = Exception("Unexpected error")

                    scraper = TaxCollectorScraper()

                    with pytest.raises(Exception, match="Unexpected error"):
                        scraper.scrape_batch(['p1'])

                    mock_close.assert_called_once()


class TestScrapingPipelineIntegration:
    """Test the complete scraping pipeline with database integration."""

    def test_pcpao_scraper_creates_property_listing(self, mock_chrome_paths):
        """Test that scraped data can be saved to PropertyListing model."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        # Simulate scraped property data
        property_data = {
            'parcel_id': '14-31-15-91961-004-0110',
            'address': '123 MAIN ST',
            'city': 'Clearwater',
            'zip_code': '33755',
            'owner_name': 'Smith John',
            'property_type': 'Single Family Residential',
            'year_built': 1987,
            'building_sqft': 1450,
            'market_value': 245000.0,
            'assessed_value': 220500.0,
            'appraiser_url': 'https://www.pcpao.gov/property-details?test',
        }

        # Create PropertyListing from scraped data
        listing, created = PropertyListing.objects.update_or_create(
            parcel_id=property_data['parcel_id'],
            defaults={
                'address': property_data['address'],
                'city': property_data['city'],
                'zip_code': property_data['zip_code'],
                'owner_name': property_data.get('owner_name'),
                'property_type': property_data.get('property_type', 'Unknown'),
                'year_built': property_data.get('year_built'),
                'building_sqft': property_data.get('building_sqft'),
                'market_value': property_data.get('market_value'),
                'assessed_value': property_data.get('assessed_value'),
                'appraiser_url': property_data.get('appraiser_url'),
            }
        )

        assert created is True
        assert listing.parcel_id == '14-31-15-91961-004-0110'
        assert listing.address == '123 MAIN ST'
        assert listing.city == 'Clearwater'
        assert listing.market_value == Decimal('245000')
        assert listing.year_built == 1987

    def test_tax_collector_updates_existing_listing(self, mock_chrome_paths, sample_property):
        """Test that tax data updates an existing PropertyListing."""
        tax_data = {
            'parcel_id': sample_property.parcel_id,
            'tax_amount': 3500.00,
            'tax_year': 2024,
            'tax_status': 'Paid',
            'delinquent': False,
            'tax_collector_url': 'https://pinellastaxcollector.gov/search?test',
        }

        # Update existing listing with tax data
        sample_property.tax_amount = Decimal(str(tax_data['tax_amount']))
        sample_property.tax_year = tax_data['tax_year']
        sample_property.tax_status = tax_data['tax_status']
        sample_property.delinquent = tax_data['delinquent']
        sample_property.tax_collector_url = tax_data['tax_collector_url']
        sample_property.save()

        # Reload and verify
        updated = PropertyListing.objects.get(parcel_id=sample_property.parcel_id)
        assert updated.tax_amount == Decimal('3500.00')
        assert updated.tax_year == 2024
        assert updated.tax_status == 'Paid'
        assert updated.delinquent is False

    def test_full_pipeline_creates_complete_listing(self, mock_chrome_paths):
        """Test creating a complete listing from both scrapers."""
        # Property data from PCPAO
        pcpao_data = {
            'parcel_id': '14-31-15-91961-004-0999',
            'address': '999 TEST ST',
            'city': 'St Petersburg',
            'zip_code': '33701',
            'owner_name': 'Test Owner',
            'property_type': 'Condo',
            'year_built': 2020,
            'building_sqft': 1200,
            'market_value': 350000.0,
            'assessed_value': 315000.0,
        }

        # Create listing from PCPAO data
        listing = PropertyListing.objects.create(
            parcel_id=pcpao_data['parcel_id'],
            address=pcpao_data['address'],
            city=pcpao_data['city'],
            zip_code=pcpao_data['zip_code'],
            owner_name=pcpao_data['owner_name'],
            property_type=pcpao_data['property_type'],
            year_built=pcpao_data['year_built'],
            building_sqft=pcpao_data['building_sqft'],
            market_value=pcpao_data['market_value'],
            assessed_value=pcpao_data['assessed_value'],
        )

        # Tax data from Tax Collector
        tax_data = {
            'tax_amount': 4200.00,
            'tax_year': 2024,
            'tax_status': 'Paid',
            'delinquent': False,
        }

        # Update with tax data
        listing.tax_amount = Decimal(str(tax_data['tax_amount']))
        listing.tax_year = tax_data['tax_year']
        listing.tax_status = tax_data['tax_status']
        listing.delinquent = tax_data['delinquent']
        listing.save()

        # Verify complete listing
        complete = PropertyListing.objects.get(parcel_id='14-31-15-91961-004-0999')
        assert complete.address == '999 TEST ST'
        assert complete.city == 'St Petersburg'
        assert complete.market_value == Decimal('350000')
        assert complete.tax_amount == Decimal('4200.00')
        assert complete.tax_status == 'Paid'


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling in scrapers."""

    def test_pcpao_handles_malformed_parcel_ids(self, mock_chrome_paths):
        """Test PCPAO scraper ignores malformed parcel IDs."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        html = """
        <html>
        <body>
            <table>
                <tbody>
                    <tr>
                        <td><a href="/property-details?strap=123">invalid-format</a></td>
                    </tr>
                    <tr>
                        <td><a href="/property-details?strap=456">14-31-15-91961-004-0110</a></td>
                    </tr>
                    <tr>
                        <td><a href="/property-details?strap=789">123456</a></td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """

        scraper = PCPAOScraper()
        mock_driver = MagicMock()
        mock_driver.page_source = html
        scraper.driver = mock_driver

        existing_ids = set()
        parcels = scraper._extract_parcels_from_page(existing_ids)

        # Only the valid parcel ID format should be extracted
        assert len(parcels) == 1
        assert parcels[0]['parcel_id'] == '14-31-15-91961-004-0110'

    def test_pcpao_handles_missing_detail_url(self, mock_chrome_paths):
        """Test PCPAO scraper handles missing detail URL gracefully."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        import apps.WebScraper.tasks.pcpao_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver

            # Search page with no property-details links
            mock_driver.page_source = """
            <html><body>
                <p>No results found</p>
            </body></html>
            """
            mock_driver.current_url = 'https://www.pcpao.gov/quick-search'

            scraper = PCPAOScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()

            result = scraper.scrape_property_details('14-31-15-91961-004-0110')

            # Should return dict with just parcel_id
            assert result['parcel_id'] == '14-31-15-91961-004-0110'

    def test_tax_collector_handles_empty_amount(self, mock_chrome_paths):
        """Test Tax Collector handles empty tax amount gracefully."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        import apps.WebScraper.tasks.tax_collector_scraper as scraper_module

        html = """
        <html><body>
            <table>
                <tr><td>Status</td><td>Paid</td></tr>
                <tr><td>Tax Year</td><td>2024</td></tr>
            </table>
        </body></html>
        """

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            mock_driver.page_source = html
            mock_driver.current_url = 'https://pinellastaxcollector.gov/search'

            scraper = TaxCollectorScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()

            result = scraper.scrape_tax_info('14-31-15-91961-004-0110')

            assert result['parcel_id'] == '14-31-15-91961-004-0110'
            assert result['tax_status'] == 'Paid'
            assert 'tax_amount' not in result  # No amount found

    def test_pcpao_handles_timeout_exception(self, mock_chrome_paths):
        """Test PCPAO scraper handles timeout exceptions."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        from selenium.common.exceptions import TimeoutException
        import apps.WebScraper.tasks.pcpao_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver

            scraper = PCPAOScraper()
            scraper.driver = mock_driver
            scraper.wait = MagicMock()
            scraper.wait.until.side_effect = TimeoutException()

            results = scraper.search_properties_with_urls({'city': 'Test'})

            # Should return empty list, not raise
            assert results == []

    def test_tax_collector_handles_non_numeric_amount(self, mock_chrome_paths):
        """Test Tax Collector handles non-numeric tax amount."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        html = """
        <html><body>
            <table>
                <tr><td>Total Tax</td><td>N/A</td></tr>
                <tr><td>Status</td><td>Unknown</td></tr>
            </table>
        </body></html>
        """
        soup = BeautifulSoup(html, 'html.parser')

        value = scraper._get_table_value(soup, 'Total Tax')
        assert value == 'N/A'

        # When parsing, this should not crash
        try:
            amount = float(value.replace('$', '').replace(',', ''))
        except ValueError:
            amount = None

        assert amount is None


class TestParcelIDValidation:
    """Test parcel ID format validation."""

    def test_valid_parcel_id_formats(self, mock_chrome_paths):
        """Test that valid parcel ID formats are accepted."""
        import re

        parcel_pattern = re.compile(r'^\d{2}-\d{2}-\d{2}-\d{5}-\d{3}-\d{4}$')

        valid_ids = [
            '14-31-15-91961-004-0110',
            '15-29-16-12345-000-0010',
            '00-00-00-00000-000-0000',
            '99-99-99-99999-999-9999',
        ]

        for parcel_id in valid_ids:
            assert parcel_pattern.match(parcel_id), f"Should match: {parcel_id}"

    def test_invalid_parcel_id_formats(self, mock_chrome_paths):
        """Test that invalid parcel ID formats are rejected."""
        import re

        parcel_pattern = re.compile(r'^\d{2}-\d{2}-\d{2}-\d{5}-\d{3}-\d{4}$')

        invalid_ids = [
            '14-31-15-9196-004-0110',    # Section too short
            '14-31-15-919610-004-0110',  # Section too long
            '14-31-15-91961-04-0110',    # Subsection too short
            '1-31-15-91961-004-0110',    # Township too short
            'AB-31-15-91961-004-0110',   # Contains letters
            '14311591961-004-0110',      # Missing dashes
            '',                           # Empty string
            '14-31-15-91961-004-011',    # Last section too short
        ]

        for parcel_id in invalid_ids:
            assert not parcel_pattern.match(parcel_id), f"Should not match: {parcel_id}"
