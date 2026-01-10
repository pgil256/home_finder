"""
Pinellas County Property Appraiser (PCPAO) Selenium Scraper
"""

import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime

import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Chrome for Testing paths
# Priority: 1. Environment variables (production), 2. Local dev paths, 3. webdriver-manager fallback
CHROME_BINARY = os.environ.get('CHROME_BIN') or os.path.expanduser("~/.chrome-for-testing/chrome-linux64/chrome")
CHROMEDRIVER_BINARY = os.environ.get('CHROMEDRIVER_PATH') or os.path.expanduser("~/.chrome-for-testing/chromedriver-linux64/chromedriver")

logger = logging.getLogger(__name__)


class PCPAOScraper:
    BASE_URL = "https://www.pcpao.gov/"
    SEARCH_URL = "https://www.pcpao.gov/quick-search"
    DETAIL_URL = "https://www.pcpao.gov/property-details"

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
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")

        if os.path.exists(CHROMEDRIVER_BINARY):
            service = Service(CHROMEDRIVER_BINARY)
        else:
            service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)
        logger.info("Chrome driver initialized for PCPAO scraper")

    def close_driver(self):
        if self.driver:
            self.driver.quit()
            logger.info("Driver closed")

    def search_properties(self, search_criteria: Dict[str, Any]) -> List[str]:
        """Search for properties using PCPAO Quick Search."""
        parcel_ids = []
        try:
            logger.info(f"Navigating to {self.SEARCH_URL}")
            self.driver.get(self.SEARCH_URL)
            time.sleep(3)
            logger.info(f"Page loaded, title: {self.driver.title}")

            # Build search query from criteria
            search_terms = []
            if search_criteria.get('address'):
                search_terms.append(search_criteria['address'])
            if search_criteria.get('city'):
                search_terms.append(search_criteria['city'])
            if search_criteria.get('zip_code'):
                search_terms.append(search_criteria['zip_code'])
            if search_criteria.get('owner_name'):
                search_terms.append(search_criteria['owner_name'])

            search_query = ' '.join(search_terms) if search_terms else 'Clearwater'
            logger.info(f"Searching for: {search_query}")

            # Use the quick search input
            search_input = self.driver.find_element(By.ID, "txtKeyWord")
            search_input.clear()
            search_input.send_keys(search_query)
            search_input.send_keys(Keys.RETURN)
            logger.info("Search submitted, waiting for results...")
            time.sleep(5)

            # Extract parcel IDs from results - they appear as links with format XX-XX-XX-XXXXX-XXX-XXXX
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                text = link.text.strip()
                href = link.get_attribute('href') or ''
                # Parcel IDs match pattern like 14-31-15-91961-004-0110
                if text and len(text) == 23 and text.count('-') == 5:
                    if text not in parcel_ids:
                        parcel_ids.append(text)
                        logger.debug(f"Found parcel: {text}")

            # Handle pagination if present
            page_num = 1
            while True:
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, "a.paginate_button.next:not(.disabled)")
                    next_button.click()
                    time.sleep(2)
                    page_num += 1
                    logger.info(f"Processing page {page_num}")

                    # Re-extract parcel IDs from new page
                    links = self.driver.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        text = link.text.strip()
                        if text and len(text) == 23 and text.count('-') == 5:
                            if text not in parcel_ids:
                                parcel_ids.append(text)
                except NoSuchElementException:
                    break

        except Exception as e:
            logger.error(f"Error searching properties: {e}", exc_info=True)
            # Log page source for debugging
            try:
                logger.error(f"Current URL: {self.driver.current_url}")
                logger.error(f"Page title: {self.driver.title}")
            except:
                pass

        logger.info(f"Found {len(parcel_ids)} parcels")
        return parcel_ids

    def scrape_property_details(self, parcel_id: str) -> Dict[str, Any]:
        property_data = {'parcel_id': parcel_id}

        try:
            parcel_url = f"{self.BASE_URL}parcel/{parcel_id}"
            self.driver.get(parcel_url)
            time.sleep(2)
            property_data['appraiser_url'] = parcel_url

            # Extract data using various selectors
            extractors = [
                ('address', "h1.property-address", "//span[contains(@class, 'address')]"),
                ('owner_name', None, "//td[text()='Owner Name']/following-sibling::td"),
                ('market_value', None, "//td[contains(text(), 'Market Value')]/following-sibling::td"),
                ('assessed_value', None, "//td[contains(text(), 'Assessed Value')]/following-sibling::td"),
                ('year_built', None, "//td[text()='Year Built']/following-sibling::td"),
                ('building_sqft', None, "//td[contains(text(), 'Living Area')]/following-sibling::td"),
                ('bedrooms', None, "//td[text()='Bedrooms']/following-sibling::td"),
                ('bathrooms', None, "//td[text()='Bathrooms']/following-sibling::td"),
                ('property_type', None, "//td[contains(text(), 'Property Use')]/following-sibling::td"),
            ]

            for field, css_selector, xpath_selector in extractors:
                try:
                    if css_selector:
                        elem = self.driver.find_element(By.CSS_SELECTOR, css_selector)
                    else:
                        elem = self.driver.find_element(By.XPATH, xpath_selector)

                    value = elem.text.strip()

                    if field in ['market_value', 'assessed_value']:
                        value = float(value.replace('$', '').replace(',', ''))
                    elif field in ['year_built', 'bedrooms']:
                        value = int(value)
                    elif field == 'bathrooms':
                        value = float(value)
                    elif field == 'building_sqft':
                        value = int(value.replace(',', '').replace('sqft', '').strip())

                    property_data[field] = value
                except:
                    pass

            # Extract city and ZIP
            try:
                city_zip_elem = self.driver.find_element(By.CSS_SELECTOR, "span.city-state-zip")
                city_zip_text = city_zip_elem.text.strip()
                parts = city_zip_text.split(',')
                if len(parts) >= 2:
                    property_data['city'] = parts[0].strip()
                    zip_parts = parts[-1].strip().split()
                    if zip_parts:
                        property_data['zip_code'] = zip_parts[-1]
            except:
                pass

            # Extract land size
            try:
                land_elem = self.driver.find_element(By.XPATH, "//td[contains(text(), 'Land Area')]/following-sibling::td")
                land_text = land_elem.text.strip()
                if 'acres' in land_text.lower():
                    land_size = float(land_text.replace('acres', '').replace(',', '').strip())
                    property_data['land_size'] = land_size
                    property_data['lot_sqft'] = int(land_size * 43560)
                elif 'sqft' in land_text.lower():
                    lot_sqft = int(land_text.replace('sqft', '').replace(',', '').strip())
                    property_data['lot_sqft'] = lot_sqft
                    property_data['land_size'] = lot_sqft / 43560
            except:
                pass

        except Exception as e:
            logger.error(f"Error scraping property {parcel_id}: {e}")

        return property_data

    def scrape_by_criteria(self, search_criteria: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        properties = []
        try:
            self.setup_driver()
            parcel_ids = self.search_properties(search_criteria)

            if limit:
                parcel_ids = parcel_ids[:limit]

            logger.info(f"Scraping details for {len(parcel_ids)} properties")

            for i, parcel_id in enumerate(parcel_ids, 1):
                logger.info(f"Scraping property {i}/{len(parcel_ids)}: {parcel_id}")
                property_data = self.scrape_property_details(parcel_id)
                properties.append(property_data)
                time.sleep(1)

        finally:
            self.close_driver()

        return properties