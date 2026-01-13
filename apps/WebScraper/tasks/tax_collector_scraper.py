"""
Pinellas County Tax Collector Selenium Scraper

Uses Selenium for navigation and form interaction, BeautifulSoup for data extraction.

NOTE: The primary tax payment site (pinellas.county-taxes.com) has Cloudflare protection
which prevents automated access. This scraper attempts to use the pinellastaxcollector.gov
search but may return limited data. Consider using the PCPAO bulk data import for tax
information when available.
"""

import logging
import re
import time
from typing import Dict, Any, Optional
from datetime import datetime

import os
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException
from webdriver_manager.chrome import ChromeDriverManager

# Chrome for Testing paths
# Priority: 1. Environment variables (production), 2. Local dev paths, 3. webdriver-manager fallback
CHROME_BINARY = os.environ.get('CHROME_BIN') or os.path.expanduser("~/.chrome-for-testing/chrome-linux64/chrome")
CHROMEDRIVER_BINARY = os.environ.get('CHROMEDRIVER_PATH') or os.path.expanduser("~/.chrome-for-testing/chromedriver-linux64/chromedriver")

logger = logging.getLogger(__name__)


class TaxCollectorScraper:
    """Scraper for Pinellas County Tax Collector information.

    Note: Direct tax bill scraping is limited due to Cloudflare protection on the
    primary tax payment site. This scraper returns basic information when available.
    """

    BASE_URL = "https://pinellastaxcollector.gov/"
    SEARCH_URL = "https://pinellastaxcollector.gov/search-results/"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.wait = None

    def setup_driver(self):
        options = Options()
        if os.path.exists(CHROME_BINARY):
            options.binary_location = CHROME_BINARY
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        if os.path.exists(CHROMEDRIVER_BINARY):
            service = Service(CHROMEDRIVER_BINARY)
        else:
            service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)
        logger.info("Chrome driver initialized for Tax Collector scraper")

    def close_driver(self):
        if self.driver:
            self.driver.quit()

    def _get_table_value(self, soup: BeautifulSoup, label: str) -> Optional[str]:
        """Find a table cell value by its label text.

        Args:
            soup: BeautifulSoup object of the page
            label: Text to search for in table cells

        Returns:
            Text content of the sibling cell, or None if not found
        """
        td = soup.find('td', string=re.compile(re.escape(label), re.I))
        if td:
            sibling = td.find_next_sibling('td')
            if sibling:
                return sibling.get_text(strip=True)
        return None

    def scrape_tax_info(self, parcel_id: str) -> Dict[str, Any]:
        """Scrape tax information using BeautifulSoup for extraction.

        Note: Due to Cloudflare protection on the primary tax site, this method
        may only return basic information. For complete tax data, consider using
        the PCPAO bulk data import which includes tax information.

        Args:
            parcel_id: The parcel ID to search for

        Returns:
            Dict with tax information (may be limited)
        """
        tax_data = {
            'parcel_id': parcel_id,
            'tax_year': datetime.now().year,
            'tax_status': 'Unknown',
            'delinquent': False,
        }

        try:
            # Use direct URL with parcel ID search parameter
            search_url = f"{self.SEARCH_URL}?search={parcel_id}"
            self.driver.get(search_url)
            # Wait for page load (reduced from 4s fixed sleep)
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(0.5)  # Brief stabilization wait
            except TimeoutException:
                pass

            tax_data['tax_collector_url'] = self.driver.current_url

            # Parse page with BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Check if we got a "no results" message
            page_text = soup.get_text().lower()
            if 'no search results' in page_text or 'no results' in page_text:
                logger.warning(f"No tax results found for parcel {parcel_id}")
                tax_data['tax_status'] = 'Not Found'
                return tax_data

            # Try to extract any available tax information
            # Look for tables with tax data
            for table in soup.find_all('table'):
                # Extract tax amount
                tax_amount = self._get_table_value(soup, 'Total Tax')
                if not tax_amount:
                    tax_amount = self._get_table_value(soup, 'Amount Due')
                if not tax_amount:
                    tax_amount = self._get_table_value(soup, 'Tax Amount')

                if tax_amount:
                    try:
                        tax_data['tax_amount'] = float(re.sub(r'[^\d.]', '', tax_amount))
                    except (ValueError, TypeError):
                        pass

                # Extract tax year
                tax_year = self._get_table_value(soup, 'Tax Year')
                if not tax_year:
                    tax_year = self._get_table_value(soup, 'Year')
                if tax_year:
                    try:
                        tax_data['tax_year'] = int(re.sub(r'[^\d]', '', tax_year))
                    except (ValueError, TypeError):
                        pass

                # Extract payment status
                status_text = self._get_table_value(soup, 'Status')
                if not status_text:
                    status_text = self._get_table_value(soup, 'Payment Status')
                if status_text:
                    status_upper = status_text.upper()
                    if 'PAID' in status_upper:
                        tax_data['tax_status'] = 'Paid'
                        tax_data['delinquent'] = False
                    elif 'UNPAID' in status_upper:
                        tax_data['tax_status'] = 'Unpaid'
                        tax_data['delinquent'] = False
                    elif 'DELINQUENT' in status_upper:
                        tax_data['tax_status'] = 'Delinquent'
                        tax_data['delinquent'] = True
                    else:
                        tax_data['tax_status'] = status_text
                        tax_data['delinquent'] = False

                # If we found any data, break
                if 'tax_amount' in tax_data:
                    break

            # If no data found, note the limitation
            if 'tax_amount' not in tax_data:
                logger.info(f"Limited tax data available for parcel {parcel_id} - site may be protected")

        except TimeoutException:
            logger.error(f"Timeout while searching for parcel {parcel_id}")
        except Exception as e:
            logger.error(f"Error scraping tax info for parcel {parcel_id}: {e}")

        return tax_data

    def scrape_batch(self, parcel_ids: list) -> list:
        tax_data_list = []
        try:
            self.setup_driver()

            for i, parcel_id in enumerate(parcel_ids, 1):
                logger.info(f"Scraping tax info {i}/{len(parcel_ids)}: {parcel_id}")
                tax_data = self.scrape_tax_info(parcel_id)
                tax_data_list.append(tax_data)
                time.sleep(0.3)  # Reduced from 1s

        finally:
            self.close_driver()

        return tax_data_list