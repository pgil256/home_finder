"""
Pinellas County Property Appraiser (PCPAO) Selenium Scraper
"""

import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


class PCPAOScraper:
    BASE_URL = "https://www.pcpao.org/"
    SEARCH_URL = "https://www.pcpao.org/search"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.wait = None

    def setup_driver(self):
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)
        logger.info("Chrome driver initialized for PCPAO scraper")

    def close_driver(self):
        if self.driver:
            self.driver.quit()
            logger.info("Driver closed")

    def search_properties(self, search_criteria: Dict[str, Any]) -> List[str]:
        parcel_ids = []
        try:
            self.driver.get(self.SEARCH_URL)
            time.sleep(2)

            # Try to access advanced search
            try:
                advanced_search = self.wait.until(
                    EC.element_to_be_clickable((By.LINK_TEXT, "Advanced Search"))
                )
                advanced_search.click()
                time.sleep(2)
            except:
                pass

            # Fill search criteria
            if search_criteria.get('city'):
                try:
                    city_field = self.driver.find_element(By.NAME, "city")
                    city_field.clear()
                    city_field.send_keys(search_criteria['city'])
                except:
                    city_select = Select(self.driver.find_element(By.NAME, "city"))
                    city_select.select_by_visible_text(search_criteria['city'])

            if search_criteria.get('zip_code'):
                zip_field = self.driver.find_element(By.NAME, "zip")
                zip_field.clear()
                zip_field.send_keys(search_criteria['zip_code'])

            if search_criteria.get('property_type'):
                try:
                    prop_type_select = Select(self.driver.find_element(By.NAME, "property_use"))
                    prop_type_select.select_by_visible_text(search_criteria['property_type'])
                except:
                    pass

            if search_criteria.get('min_value'):
                min_val = self.driver.find_element(By.NAME, "min_market_value")
                min_val.clear()
                min_val.send_keys(str(search_criteria['min_value']))

            if search_criteria.get('max_value'):
                max_val = self.driver.find_element(By.NAME, "max_market_value")
                max_val.clear()
                max_val.send_keys(str(search_criteria['max_value']))

            # Submit search
            search_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            search_button.click()
            time.sleep(3)

            # Process results
            page_num = 1
            while True:
                logger.info(f"Processing page {page_num}")
                parcel_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='parcel']")

                for link in parcel_links:
                    href = link.get_attribute('href')
                    if 'parcel/' in href:
                        parcel_id = href.split('parcel/')[-1].split('/')[0]
                        if parcel_id and parcel_id not in parcel_ids:
                            parcel_ids.append(parcel_id)

                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next page']")
                    if 'disabled' in next_button.get_attribute('class'):
                        break
                    next_button.click()
                    time.sleep(2)
                    page_num += 1
                except NoSuchElementException:
                    break

        except Exception as e:
            logger.error(f"Error searching properties: {e}")

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