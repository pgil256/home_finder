"""
Pinellas County Property Appraiser (PCPAO) Selenium Scraper

Uses Selenium for navigation and form interaction, BeautifulSoup for data extraction.
"""

import logging
import re
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
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
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--single-process")
        options.add_argument("--memory-pressure-off")

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

    def _extract_parcels_from_page(self, existing_ids: set) -> List[Dict[str, str]]:
        """Extract parcel info from current page using BeautifulSoup.

        The search results contain both the parcel ID and a strap ID (used in detail URLs).

        Args:
            existing_ids: Set of already-found parcel IDs to avoid duplicates

        Returns:
            List of dicts with parcel_id and detail_url for each new parcel found
        """
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        found = []

        # Parcel ID pattern: 14-31-15-91961-004-0110 (23 chars, 5 dashes)
        parcel_pattern = re.compile(r'^\d{2}-\d{2}-\d{2}-\d{5}-\d{3}-\d{4}$')

        # Find links to property-details pages (they contain strap IDs)
        for link in soup.select('a[href*="property-details"]'):
            text = link.get_text(strip=True)
            href = link.get('href', '')

            if parcel_pattern.match(text) and text not in existing_ids:
                existing_ids.add(text)
                found.append({
                    'parcel_id': text,
                    'detail_url': href if href.startswith('http') else f"{self.BASE_URL}{href.lstrip('/')}"
                })

        return found

    def _extract_parcel_ids_from_page(self, existing_ids: set) -> List[str]:
        """Extract parcel IDs from current page (legacy compatibility).

        Args:
            existing_ids: Set of already-found parcel IDs to avoid duplicates

        Returns:
            List of new parcel IDs found on this page
        """
        parcels = self._extract_parcels_from_page(existing_ids)
        return [p['parcel_id'] for p in parcels]

    def search_properties_with_urls(self, search_criteria: Dict[str, Any]) -> List[Dict[str, str]]:
        """Search for properties using PCPAO Quick Search.

        Returns list of dicts with parcel_id and detail_url for each property.
        """
        parcels = []
        seen_ids = set()

        try:
            logger.info(f"Navigating to {self.SEARCH_URL}")
            self.driver.get(self.SEARCH_URL)

            # Wait for search input to be ready
            search_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "txtKeyWord"))
            )
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

            # Submit search
            search_input.clear()
            search_input.send_keys(search_query)
            search_input.send_keys(Keys.RETURN)
            logger.info("Search submitted, waiting for results...")

            # Wait for results table to load (AJAX content)
            # The page has multiple tables; we need to wait for the DataTable with
            # property-details links to be populated, not just any table row.
            try:
                # First wait for any table structure
                self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
                )

                # Now poll for property-details links (the actual AJAX-loaded data)
                # The DataTable loads asynchronously and may take longer in production
                max_wait_seconds = 15
                poll_interval = 0.5
                waited = 0
                links_found = False

                while waited < max_wait_seconds:
                    try:
                        links = self.driver.find_elements(
                            By.CSS_SELECTOR, "a[href*='property-details']"
                        )
                        if links:
                            links_found = True
                            logger.info(f"Found {len(links)} property-details links after {waited:.1f}s")
                            break
                    except Exception:
                        pass
                    time.sleep(poll_interval)
                    waited += poll_interval

                if not links_found:
                    logger.warning(f"No property-details links found after {max_wait_seconds}s - search may have returned no results")
                    return parcels

                # Brief extra wait for any final rendering (reduced from 1s)
                time.sleep(0.5)

            except TimeoutException:
                logger.warning("No results table found - search may have returned no results")
                return parcels

            # Extract from first page using BeautifulSoup
            first_page_parcels = self._extract_parcels_from_page(seen_ids)
            parcels.extend(first_page_parcels)
            logger.info(f"Page 1: Found {len(first_page_parcels)} parcels")

            # Handle pagination - Selenium for clicking, BeautifulSoup for extraction
            page_num = 1
            MAX_PAGES = 100
            consecutive_empty_pages = 0

            while page_num < MAX_PAGES:
                try:
                    next_button = self.driver.find_element(
                        By.CSS_SELECTOR, "a.paginate_button.next:not(.disabled)"
                    )

                    # Get current links count before clicking
                    current_links = self.driver.find_elements(
                        By.CSS_SELECTOR, "a[href*='property-details']"
                    )
                    current_link_count = len(current_links)

                    next_button.click()
                    page_num += 1

                    # Wait for page transition - poll until links change or timeout
                    max_wait = 10
                    waited = 0
                    while waited < max_wait:
                        time.sleep(0.5)
                        waited += 0.5
                        try:
                            new_links = self.driver.find_elements(
                                By.CSS_SELECTOR, "a[href*='property-details']"
                            )
                            # Page has transitioned when we have links
                            # (they may be same count but different content)
                            if new_links:
                                break
                        except StaleElementReferenceException:
                            # Page is updating, keep waiting
                            continue

                    # Brief wait for rendering stability (reduced from 1s)
                    time.sleep(0.3)

                    # Extract with BeautifulSoup
                    page_parcels = self._extract_parcels_from_page(seen_ids)
                    parcels.extend(page_parcels)
                    logger.info(f"Page {page_num}: Found {len(page_parcels)} new parcels (total: {len(parcels)})")

                    if not page_parcels:
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= 1:
                            logger.info("Empty page reached, stopping pagination")
                            break
                    else:
                        consecutive_empty_pages = 0

                except NoSuchElementException:
                    logger.info("No more pages (next button disabled or not found)")
                    break
                except StaleElementReferenceException:
                    logger.warning(f"Stale element on page {page_num}, retrying...")
                    time.sleep(1)
                    continue

            if page_num >= MAX_PAGES:
                logger.warning(f"Hit max page limit ({MAX_PAGES}), stopping pagination")

        except Exception as e:
            logger.error(f"Error searching properties: {e}", exc_info=True)
            try:
                logger.error(f"Current URL: {self.driver.current_url}")
                logger.error(f"Page title: {self.driver.title}")
            except:
                pass

        logger.info(f"Found {len(parcels)} parcels")
        return parcels

    def search_properties(self, search_criteria: Dict[str, Any]) -> List[str]:
        """Search for properties using PCPAO Quick Search (legacy compatibility).

        Returns list of parcel IDs only. Use search_properties_with_urls for
        better performance when scraping property details.
        """
        parcels = self.search_properties_with_urls(search_criteria)
        return [p['parcel_id'] for p in parcels]

    def _get_h2_value(self, soup: BeautifulSoup, label: str) -> Optional[str]:
        """Extract value from h2 element where label is in the parent.

        PCPAO uses a pattern where the label text and h2 value are both in a parent div.

        Args:
            soup: BeautifulSoup object of the page
            label: Text to search for (case-insensitive)

        Returns:
            Text content of the h2 element, or None if not found
        """
        for h2 in soup.find_all('h2'):
            parent = h2.parent
            if parent:
                parent_text = parent.get_text(strip=True)
                if label.lower() in parent_text.lower():
                    return h2.get_text(strip=True)
        return None

    def _get_sibling_value(self, soup: BeautifulSoup, label: str) -> Optional[str]:
        """Extract value from sibling element after a label.

        PCPAO uses a pattern where label text is followed by value in next sibling.

        Args:
            soup: BeautifulSoup object of the page
            label: Text to search for (case-insensitive)

        Returns:
            Text content of the sibling element, or None if not found
        """
        elem = soup.find(string=re.compile(re.escape(label), re.I))
        if elem:
            parent = elem.find_parent()
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    return sibling.get_text(strip=True)
        return None

    def _get_address_parts(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract address, city, and zip from Site Address section.

        The Site Address label is followed by a sibling element containing
        street address and city/state/zip separated by <br> tags.

        Args:
            soup: BeautifulSoup object of the page

        Returns:
            Dict with address, city, and zip_code keys
        """
        result = {}
        elem = soup.find(string=re.compile('Site Address', re.I))
        if elem:
            parent = elem.find_parent()
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    # Get text parts split by <br> tags
                    parts = []
                    for child in sibling.children:
                        if hasattr(child, 'name') and child.name == 'br':
                            continue
                        text = str(child).strip() if not hasattr(child, 'get_text') else child.get_text(strip=True)
                        if text:
                            parts.append(text)

                    if len(parts) >= 1:
                        result['address'] = parts[0]
                    if len(parts) >= 2:
                        # Parse "CLEARWATER, FL 33759"
                        city_state_zip = parts[1]
                        city_match = re.match(r'([A-Z\s]+),?\s*FL\s*(\d{5})', city_state_zip)
                        if city_match:
                            result['city'] = city_match.group(1).strip().title()
                            result['zip_code'] = city_match.group(2)
        return result

    def _get_parcel_from_page(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract parcel ID from the detail page.

        Args:
            soup: BeautifulSoup object of the page

        Returns:
            Parcel ID string or None if not found
        """
        parcel_pattern = re.compile(r'^\d{2}-\d{2}-\d{2}-\d{5}-\d{3}-\d{4}$')
        for h2 in soup.find_all('h2'):
            text = h2.get_text(strip=True)
            if parcel_pattern.match(text):
                return text
        return None

    def _get_valuation_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract valuation data from the current year's valuation table.

        Args:
            soup: BeautifulSoup object of the page

        Returns:
            Dict with market_value and assessed_value if found
        """
        data = {}
        for table in soup.find_all('table'):
            text = table.get_text()
            if 'Just/Market Value' in text and 'Assessed' in text:
                rows = table.select('tbody tr')
                if rows:
                    cells = [td.get_text(strip=True) for td in rows[0].find_all('td')]
                    # Typical structure: Year, Just/Market Value, Assessed Value, ...
                    if len(cells) >= 3:
                        try:
                            market_val = cells[1].replace('$', '').replace(',', '')
                            data['market_value'] = float(market_val)
                        except (ValueError, IndexError):
                            pass
                        try:
                            assessed_val = cells[2].replace('$', '').replace(',', '')
                            data['assessed_value'] = float(assessed_val)
                        except (ValueError, IndexError):
                            pass
                break
        return data

    def _extract_property_image(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property image URL from detail page.

        PCPAO may have property photos in various locations. This method
        attempts multiple selectors to find the primary property image.

        Args:
            soup: BeautifulSoup object of the property detail page

        Returns:
            Full URL to property image, or None if not found
        """
        # Common selectors for property photos on county appraiser sites
        selectors = [
            'img.property-photo',
            'img.property-image',
            'img[alt*="property"]',
            'img[alt*="Property"]',
            '.property-photo img',
            '.property-image img',
            '#property-photo img',
            '.photo-gallery img',
            '.main-photo img',
            'img[src*="property"]',
            'img[src*="parcel"]',
        ]

        for selector in selectors:
            img = soup.select_one(selector)
            if img and img.get('src'):
                src = img['src']
                # Handle relative URLs
                if src.startswith('//'):
                    return f"https:{src}"
                elif src.startswith('/'):
                    return f"{self.BASE_URL.rstrip('/')}{src}"
                elif src.startswith('http'):
                    return src

        # Fallback: look for any large image that might be a property photo
        for img in soup.find_all('img'):
            src = img.get('src', '')
            # Skip small icons, logos, and UI elements
            if any(skip in src.lower() for skip in ['logo', 'icon', 'button', 'arrow', 'nav']):
                continue
            # Check for reasonable image dimensions if available
            width = img.get('width', '')
            height = img.get('height', '')
            if width and height:
                try:
                    if int(width) >= 200 and int(height) >= 150:
                        if src.startswith('/'):
                            return f"{self.BASE_URL.rstrip('/')}{src}"
                        elif src.startswith('http'):
                            return src
                except ValueError:
                    pass

        return None

    def scrape_property_details(self, parcel_id: str, detail_url: Optional[str] = None) -> Dict[str, Any]:
        """Scrape property details using BeautifulSoup for extraction.

        Args:
            parcel_id: The parcel ID
            detail_url: Optional direct URL to property details page

        Returns:
            Dict containing property data
        """
        property_data = {'parcel_id': parcel_id}

        try:
            # Use provided detail_url or search for the property
            if detail_url:
                self.driver.get(detail_url)
            else:
                # Search for the parcel to get the detail URL
                self.driver.get(self.SEARCH_URL)
                # Wait for search input instead of fixed sleep
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "txtKeyWord"))
                )
                search_input = self.driver.find_element(By.ID, "txtKeyWord")
                search_input.clear()
                search_input.send_keys(parcel_id)
                search_input.send_keys(Keys.RETURN)
                # Wait for results instead of fixed 4s sleep
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='property-details']"))
                    )
                except TimeoutException:
                    time.sleep(1)  # Fallback short wait

                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                link = soup.select_one(f'a[href*="property-details"]')
                if link:
                    detail_url = link.get('href')
                    if not detail_url.startswith('http'):
                        detail_url = f"{self.BASE_URL}{detail_url.lstrip('/')}"
                    self.driver.get(detail_url)
                else:
                    logger.warning(f"No detail link found for parcel {parcel_id}")
                    return property_data

            # Wait for page to load (reduced from 3s fixed sleep)
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h2"))
                )
            except TimeoutException:
                time.sleep(1)  # Fallback short wait
            property_data['appraiser_url'] = self.driver.current_url

            # Parse page with BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Extract H2 label-value pairs (PCPAO pattern)
            h2_fields = {
                'building_sqft': ['Living SF', 'Heated SF'],
                'gross_sqft': ['Gross SF'],
                'living_units': ['Living Units'],
                'buildings': ['Buildings'],
            }

            for field, labels in h2_fields.items():
                for label in labels:
                    value = self._get_h2_value(soup, label)
                    if value and value not in ['n/a', 'N/A', '']:
                        try:
                            property_data[field] = int(re.sub(r'[^\d]', '', value))
                            break
                        except (ValueError, TypeError):
                            pass

            # Get parcel ID from the page (in case it wasn't provided correctly)
            page_parcel = self._get_parcel_from_page(soup)
            if page_parcel:
                property_data['parcel_id'] = page_parcel

            # Extract sibling-pattern fields (label followed by value in sibling)
            sibling_fields = {
                'owner_name': 'Owner Name',
                'year_built': 'Year Built',
                'property_type': 'Property Use',
            }

            for field, label in sibling_fields.items():
                value = self._get_sibling_value(soup, label)
                if value and value not in ['n/a', 'N/A', '']:
                    if field == 'year_built':
                        try:
                            property_data[field] = int(re.sub(r'[^\d]', '', value))
                        except (ValueError, TypeError):
                            pass
                    elif field == 'owner_name':
                        # Clean up owner name (remove "More" suffix and add space between names)
                        value = re.sub(r'More$', '', value).strip()
                        # Add space before uppercase letters that follow lowercase (name boundaries)
                        value = re.sub(r'([a-z])([A-Z])', r'\1 \2', value)
                        property_data[field] = value
                    else:
                        property_data[field] = value

            # Extract site address with proper parsing (handles <br> tags)
            address_parts = self._get_address_parts(soup)
            property_data.update(address_parts)

            # Extract valuation data from table
            valuation = self._get_valuation_data(soup)
            property_data.update(valuation)

            # Extract property image URL
            image_url = self._extract_property_image(soup)
            if image_url:
                property_data['image_url'] = image_url

        except Exception as e:
            logger.error(f"Error scraping property {parcel_id}: {e}")

        # Log extracted data for debugging
        logger.info(f"Scraped property {parcel_id}: address={property_data.get('address')}, "
                    f"city={property_data.get('city')}, market_value={property_data.get('market_value')}, "
                    f"owner={property_data.get('owner_name')}, sqft={property_data.get('building_sqft')}, "
                    f"image={'found' if property_data.get('image_url') else 'not found'}")

        return property_data

    def _scrape_worker(self, parcels_chunk: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Worker function for parallel scraping. Each worker gets its own browser instance.

        Args:
            parcels_chunk: List of parcel dicts with parcel_id and detail_url

        Returns:
            List of property data dicts
        """
        worker_scraper = PCPAOScraper(headless=self.headless)
        results = []
        try:
            worker_scraper.setup_driver()
            for parcel_info in parcels_chunk:
                parcel_id = parcel_info['parcel_id']
                detail_url = parcel_info.get('detail_url')
                try:
                    property_data = worker_scraper.scrape_property_details(parcel_id, detail_url=detail_url)
                    results.append((parcel_info['_index'], property_data))
                    time.sleep(0.3)  # Brief delay between requests
                except Exception as e:
                    logger.error(f"Worker error scraping {parcel_id}: {e}")
                    results.append((parcel_info['_index'], {'parcel_id': parcel_id}))
        finally:
            worker_scraper.close_driver()
        return results

    def scrape_properties_parallel(
        self,
        parcels: List[Dict[str, str]],
        max_workers: int = 3,
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """Scrape property details using multiple browser instances in parallel.

        Args:
            parcels: List of parcel dicts with parcel_id and detail_url
            max_workers: Number of concurrent browser instances (default 3)
            progress_callback: Optional callback(completed, total) for progress updates

        Returns:
            List of property data dicts in original order
        """
        if not parcels:
            return []

        # Add index to each parcel for maintaining order
        indexed_parcels = [
            {**p, '_index': i} for i, p in enumerate(parcels)
        ]

        # Distribute parcels across workers (round-robin)
        chunks = [[] for _ in range(max_workers)]
        for i, parcel in enumerate(indexed_parcels):
            chunks[i % max_workers].append(parcel)

        # Remove empty chunks
        chunks = [c for c in chunks if c]
        actual_workers = len(chunks)

        logger.info(f"Parallel scraping {len(parcels)} properties with {actual_workers} workers")

        # Results array to maintain order
        results = [None] * len(parcels)
        completed = 0

        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            futures = {
                executor.submit(self._scrape_worker, chunk): chunk
                for chunk in chunks
            }

            for future in as_completed(futures):
                try:
                    worker_results = future.result()
                    for idx, property_data in worker_results:
                        results[idx] = property_data
                        completed += 1
                        if progress_callback:
                            progress_callback(completed, len(parcels))
                except Exception as e:
                    logger.error(f"Worker failed: {e}")

        # Filter out any None results (shouldn't happen but defensive)
        return [r for r in results if r is not None]

    def scrape_by_criteria(self, search_criteria: Dict[str, Any], limit: Optional[int] = None, max_workers: int = 3) -> List[Dict[str, Any]]:
        """Search for properties and scrape their details using parallel browser instances.

        Args:
            search_criteria: Dict with search parameters (city, zip_code, address, owner_name)
            limit: Optional max number of properties to scrape
            max_workers: Number of concurrent browser instances (default 3)

        Returns:
            List of property data dicts
        """
        try:
            self.setup_driver()
            parcels = self.search_properties_with_urls(search_criteria)

            if limit:
                parcels = parcels[:limit]

            logger.info(f"Scraping details for {len(parcels)} properties")

        finally:
            self.close_driver()

        # Use parallel scraping for property details (each worker creates its own browser)
        if not parcels:
            return []

        if len(parcels) == 1:
            # Single property - no need for parallel overhead
            single_scraper = PCPAOScraper(headless=self.headless)
            try:
                single_scraper.setup_driver()
                return [single_scraper.scrape_property_details(
                    parcels[0]['parcel_id'],
                    detail_url=parcels[0].get('detail_url')
                )]
            finally:
                single_scraper.close_driver()

        return self.scrape_properties_parallel(parcels, max_workers=max_workers)