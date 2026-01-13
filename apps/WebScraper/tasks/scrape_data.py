from celery import shared_task
from celery_progress.backend import ProgressRecorder
import logging
from apps.WebScraper.models import PropertyListing

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
        # Lazy import to avoid loading selenium at startup
        from .pcpao_scraper import PCPAOScraper
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
                defaults = {
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
                logger.info(f"Saving property {parcel_id} to database: "
                            f"address={defaults['address']}, city={defaults['city']}, "
                            f"market_value={defaults['market_value']}")
                listing, created = PropertyListing.objects.update_or_create(
                    parcel_id=parcel_id,
                    defaults=defaults
                )
                logger.info(f"Property {parcel_id} {'created' if created else 'updated'} in database (pk={listing.pk})")
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
    Collect tax information for the given property IDs.

    First checks if tax data already exists from PCPAO bulk import.
    Only attempts web scraping for properties missing tax data.
    """
    progress_recorder = ProgressRecorder(self)
    progress_recorder.set_progress(0, 100, description="Starting tax data collection...")

    property_ids = scrape_result.get('property_ids', [])
    search_criteria = scrape_result.get('search_criteria', {})

    updated_properties = []
    skipped_properties = []

    # Check which properties already have tax data from PCPAO
    properties_needing_tax = []
    for parcel_id in property_ids:
        try:
            listing = PropertyListing.objects.get(parcel_id=parcel_id)
            if listing.tax_amount is not None:
                # Already has tax data from PCPAO import
                skipped_properties.append(parcel_id)
                logger.info(f"Property {parcel_id} already has tax data (${listing.tax_amount}), skipping scrape")
            else:
                properties_needing_tax.append(parcel_id)
        except PropertyListing.DoesNotExist:
            properties_needing_tax.append(parcel_id)

    total_properties = len(property_ids)
    logger.info(f"Tax data collection: {len(skipped_properties)} already have tax data, "
                f"{len(properties_needing_tax)} need scraping")

    # If all properties already have tax data, we're done
    if not properties_needing_tax:
        progress_recorder.set_progress(100, 100,
            description=f"All {total_properties} properties already have tax data from PCPAO")
        return {
            'status': 'Tax data collection completed (all from PCPAO)',
            'updated_properties': skipped_properties,
            'total_processed': len(skipped_properties),
            'from_pcpao': len(skipped_properties),
            'from_scraping': 0,
            'search_criteria': search_criteria
        }

    # Attempt to scrape tax data for properties that need it
    try:
        from .tax_collector_scraper import TaxCollectorScraper
        scraper = TaxCollectorScraper(headless=True)
        logger.info(f"Attempting to scrape tax data for {len(properties_needing_tax)} properties")

        tax_data_list = scraper.scrape_batch(properties_needing_tax)

        for i, tax_data in enumerate(tax_data_list, 1):
            progress_recorder.set_progress(
                int(((len(skipped_properties) + i) / total_properties) * 100),
                100,
                description=f"Processing tax data {len(skipped_properties) + i}/{total_properties}..."
            )

            parcel_id = tax_data.get('parcel_id')
            if parcel_id:
                try:
                    property_listing = PropertyListing.objects.get(parcel_id=parcel_id)
                    # Only update if we got actual tax data
                    if tax_data.get('tax_amount') is not None:
                        property_listing.tax_amount = tax_data.get('tax_amount')
                        property_listing.tax_status = tax_data.get('tax_status', 'Unknown')
                        property_listing.delinquent = tax_data.get('delinquent', False)
                        property_listing.tax_year = tax_data.get('tax_year')
                        property_listing.tax_collector_url = tax_data.get('tax_collector_url')
                        property_listing.save()
                        updated_properties.append(parcel_id)
                    else:
                        logger.warning(f"No tax data returned for parcel {parcel_id}")

                except PropertyListing.DoesNotExist:
                    logger.warning(f"Property listing not found for parcel {parcel_id}")

        progress_recorder.set_progress(100, 100,
            description=f"Completed: {len(skipped_properties)} from PCPAO, {len(updated_properties)} scraped")

    except Exception as e:
        logger.error(f"Error in scrape_tax_data: {e}")
        raise

    return {
        'status': 'Tax data collection completed',
        'updated_properties': skipped_properties + updated_properties,
        'total_processed': len(skipped_properties) + len(updated_properties),
        'from_pcpao': len(skipped_properties),
        'from_scraping': len(updated_properties),
        'search_criteria': search_criteria
    }