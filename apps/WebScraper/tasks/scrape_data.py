import logging
from datetime import timedelta

from django.utils import timezone

from apps.WebScraper.models import PropertyListing

logger = logging.getLogger(__name__)

CACHE_HOURS = 24
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2


def filter_properties_by_criteria(properties, search_criteria):
    """
    Filter scraped properties by search criteria.

    PCPAO Quick Search only supports keyword search, so we post-filter
    the results to match the user's actual criteria.
    """
    filtered = []

    requested_types = search_criteria.get('property_type', [])
    if isinstance(requested_types, str):
        requested_types = [requested_types]
    requested_types_lower = [t.lower() for t in requested_types] if requested_types else []

    min_value = search_criteria.get('min_value')
    max_value = search_criteria.get('max_value')

    try:
        min_value = float(min_value) if min_value else None
    except (ValueError, TypeError):
        min_value = None
    try:
        max_value = float(max_value) if max_value else None
    except (ValueError, TypeError):
        max_value = None

    for prop in properties:
        if requested_types_lower:
            prop_type = (prop.get('property_type') or '').lower()
            type_match = any(req_type in prop_type for req_type in requested_types_lower)
            if not type_match:
                continue

        market_value = prop.get('market_value')
        if market_value is not None:
            try:
                market_value = float(market_value)
            except (ValueError, TypeError):
                market_value = None

        if min_value is not None and market_value is not None and market_value < min_value:
            continue
        if max_value is not None and market_value is not None and market_value > max_value:
            continue

        bedrooms_min = search_criteria.get('bedrooms_min')
        if bedrooms_min:
            try:
                bedrooms_min_val = int(bedrooms_min)
                prop_bedrooms = prop.get('bedrooms')
                if prop_bedrooms is not None and prop_bedrooms < bedrooms_min_val:
                    continue
            except (ValueError, TypeError):
                pass

        bathrooms_min = search_criteria.get('bathrooms_min')
        if bathrooms_min:
            try:
                bathrooms_min_val = float(bathrooms_min)
                prop_bathrooms = prop.get('bathrooms')
                if prop_bathrooms is not None and float(prop_bathrooms) < bathrooms_min_val:
                    continue
            except (ValueError, TypeError):
                pass

        year_built_after = search_criteria.get('year_built_after')
        if year_built_after:
            try:
                year_built_min = int(year_built_after)
                prop_year = prop.get('year_built')
                if prop_year is not None and prop_year < year_built_min:
                    continue
            except (ValueError, TypeError):
                pass

        sqft_min = search_criteria.get('sqft_min')
        if sqft_min:
            try:
                sqft_min_val = int(sqft_min)
                prop_sqft = prop.get('building_sqft')
                if prop_sqft is not None and prop_sqft < sqft_min_val:
                    continue
            except (ValueError, TypeError):
                pass

        sqft_max = search_criteria.get('sqft_max')
        if sqft_max:
            try:
                sqft_max_val = int(sqft_max)
                prop_sqft = prop.get('building_sqft')
                if prop_sqft is not None and prop_sqft > sqft_max_val:
                    continue
            except (ValueError, TypeError):
                pass

        tax_status_filter = search_criteria.get('tax_status')
        if tax_status_filter:
            prop_tax_status = prop.get('tax_status')
            if prop_tax_status is not None and prop_tax_status != tax_status_filter:
                continue

        filtered.append(prop)

    return filtered


def run_scrape(search_criteria, limit=10):
    """
    Scrape property data from PCPAO synchronously and persist to the DB.

    Returns a list of parcel_ids that ended up in the result set
    (cached + freshly scraped, capped at `limit`).
    """
    from .pcpao_scraper import PCPAOScraper
    import requests as req
    import time as _time

    scraper = PCPAOScraper(headless=True)
    logger.info("Starting PCPAO scrape: criteria=%s limit=%s", search_criteria, limit)

    parcels = scraper._search_via_api(search_criteria, limit=limit)
    if not parcels:
        return []

    parcel_ids = [p['parcel_id'] for p in parcels]
    cache_cutoff = timezone.now() - timedelta(hours=CACHE_HOURS)
    cached_parcels = set(
        PropertyListing.objects.filter(
            parcel_id__in=parcel_ids,
            last_scraped__gte=cache_cutoff,
        ).values_list('parcel_id', flat=True)
    )
    parcels_to_scrape = [p for p in parcels if p['parcel_id'] not in cached_parcels]
    logger.info("Cache: %d hits, %d to scrape", len(cached_parcels), len(parcels_to_scrape))

    property_ids = []

    if cached_parcels:
        cached_listings = PropertyListing.objects.filter(parcel_id__in=cached_parcels)
        cached_properties = [{
            'parcel_id': l.parcel_id,
            'property_type': l.property_type,
            'market_value': l.market_value,
            'bedrooms': l.bedrooms,
            'bathrooms': l.bathrooms,
            'year_built': l.year_built,
            'building_sqft': l.building_sqft,
            'tax_status': l.tax_status,
        } for l in cached_listings]
        filtered_cached = filter_properties_by_criteria(cached_properties, search_criteria)
        property_ids.extend([p['parcel_id'] for p in filtered_cached])

    if parcels_to_scrape:
        session = req.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

        properties = []
        for i, parcel_info in enumerate(parcels_to_scrape):
            p_id = parcel_info['parcel_id']
            d_url = parcel_info.get('detail_url')
            prop_data = {'parcel_id': p_id}
            if d_url:
                for attempt in range(MAX_RETRIES):
                    try:
                        prop_data = scraper._scrape_detail_via_requests(p_id, d_url, session=session)
                        break
                    except (req.exceptions.RequestException, req.exceptions.Timeout) as e:
                        wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning("Retry %d/%d for %s: %s (waiting %ds)",
                                       attempt + 1, MAX_RETRIES, p_id, e, wait)
                        _time.sleep(wait)
                else:
                    logger.error("Failed to scrape %s after %d retries", p_id, MAX_RETRIES)
            if len(prop_data) > 1:
                properties.append(prop_data)
            if i < len(parcels_to_scrape) - 1:
                _time.sleep(0.3)

        properties = filter_properties_by_criteria(properties, search_criteria)
        logger.info("Saving %d properties to database", len(properties))

        optional_fields = (
            'address', 'city', 'zip_code', 'owner_name',
            'market_value', 'assessed_value', 'building_sqft',
            'year_built', 'bedrooms', 'bathrooms', 'land_size',
            'lot_sqft', 'appraiser_url', 'image_url',
            'tax_collector_url', 'tax_amount', 'tax_year',
        )
        for property_data in properties:
            parcel_id = property_data.get('parcel_id')
            if not parcel_id:
                continue
            defaults = {'property_type': property_data.get('property_type', 'Unknown')}
            for field in optional_fields:
                value = property_data.get(field)
                if value is not None:
                    defaults[field] = value
            tax_status = property_data.get('tax_status')
            if tax_status and tax_status != 'Unknown':
                defaults['tax_status'] = tax_status
            PropertyListing.objects.update_or_create(parcel_id=parcel_id, defaults=defaults)
            property_ids.append(parcel_id)

    if limit and len(property_ids) > limit:
        property_ids = property_ids[:limit]

    logger.info("Scrape complete: %d properties", len(property_ids))
    return property_ids


# Optional fields the per-parcel refresh persists into PropertyListing.
# Mirrors the keys `_scrape_detail_via_requests` returns; nullable in the
# model. We only overwrite when the new value is not None so a partial
# response doesn't wipe data populated by the bulk import.
_REFRESH_OPTIONAL_FIELDS = (
    'address', 'city', 'zip_code', 'owner_name',
    'market_value', 'assessed_value', 'building_sqft',
    'year_built', 'bedrooms', 'bathrooms', 'land_size',
    'lot_sqft', 'appraiser_url', 'image_url',
    'tax_collector_url', 'tax_amount', 'tax_year',
)


class ParcelNotFoundError(Exception):
    """PCPAO returned no results for the parcel ID."""


def refresh_one_parcel(parcel_id: str) -> "PropertyListing":
    """Fetch fresh data for a single parcel from PCPAO and upsert it.

    Used by the per-property "Refresh" button on the detail page.

    Returns the updated `PropertyListing` instance on success.
    Raises `ParcelNotFoundError` if PCPAO has no record for this parcel,
    or `requests.RequestException` if the upstream scrape fails.
    """
    from .pcpao_scraper import PCPAOScraper
    import requests as req

    scraper = PCPAOScraper(headless=True)

    # Search PCPAO for this parcel ID specifically. The scraper's
    # _search_via_api recognizes a `parcel_id` key and switches the
    # PCPAO `searchsort` parameter to `parcel_number` (other sorts
    # return zero results for parcel-ID queries).
    parcels = scraper._search_via_api({'parcel_id': parcel_id}, limit=5)
    match = next((p for p in parcels if p['parcel_id'] == parcel_id), None)
    if not match or not match.get('detail_url'):
        raise ParcelNotFoundError(f"PCPAO returned no detail URL for {parcel_id}")

    session = req.Session()
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
    })

    last_error: Exception | None = None
    prop_data: dict | None = None
    for attempt in range(MAX_RETRIES):
        try:
            prop_data = scraper._scrape_detail_via_requests(
                parcel_id, match['detail_url'], session=session
            )
            break
        except (req.exceptions.RequestException, req.exceptions.Timeout) as e:
            last_error = e
            wait = RETRY_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Refresh retry %d/%d for %s: %s (waiting %ds)",
                attempt + 1, MAX_RETRIES, parcel_id, e, wait,
            )
            import time as _time
            _time.sleep(wait)
    if prop_data is None:
        raise last_error or RuntimeError(
            f"Failed to refresh parcel {parcel_id} after {MAX_RETRIES} retries"
        )

    defaults: dict = {}
    if prop_data.get('property_type'):
        defaults['property_type'] = prop_data['property_type']
    for field in _REFRESH_OPTIONAL_FIELDS:
        value = prop_data.get(field)
        if value is not None:
            defaults[field] = value
    tax_status = prop_data.get('tax_status')
    if tax_status and tax_status != 'Unknown':
        defaults['tax_status'] = tax_status

    listing, _created = PropertyListing.objects.update_or_create(
        parcel_id=parcel_id, defaults=defaults,
    )
    logger.info("Refreshed parcel %s (pk=%s)", parcel_id, listing.pk)
    return listing
