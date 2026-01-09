"""
Pinellas County Tax Collector Selenium Scraper
"""

import logging
import time
from typing import Dict, Any
from datetime import datetime

import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
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


class TaxCollectorScraper:
    BASE_URL = "https://taxcollect.com/"
    SEARCH_URL = "https://taxcollect.com/search"

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

    def scrape_tax_info(self, parcel_id: str) -> Dict[str, Any]:
        tax_data = {'parcel_id': parcel_id}

        try:
            self.driver.get(self.SEARCH_URL)
            time.sleep(2)

            # Find and fill search field
            search_selectors = [
                "input[name='parcel']",
                "input[name='parcel_id']",
                "input[placeholder*='Parcel']",
                "input[type='search']"
            ]

            search_input = None
            for selector in search_selectors:
                try:
                    search_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue

            if not search_input:
                try:
                    search_input = self.driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Enter parcel')]")
                except:
                    logger.error(f"Could not find search input for parcel {parcel_id}")
                    return tax_data

            search_input.clear()
            search_input.send_keys(parcel_id)
            search_input.send_keys(Keys.RETURN)
            time.sleep(3)

            tax_data['tax_collector_url'] = self.driver.current_url

            # Extract tax amount
            try:
                tax_amount_elem = self.driver.find_element(By.XPATH, "//td[contains(text(), 'Total Tax')]/following-sibling::td")
                tax_amount_text = tax_amount_elem.text.replace('$', '').replace(',', '').strip()
                tax_data['tax_amount'] = float(tax_amount_text)
            except:
                try:
                    tax_amount_elem = self.driver.find_element(By.CSS_SELECTOR, ".tax-amount")
                    tax_amount_text = tax_amount_elem.text.replace('$', '').replace(',', '').strip()
                    tax_data['tax_amount'] = float(tax_amount_text)
                except:
                    pass

            # Extract tax year
            try:
                year_elem = self.driver.find_element(By.XPATH, "//td[contains(text(), 'Tax Year')]/following-sibling::td")
                tax_data['tax_year'] = int(year_elem.text.strip())
            except:
                tax_data['tax_year'] = datetime.now().year

            # Extract payment status
            try:
                status_elem = self.driver.find_element(By.XPATH, "//td[contains(text(), 'Status')]/following-sibling::td")
                status_text = status_elem.text.strip().upper()

                if 'PAID' in status_text:
                    tax_data['tax_status'] = 'Paid'
                    tax_data['delinquent'] = False
                elif 'UNPAID' in status_text:
                    tax_data['tax_status'] = 'Unpaid'
                    tax_data['delinquent'] = False
                elif 'DELINQUENT' in status_text:
                    tax_data['tax_status'] = 'Delinquent'
                    tax_data['delinquent'] = True
                else:
                    tax_data['tax_status'] = status_text
                    tax_data['delinquent'] = False
            except:
                tax_data['tax_status'] = 'Unknown'
                tax_data['delinquent'] = False

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
                time.sleep(1)

        finally:
            self.close_driver()

        return tax_data_list