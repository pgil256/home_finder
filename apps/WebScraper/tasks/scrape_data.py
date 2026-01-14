from celery import shared_task
from celery_progress.backend import ProgressRecorder
import logging
from datetime import timedelta
from django.utils import timezone
from apps.WebScraper.models import PropertyListing

logger = logging.getLogger(__name__)

# Cache duration for recently scraped properties
CACHE_HOURS = 24


@shared_task(bind=True)
def scrape_pinellas_properties(self, search_criteria, limit=10):
    """
    Scrape property data from Pinellas County Property Appraiser.

    Uses parallel browser instances for faster scraping and skips
    properties that were scraped within the last 24 hours.
    """
    progress_recorder = ProgressRecorder(self)
    progress_recorder.set_progress(0, 100, description="Starting property scraper...")

    property_ids = []
    cached_count = 0

    try:
        # Lazy import to avoid loading selenium at startup
        from .pcpao_scraper import PCPAOScraper
        scraper = PCPAOScraper(headless=True)
        logger.info(f"Starting PCPAO scraping with criteria: {search_criteria}, limit: {limit}")

        # Step 1: Search for parcels (uses one browser instance)
        progress_recorder.set_progress(5, 100, description="Searching for properties...")
        scraper.setup_driver()
        try:
            parcels = scraper.search_properties_with_urls(search_criteria)
            if limit:
                parcels = parcels[:limit]
        finally:
            scraper.close_driver()

        if not parcels:
            progress_recorder.set_progress(100, 100, description="No properties found")
            return {'property_ids': [], 'search_criteria': search_criteria}

        logger.info(f"Found {len(parcels)} parcels to process")

        # Step 2: Check cache - skip properties scraped within CACHE_HOURS
        parcel_ids = [p['parcel_id'] for p in parcels]
        cache_cutoff = timezone.now() - timedelta(hours=CACHE_HOURS)

        cached_parcels = set(
            PropertyListing.objects.filter(
                parcel_id__in=parcel_ids,
                last_scraped__gte=cache_cutoff
            ).values_list('parcel_id', flat=True)
        )

        parcels_to_scrape = [p for p in parcels if p['parcel_id'] not in cached_parcels]
        cached_count = len(cached_parcels)

        logger.info(f"Cache check: {cached_count} cached (< {CACHE_HOURS}h old), "
                    f"{len(parcels_to_scrape)} need scraping")

        # Add cached parcel IDs to results
        property_ids.extend(cached_parcels)

        # Step 3: Scrape non-cached properties in parallel
        if parcels_to_scrape:
            progress_recorder.set_progress(10, 100,
                description=f"Scraping {len(parcels_to_scrape)} properties ({cached_count} cached)...")

            properties = scraper.scrape_properties_parallel(
                parcels_to_scrape,
                max_workers=3
            )

            total_to_save = len(properties)
            logger.info(f"Scraped {total_to_save} properties, saving to database")

            for i, property_data in enumerate(properties, 1):
                progress_recorder.set_progress(
                    10 + int((i / total_to_save) * 85),
                    100,
                    description=f"Saving property {i}/{total_to_save}..."
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
                        'image_url': property_data.get('image_url'),
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

        total_properties = len(property_ids)
        progress_recorder.set_progress(100, 100,
            description=f"Completed: {total_properties} properties ({cached_count} cached, {total_properties - cached_count} scraped)")

    except Exception as e:
        logger.error(f"Error in scrape_pinellas_properties: {e}")
        raise

    return {
        'property_ids': property_ids,
        'search_criteria': search_criteria,
        'cached_count': cached_count
    }


@shared_task(bind=True)
def scrape_tax_data(self, scrape_result):
    """
    Tax data passthrough - tax data now comes from PCPAO bulk import only.

    The real-time tax collector scraper has been disabled because:
    1. pinellastaxcollector.gov doesn't have property-specific tax data
    2. pinellas.county-taxes.com has Cloudflare protection

    Tax data should be populated via the PCPAO bulk data import command:
        python manage.py import_pcpao_data

    This task is preserved for pipeline compatibility.
    """
    progress_recorder = ProgressRecorder(self)

    property_ids = scrape_result.get('property_ids', [])
    search_criteria = scrape_result.get('search_criteria', {})
    cached_count = scrape_result.get('cached_count', 0)

    logger.info(f"Tax data passthrough: {len(property_ids)} properties (tax data from PCPAO bulk import)")

    progress_recorder.set_progress(100, 100,
        description="Tax data sourced from PCPAO bulk import")

    return {
        'status': 'Tax data from PCPAO bulk import',
        'property_ids': property_ids,
        'total_processed': len(property_ids),
        'search_criteria': search_criteria,
        'cached_count': cached_count
    }