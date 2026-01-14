"""Google Street View Static API integration."""

import logging
import urllib.parse
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Log warning once if API key missing
_api_key_warning_logged = False


def get_street_view_url(
    address: str,
    city: str = None,
    zip_code: str = None,
    size: str = None
) -> Optional[str]:
    """Build Google Street View Static API URL for a property.

    Checks metadata endpoint first to verify imagery exists.

    Args:
        address: Street address (e.g., "123 Main St")
        city: City name (e.g., "Clearwater")
        zip_code: ZIP code (e.g., "33755")
        size: Image size as "WxH" (default from settings)

    Returns:
        Street View image URL if imagery exists, None otherwise.
    """
    global _api_key_warning_logged

    api_key = getattr(settings, 'GOOGLE_STREET_VIEW_API_KEY', None)
    if not api_key:
        if not _api_key_warning_logged:
            logger.warning("GOOGLE_STREET_VIEW_API_KEY not configured - images disabled")
            _api_key_warning_logged = True
        return None

    if not address:
        return None

    # Build full address string
    location_parts = [address]
    if city:
        location_parts.append(city)
    location_parts.append("FL")  # State is always Florida for this app
    if zip_code:
        location_parts.append(zip_code)

    location = ", ".join(location_parts)

    # Check if Street View imagery exists (free API call)
    if not _has_street_view_imagery(location, api_key):
        logger.debug(f"No Street View imagery for: {location}")
        return None

    # Build image URL
    size = size or getattr(settings, 'STREET_VIEW_IMAGE_SIZE', '640x480')

    params = {
        'size': size,
        'location': location,
        'key': api_key,
    }

    url = f"https://maps.googleapis.com/maps/api/streetview?{urllib.parse.urlencode(params)}"
    logger.debug(f"Street View URL generated for: {location}")
    return url


def _has_street_view_imagery(location: str, api_key: str) -> bool:
    """Check if Street View imagery exists for a location.

    Uses the metadata endpoint which is free and doesn't count
    against the image API quota.

    Args:
        location: Full address string
        api_key: Google API key

    Returns:
        True if imagery exists, False otherwise.
    """
    metadata_url = "https://maps.googleapis.com/maps/api/streetview/metadata"

    params = {
        'location': location,
        'key': api_key,
    }

    try:
        response = requests.get(metadata_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get('status') == 'OK'
    except requests.RequestException as e:
        logger.warning(f"Street View metadata check failed for {location}: {e}")
        return False
