import random
import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from django.conf import settings
import json
from scrapingant_client import (
    ScrapingAntClient,
    ScrapingantClientException,
    ScrapingantInvalidInputException,
)
from lxml import html
from requests_html import HTMLSession
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry  # Corrected import

from .user_agents import get_user_agent

# Proxy address from Django settings
proxy_address = settings.PROXY_ADDRESS
scraping_api_key = settings.SCRAPING_API_KEY

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("urllib3").setLevel(logging.WARNING)




# Function to retrieve random user-agent headers
def get_random_headers():
    return {
        "user-agent": get_user_agent(),
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.5",
        "accept-encoding": "gzip, deflate, br",
        "referer": "https://www.google.com/",
    }


# Consolidated session creation function
def create_session_with_retry(
    session_type="requests",
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
):
    if session_type == "html":
        session = HTMLSession()
    else:
        session = requests.Session()
    logger.info(f"Session type: {session_type}")

    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


# Function to scrape individual listings
def make_listing_request(url):
    retries = 0
    max_retries = 3
    request_delay = random.uniform(1, 3)  # Random delay between requests
    rate_limit = 5  # Maximum requests per minute
    request_count = 0
    start_time = time.time()

    while retries < max_retries:
        if request_count >= rate_limit:
            elapsed_time = time.time() - start_time
            if elapsed_time < 60:
                time.sleep(60 - elapsed_time)
            request_count = 0
            start_time = time.time()

        session = requests.Session()
        headers = get_random_headers()
        proxies = {"http": proxy_address, "https": proxy_address}

        logger.info(f"Scraping with headers: {headers}, proxies: {proxies}")
        time.sleep(request_delay)

        try:
            response = session.get(url, headers=headers, proxies=proxies, timeout=10)
            if response.status_code == 200:
                logger.info("Scraped listing successfully.")
                request_count += 1
                return response
            else:
                logger.info(
                    f"Request to {url} failed with status {response.status_code}: {response.text}"
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed with {proxies}: {e}, retrying...")

        retries += 1

    logger.error("Max retries exceeded. Returning None.")
    return None



def make_search_request(url, max_pages=5, max_retries=3):
    all_links = []
    for page in range(1, max_pages + 1):
        page_url = f"{url}/pg-{page}"
        retries = 0
        client = ScrapingAntClient(token=scraping_api_key)
        time.sleep(random.uniform(1, 3))  # Add random delay between requests
        while retries < max_retries:
            headers = get_random_headers()
            logger.info(f"Scraping page {page} with headers: {headers}")
            time.sleep(random.uniform(1, 3))  # Add random delay between requests

            try:
                js_snippet = "ZDJsdVpHOTNMbk5qY205c2JGUnZLREFzWkc5amRXMWxiblF1WW05a2VTNXpZM0p2Ykd4SVpXbG5hSFFwT3dwaGQyRnBkQ0J1WlhjZ1VISnZiV2x6WlNoeUlEMCtJSE5sZEZScGJXVnZkWFFvY2l3Z01qQXdNQ2twT3c9PQ=="

                result = client.general_request(
                    url=page_url, js_snippet=js_snippet, return_page_source=True
                )

                if result and result.content:
                    soup = BeautifulSoup(result.content, "html.parser")
                    links = [
                        listing["href"]
                        for listing in soup.find_all("a", href=True)
                        if "realestateandhomes-detail" in listing["href"]
                        or "realestateandhomes-search" in listing["href"]
                    ]
                    all_links.extend(links)
                else:
                    logger.error(
                        f"No content received from ScrapingAnt API for page {page}"
                    )
                    break

            except Exception as e:
                logger.error(f"Unexpected error fetching page {page}: {e}, retrying...")
                retries += 1
                continue

            retries = 0
            break

    base_url = "https://www.realtor.com"
    unique_links = list(set(all_links))
    hyperlinks = [
        base_url + link if link.startswith("/") else link for link in unique_links
    ]
    return hyperlinks
