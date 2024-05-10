from celery import shared_task
from celery_progress.backend import ProgressRecorder
import logging
from bs4 import BeautifulSoup
from .request_manager import make_listing_request, make_search_request
from apps.WebScraper.models import PropertyListing

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

@shared_task(bind=True)
def scrape_website(self, scrape_config):
    progress_recorder = ProgressRecorder(self)

    if not isinstance(scrape_config, dict):
        logger.error(f"Invalid scrape_config: Expected dict, got {type(scrape_config).__name__}")
        return {"status": "Invalid configuration format", "data": scrape_config}

    location = scrape_config.get("Location")
    if not location:
        logger.error("Missing location in scrape configuration")
        return {"status": "Missing location", "data": scrape_config}

    hyperlinks = scrape_main_page(location)
    total_links = len(hyperlinks)
    logger.info(f"Scraped the following links: {total_links}")

    if hyperlinks:
        count = 0
        for count, hyperlink in enumerate(hyperlinks, 1):
            new_listing = scrape_listings(hyperlink)
            if new_listing:
                PropertyListing.objects.create(**new_listing)
                logger.info(f"Database updated with new listing from {hyperlink}.")
            else:
                logger.error(f"Failed to retrieve listing data from {hyperlink}")

            progress_recorder.set_progress(count, total_links, description=f"Gathering listings... ({count}/{total_links})")

        return {"status": "Scraping completed", "data": scrape_config}
    else:
        logger.info("No hyperlinks returned.")
        return {"status": "No hyperlinks found", "data": scrape_config}

def scrape_listings(hyperlink):
    url = hyperlink
    try:
        response = make_listing_request(url)
        if response.status_code == 200:
            listing_soup = BeautifulSoup(response.content, "html.parser")
            script_content = listing_soup.select_one("#__NEXT_DATA__").text
            data_json = json.loads(script_content)
            return extract_listing_details(data_json, hyperlink)
        else:
            logger.error(f"HTTP status code {response.status_code} encountered for {url}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing {url}: {str(e)}")
        return None

def extract_listing_details(data_json, hyperlink):
    try:
        details = data_json["props"]["pageProps"]["initialReduxState"]["propertyDetails"]
        mortgage = details.get("mortgage", {})
        description = details.get("description", {})
        location = details.get("location", {})
        primary_photo = details.get("primary_photo", {})
        return {
            "link": hyperlink,
            "address": location.get("address", {}).get("line", "Unknown Address"),
            "image_of_property": primary_photo.get("href", "No image available"),
            "description": description.get("text", "No description available"),
            "price": details.get("list_price", "Price not available"),
            "bedrooms": description.get("beds", "Not specified"),
            "bathrooms": description.get("baths", "Not specified"),
            "stories": description.get("stories", "Not specified"),
            "home_size": description.get("sqft", "Size not specified"),
            "lot_size": description.get("lot_sqft", "Lot size not specified"),
            "property_type": description.get("type", "Type not specified"),
            "price_per_sqft": details.get("price_per_sqft", "Not available"),
            "garage": description.get("garage", "Garage details not specified"),
            "year_built": description.get("year_built", "Year not specified"),
            "time_on_market": details.get("days_on_market", "Time on market not specified"),
            "estimated_monthly_payment": mortgage.get("estimate", {}).get("monthly_payment", "Not specified"),
            "home_insurance": mortgage.get("estimate", {}).get("monthly_payment_details", [{}])[1].get("amount", "Not specified"),
            "hoa_fees": mortgage.get("estimate", {}).get("monthly_payment_details", [{}])[2].get("amount", "Not specified"),
            "mortgage_insurance": mortgage.get("estimate", {}).get("monthly_payment_details", [{}])[3].get("amount", "Not specified"),
            "property_tax": mortgage.get("estimate", {}).get("monthly_payment_details", [{}])[4].get("amount", "Not specified"),
        }
    except KeyError as e:
        logger.error(f"Key error in data extraction for hyperlink {hyperlink}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during data extraction for hyperlink {hyperlink}: {str(e)}")
        return None

def scrape_main_page(location):
    url = f"https://www.realtor.com/realestateandhomes-search/{location}"
    logger.info(f"Fetching main page for location: {location}")

    try:
        hyperlinks = make_search_request(url)
        return hyperlinks
    except Exception as e:
        logger.error(f"Error fetching main page {url}: {str(e)}")
        return []
