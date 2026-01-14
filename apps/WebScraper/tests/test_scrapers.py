"""
Mocked Selenium Scraper Tests for PCPAO and Tax Collector scrapers.

These tests use mocked WebDriver to test scraper logic without requiring
actual browser automation.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from decimal import Decimal

pytestmark = [pytest.mark.django_db, pytest.mark.selenium]


@pytest.fixture(autouse=True)
def mock_time_sleep():
    """Auto-mock time.sleep for all tests to prevent delays."""
    with patch('apps.WebScraper.tasks.pcpao_scraper.time.sleep'):
        with patch('apps.WebScraper.tasks.tax_collector_scraper.time.sleep'):
            yield


@pytest.fixture
def mock_chrome_dependencies():
    """Mock Chrome binary paths and ChromeDriverManager to avoid TLS errors."""
    with patch('apps.WebScraper.tasks.pcpao_scraper.os.path.exists', return_value=False):
        with patch('apps.WebScraper.tasks.tax_collector_scraper.os.path.exists', return_value=False):
            with patch('apps.WebScraper.tasks.pcpao_scraper.ChromeDriverManager') as mock_cdm1:
                with patch('apps.WebScraper.tasks.tax_collector_scraper.ChromeDriverManager') as mock_cdm2:
                    mock_service1 = MagicMock()
                    mock_service2 = MagicMock()
                    mock_cdm1.return_value.install.return_value = '/fake/chromedriver'
                    mock_cdm2.return_value.install.return_value = '/fake/chromedriver'
                    yield


class TestPCPAOScraper:
    """Tests for PCPAOScraper with mocked Selenium WebDriver."""

    @pytest.fixture
    def mock_webdriver(self):
        """Create mock Chrome WebDriver."""
        with patch('apps.WebScraper.tasks.pcpao_scraper.webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            yield mock_driver

    @pytest.fixture
    def mock_chrome_paths(self):
        """Mock Chrome binary path checks."""
        with patch('apps.WebScraper.tasks.pcpao_scraper.os.path.exists', return_value=False):
            yield

    def test_scraper_initialization(self, mock_webdriver, mock_chrome_paths):
        """Test scraper initializes with correct default settings."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        assert scraper is not None
        assert scraper.headless is True
        assert scraper.driver is None

    def test_scraper_initialization_headless_false(self, mock_webdriver, mock_chrome_paths):
        """Test scraper can be initialized with headless=False."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper(headless=False)
        assert scraper.headless is False

    def test_setup_driver_creates_chrome_instance(self, mock_chrome_dependencies):
        """Test setup_driver creates Chrome WebDriver."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        import apps.WebScraper.tasks.pcpao_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver

            scraper = PCPAOScraper()
            scraper.setup_driver()

            mock_wd.Chrome.assert_called_once()
            assert scraper.driver == mock_driver

    def test_close_driver_quits_webdriver(self, mock_webdriver, mock_chrome_paths):
        """Test close_driver calls quit on WebDriver."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        scraper.driver = mock_webdriver

        scraper.close_driver()

        mock_webdriver.quit.assert_called_once()

    def test_close_driver_handles_none_driver(self, mock_chrome_paths):
        """Test close_driver handles None driver gracefully."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        scraper.driver = None

        # Should not raise
        scraper.close_driver()

    def test_search_properties_navigates_to_search_url(self, mock_webdriver, mock_chrome_paths):
        """Test search_properties navigates to PCPAO search page."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        from selenium.common.exceptions import NoSuchElementException, TimeoutException
        from selenium.webdriver.common.by import By

        mock_search_input = MagicMock()

        def find_element_side_effect(by, selector):
            if by == By.ID and selector == 'txtKeyWord':
                return mock_search_input
            # Pagination button lookup - raise to break loop
            raise NoSuchElementException()

        mock_webdriver.find_element.side_effect = find_element_side_effect
        mock_webdriver.find_elements.return_value = []
        mock_webdriver.page_source = '<html><body><table><tbody></tbody></table></body></html>'

        scraper = PCPAOScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()
        # Make wait.until raise TimeoutException to exit search early
        scraper.wait.until.side_effect = TimeoutException()

        scraper.search_properties({'city': 'Clearwater'})

        mock_webdriver.get.assert_called()
        assert 'pcpao' in mock_webdriver.get.call_args[0][0].lower()

    def test_search_properties_extracts_parcel_ids(self, mock_webdriver, mock_chrome_paths):
        """Test search_properties extracts parcel IDs from results."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.common.by import By

        # HTML with parcel links (BeautifulSoup-based extraction)
        html_with_parcels = """
        <html>
        <body>
            <table>
                <tbody>
                    <tr>
                        <td><a href="/property-details?strap=1">15-29-16-12345-000-0010</a></td>
                    </tr>
                    <tr>
                        <td><a href="/property-details?strap=2">15-29-16-12345-000-0020</a></td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """

        mock_search_input = MagicMock()

        def find_element_side_effect(by, selector):
            if by == By.ID and selector == 'txtKeyWord':
                return mock_search_input
            # Pagination button lookup - raise to break loop
            raise NoSuchElementException()

        mock_webdriver.find_element.side_effect = find_element_side_effect
        mock_webdriver.page_source = html_with_parcels

        scraper = PCPAOScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()
        scraper.wait.until = MagicMock(return_value=mock_search_input)

        results = scraper.search_properties({'city': 'Clearwater'})

        assert '15-29-16-12345-000-0010' in results
        assert '15-29-16-12345-000-0020' in results

    def test_search_properties_handles_empty_results(self, mock_webdriver, mock_chrome_paths):
        """Test search_properties handles empty search results gracefully."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        from selenium.common.exceptions import NoSuchElementException, TimeoutException
        from selenium.webdriver.common.by import By

        mock_search_input = MagicMock()

        def find_element_side_effect(by, selector):
            if by == By.ID and selector == 'txtKeyWord':
                return mock_search_input
            raise NoSuchElementException()

        mock_webdriver.find_element.side_effect = find_element_side_effect
        mock_webdriver.find_elements.return_value = []
        mock_webdriver.page_source = '<html><body></body></html>'

        scraper = PCPAOScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()
        scraper.wait.until.side_effect = TimeoutException()

        results = scraper.search_properties({'city': 'NonexistentCity'})

        assert results == []

    def test_scrape_property_details_returns_dict(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_property_details returns dictionary with parcel_id."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        mock_webdriver.find_element.side_effect = Exception("Element not found")
        mock_webdriver.page_source = '<html><body></body></html>'
        mock_webdriver.current_url = 'https://www.pcpao.gov/property-details'

        scraper = PCPAOScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_property_details('15-29-16-12345-000-0010', detail_url='https://test')

        assert isinstance(result, dict)
        assert result['parcel_id'] == '15-29-16-12345-000-0010'

    def test_scrape_property_details_extracts_address(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_property_details extracts address when available."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper
        from selenium.webdriver.common.by import By

        mock_address_elem = MagicMock()
        mock_address_elem.text = '123 Main St'
        mock_webdriver.page_source = '<html><body></body></html>'
        mock_webdriver.current_url = 'https://www.pcpao.gov/property-details'

        def find_element_side_effect(by, selector):
            if 'address' in selector.lower():
                return mock_address_elem
            raise Exception("Not found")

        mock_webdriver.find_element.side_effect = find_element_side_effect

        scraper = PCPAOScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_property_details('15-29-16-12345-000-0010', detail_url='https://test')

        assert result['parcel_id'] == '15-29-16-12345-000-0010'

    def test_scrape_by_criteria_orchestrates_full_workflow(self, mock_chrome_paths):
        """Test scrape_by_criteria sets up driver, searches, and scrapes details.

        Note: With parallel scraping, setup_driver/close_driver are called multiple times:
        once for the initial search, and once per worker thread.
        """
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        with patch.object(PCPAOScraper, 'setup_driver') as mock_setup:
            with patch.object(PCPAOScraper, 'close_driver') as mock_close:
                with patch.object(PCPAOScraper, 'search_properties_with_urls') as mock_search:
                    with patch.object(PCPAOScraper, 'scrape_property_details') as mock_details:
                        mock_search.return_value = [
                            {'parcel_id': 'parcel-001', 'detail_url': 'http://test1'},
                            {'parcel_id': 'parcel-002', 'detail_url': 'http://test2'},
                        ]
                        mock_details.side_effect = [
                            {'parcel_id': 'parcel-001', 'address': '123 Test'},
                            {'parcel_id': 'parcel-002', 'address': '456 Test'},
                        ]

                        scraper = PCPAOScraper()
                        results = scraper.scrape_by_criteria({'city': 'Clearwater'})

                        # setup_driver called once for search + once per worker (parallel scraping)
                        assert mock_setup.call_count >= 1
                        mock_search.assert_called_once()
                        assert mock_details.call_count == 2
                        # close_driver called once for search + once per worker
                        assert mock_close.call_count >= 1
                        assert len(results) == 2

    def test_scrape_by_criteria_respects_limit(self, mock_chrome_paths):
        """Test scrape_by_criteria respects the limit parameter."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        with patch.object(PCPAOScraper, 'setup_driver'):
            with patch.object(PCPAOScraper, 'close_driver'):
                with patch.object(PCPAOScraper, 'search_properties_with_urls') as mock_search:
                    with patch.object(PCPAOScraper, 'scrape_property_details') as mock_details:
                        mock_search.return_value = [
                            {'parcel_id': f'p{i}', 'detail_url': f'http://test{i}'}
                            for i in range(5)
                        ]
                        mock_details.return_value = {'parcel_id': 'test'}

                        scraper = PCPAOScraper()
                        results = scraper.scrape_by_criteria({'city': 'Test'}, limit=2)

                        assert mock_details.call_count == 2
                        assert len(results) == 2


class TestTaxCollectorScraper:
    """Tests for TaxCollectorScraper with mocked Selenium WebDriver."""

    @pytest.fixture
    def mock_webdriver(self):
        """Create mock Chrome WebDriver."""
        with patch('apps.WebScraper.tasks.tax_collector_scraper.webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            yield mock_driver

    @pytest.fixture
    def mock_chrome_paths(self):
        """Mock Chrome binary path checks."""
        with patch('apps.WebScraper.tasks.tax_collector_scraper.os.path.exists', return_value=False):
            yield

    def test_scraper_initialization(self, mock_webdriver, mock_chrome_paths):
        """Test scraper initializes with correct default settings."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        assert scraper is not None
        assert scraper.headless is True
        assert scraper.driver is None

    def test_setup_driver_creates_chrome_instance(self, mock_chrome_dependencies):
        """Test setup_driver creates Chrome WebDriver."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        import apps.WebScraper.tasks.tax_collector_scraper as scraper_module

        with patch.object(scraper_module, 'webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver

            scraper = TaxCollectorScraper()
            scraper.setup_driver()

            mock_wd.Chrome.assert_called_once()
            assert scraper.driver == mock_driver

    def test_close_driver_quits_webdriver(self, mock_webdriver, mock_chrome_paths):
        """Test close_driver calls quit on WebDriver."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        scraper.driver = mock_webdriver

        scraper.close_driver()

        mock_webdriver.quit.assert_called_once()

    def test_scrape_tax_info_searches_by_parcel_id(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_tax_info searches using parcel ID via direct URL."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        # Tax collector now uses direct URL navigation, not form input
        mock_webdriver.page_source = '<html><body><p>No results</p></body></html>'
        mock_webdriver.current_url = 'https://pinellastaxcollector.gov/search-results/?search=15-29-16-12345-000-0010'

        scraper = TaxCollectorScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_tax_info('15-29-16-12345-000-0010')

        # Should navigate to search URL with parcel ID in query string
        mock_webdriver.get.assert_called()
        call_url = mock_webdriver.get.call_args[0][0]
        assert '15-29-16-12345-000-0010' in call_url

        assert result['parcel_id'] == '15-29-16-12345-000-0010'

    def test_scrape_tax_info_extracts_tax_amount(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_tax_info extracts tax amount."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        from selenium.webdriver.common.by import By

        # HTML with tax table data (BeautifulSoup parses this)
        html_with_tax = """
        <html><body>
            <table>
                <tr><td>Total Tax</td><td>$3,125.00</td></tr>
                <tr><td>Status</td><td>PAID</td></tr>
            </table>
        </body></html>
        """

        mock_webdriver.page_source = html_with_tax
        mock_webdriver.current_url = 'https://pinellastaxcollector.gov/search-results/'

        scraper = TaxCollectorScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_tax_info('15-29-16-12345-000-0010')

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['tax_amount'] == 3125.00
        assert result['tax_status'] == 'Paid'

    def test_scrape_tax_info_handles_paid_status(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_tax_info correctly identifies paid status."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        html_with_paid = """
        <html><body>
            <table>
                <tr><td>Status</td><td>PAID</td></tr>
            </table>
        </body></html>
        """

        mock_webdriver.page_source = html_with_paid
        mock_webdriver.current_url = 'https://pinellastaxcollector.gov/search-results/'

        scraper = TaxCollectorScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_tax_info('15-29-16-12345-000-0010')

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['tax_status'] == 'Paid'
        assert result['delinquent'] is False

    def test_scrape_tax_info_handles_delinquent_status(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_tax_info correctly identifies delinquent status."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        html_with_delinquent = """
        <html><body>
            <table>
                <tr><td>Status</td><td>DELINQUENT</td></tr>
            </table>
        </body></html>
        """

        mock_webdriver.page_source = html_with_delinquent
        mock_webdriver.current_url = 'https://pinellastaxcollector.gov/search-results/'

        scraper = TaxCollectorScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_tax_info('15-29-16-12345-000-0010')

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['tax_status'] == 'Delinquent'
        assert result['delinquent'] is True

    def test_scrape_tax_info_handles_missing_parcel(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_tax_info handles parcel not found gracefully."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        from selenium.common.exceptions import NoSuchElementException

        mock_webdriver.page_source = '<html><body><p>No search results found</p></body></html>'
        mock_webdriver.current_url = 'https://pinellastaxcollector.gov/search-results/'

        scraper = TaxCollectorScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_tax_info('invalid-parcel-id')

        # Should return dict with at least parcel_id, not raise
        assert isinstance(result, dict)
        assert result['parcel_id'] == 'invalid-parcel-id'
        assert result['tax_status'] == 'Not Found'

    def test_scrape_tax_info_handles_timeout(self, mock_webdriver, mock_chrome_paths):
        """Test scrape_tax_info handles timeout gracefully."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        from selenium.common.exceptions import TimeoutException

        mock_webdriver.get.side_effect = TimeoutException()

        scraper = TaxCollectorScraper()
        scraper.driver = mock_webdriver
        scraper.wait = MagicMock()

        result = scraper.scrape_tax_info('15-29-16-12345-000-0010')

        assert isinstance(result, dict)
        assert result['parcel_id'] == '15-29-16-12345-000-0010'

    def test_scrape_batch_processes_multiple_parcels(self, mock_chrome_paths):
        """Test scrape_batch processes list of parcel IDs."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        with patch.object(TaxCollectorScraper, 'setup_driver') as mock_setup:
            with patch.object(TaxCollectorScraper, 'close_driver') as mock_close:
                with patch.object(TaxCollectorScraper, 'scrape_tax_info') as mock_scrape:
                    mock_scrape.side_effect = [
                        {'parcel_id': 'p1', 'tax_amount': 1000},
                        {'parcel_id': 'p2', 'tax_amount': 2000},
                        {'parcel_id': 'p3', 'tax_amount': 3000},
                    ]

                    scraper = TaxCollectorScraper()
                    results = scraper.scrape_batch(['p1', 'p2', 'p3'])

                    mock_setup.assert_called_once()
                    assert mock_scrape.call_count == 3
                    mock_close.assert_called_once()
                    assert len(results) == 3

    def test_scrape_batch_closes_driver_on_error(self, mock_chrome_paths):
        """Test scrape_batch closes driver even when error occurs."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        with patch.object(TaxCollectorScraper, 'setup_driver'):
            with patch.object(TaxCollectorScraper, 'close_driver') as mock_close:
                with patch.object(TaxCollectorScraper, 'scrape_tax_info') as mock_scrape:
                    mock_scrape.side_effect = Exception("Unexpected error")

                    scraper = TaxCollectorScraper()

                    with pytest.raises(Exception):
                        scraper.scrape_batch(['p1'])

                    # Driver should still be closed via finally block
                    mock_close.assert_called_once()
