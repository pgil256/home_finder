from celery import shared_task
from celery_progress.backend import ProgressRecorder
import logging
from apps.WebScraper.models import PropertyListing
from .pcpao_scraper import PCPAOScraper
from .tax_collector_scraper import TaxCollectorScraper

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def scrape_pinellas_properties(self, search_criteria, limit=10):
    """
    Scrape property data from Pinellas County Property Appraiser
    """
    progress_recorder = ProgressRecorder(self)
    progress_recorder.set_progress(0, 100, description="Starting property scraper...")

    property_ids = []

    try:
        scraper = PCPAOScraper(headless=True)
        logger.info(f"Starting PCPAO scraping with criteria: {search_criteria}, limit: {limit}")

        properties = scraper.scrape_by_criteria(search_criteria, limit)
        total_properties = len(properties)
        logger.info(f"Found {total_properties} properties to process")

        for i, property_data in enumerate(properties, 1):
            progress_recorder.set_progress(
                int((i / total_properties) * 100),
                100,
                description=f"Processing property {i}/{total_properties}..."
            )

            parcel_id = property_data.get('parcel_id')
            if parcel_id:
                listing, created = PropertyListing.objects.update_or_create(
                    parcel_id=parcel_id,
                    defaults={
                        'address': property_data.get('address', ''),
                        'city': property_data.get('city', ''),
                        'zip_code': property_data.get('zip_code', ''),
                        'owner_name': property_data.get('owner_name'),
                        'market_value': property_data.get('market_value'),
                        'assessed_value': property_data.get('assessed_value'),
                        'building_sqft': property_data.get('building_sqft'),
                        'year_built': property_data.get('year_built'),
                        'bedrooms': property_data.get('bedrooms'),
                        'bathrooms': property_data.get('bathrooms'),
                        'property_type': property_data.get('property_type', 'Unknown'),
                        'land_size': property_data.get('land_size'),
                        'lot_sqft': property_data.get('lot_sqft'),
                        'appraiser_url': property_data.get('appraiser_url'),
                    }
                )
                property_ids.append(parcel_id)

        progress_recorder.set_progress(100, 100, description=f"Completed {total_properties} properties")

    except Exception as e:
        logger.error(f"Error in scrape_pinellas_properties: {e}")
        raise

    return {
        'property_ids': property_ids,
        'search_criteria': search_criteria
    }


@shared_task(bind=True)
def scrape_tax_data(self, scrape_result):
    """
    Scrape tax information for the given property IDs
    """
    progress_recorder = ProgressRecorder(self)
    progress_recorder.set_progress(0, 100, description="Starting tax data collection...")

    property_ids = scrape_result.get('property_ids', [])
    search_criteria = scrape_result.get('search_criteria', {})

    updated_properties = []

    try:
        scraper = TaxCollectorScraper(headless=True)
        total_properties = len(property_ids)
        logger.info(f"Starting tax data collection for {total_properties} properties")

        tax_data_list = scraper.scrape_batch(property_ids)

        for i, tax_data in enumerate(tax_data_list, 1):
            progress_recorder.set_progress(
                int((i / total_properties) * 100),
                100,
                description=f"Processing tax data {i}/{total_properties}..."
            )

            parcel_id = tax_data.get('parcel_id')
            if parcel_id:
                try:
                    property_listing = PropertyListing.objects.get(parcel_id=parcel_id)
                    property_listing.tax_amount = tax_data.get('tax_amount')
                    property_listing.tax_status = tax_data.get('tax_status', 'Unknown')
                    property_listing.delinquent = tax_data.get('delinquent', False)
                    property_listing.tax_year = tax_data.get('tax_year')
                    property_listing.tax_collector_url = tax_data.get('tax_collector_url')
                    property_listing.save()
                    updated_properties.append(parcel_id)

                except PropertyListing.DoesNotExist:
                    logger.warning(f"Property listing not found for parcel {parcel_id}")

        progress_recorder.set_progress(100, 100, description=f"Completed tax data for {len(updated_properties)} properties")

    except Exception as e:
        logger.error(f"Error in scrape_tax_data: {e}")
        raise

    return {
        'status': 'Tax data collection completed',
        'updated_properties': updated_properties,
        'total_processed': len(updated_properties),
        'search_criteria': search_criteria
    }