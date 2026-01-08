"""
PCPAO Bulk Data Importer

Imports property data from PCPAO CSV downloads.
Data source: https://www.pcpao.gov/tools-data/data-downloads/raw-database-files
"""
import os
import requests
import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# PCPAO data download URL pattern
PCPAO_DATA_URL = "https://www.pcpao.gov/Data/Downloads/{filename}.csv"


# PCPAO CSV column to PropertyListing field mapping
# Based on RP_PROPERTY_INFO file structure
FIELD_MAPPING = {
    'PARCEL_ID': 'parcel_id',
    'SITE_ADDR': 'address',
    'SITE_CITY': 'city',
    'SITE_ZIP': 'zip_code',
    'OWN_NAME': 'owner_name',
    'JV': 'market_value',        # Just Value = Market Value
    'AV': 'assessed_value',       # Assessed Value
    'LIV_AREA': 'building_sqft',  # Living Area
    'YR_BLT': 'year_built',
    'BEDS': 'bedrooms',
    'BATHS': 'bathrooms',
    'DOR_UC': 'property_type',    # DOR Use Code
    'LAND_SQFT': 'lot_sqft',
}


def download_pcpao_file(filename: str, output_dir: str) -> str:
    """
    Download a PCPAO data file.

    Args:
        filename: Name of the file (e.g., 'RP_PROPERTY_INFO')
        output_dir: Directory to save the downloaded file

    Returns:
        Path to the downloaded file
    """
    url = PCPAO_DATA_URL.format(filename=filename)
    output_path = os.path.join(output_dir, f"{filename}.csv")

    logger.info(f"Downloading {filename} from {url}")

    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    logger.info(f"Downloaded {filename} to {output_path}")
    return output_path


def safe_decimal(value: str) -> Optional[Decimal]:
    """Convert string to Decimal, returning None for empty/invalid values."""
    if not value or value.strip() == '':
        return None
    try:
        return Decimal(value.replace(',', '').strip())
    except InvalidOperation:
        return None


def safe_int(value: str) -> Optional[int]:
    """Convert string to int, returning None for empty/invalid values."""
    if not value or value.strip() == '':
        return None
    try:
        return int(float(value.replace(',', '').strip()))
    except (ValueError, TypeError):
        return None


def map_csv_row_to_property(row: Dict[str, str]) -> Dict[str, Any]:
    """
    Map a PCPAO CSV row to PropertyListing fields.

    Args:
        row: Dictionary with CSV column names as keys

    Returns:
        Dictionary with PropertyListing field names and converted values
    """
    result = {}

    # String fields
    result['parcel_id'] = row.get('PARCEL_ID', '').strip()
    result['address'] = row.get('SITE_ADDR', '').strip() or None
    result['city'] = row.get('SITE_CITY', '').strip() or None
    result['zip_code'] = row.get('SITE_ZIP', '').strip() or None
    result['owner_name'] = row.get('OWN_NAME', '').strip() or None
    result['property_type'] = row.get('DOR_UC', '').strip() or 'Unknown'

    # Decimal fields
    result['market_value'] = safe_decimal(row.get('JV', ''))
    result['assessed_value'] = safe_decimal(row.get('AV', ''))
    result['bathrooms'] = safe_decimal(row.get('BATHS', ''))

    # Integer fields
    result['building_sqft'] = safe_int(row.get('LIV_AREA', ''))
    result['year_built'] = safe_int(row.get('YR_BLT', ''))
    result['bedrooms'] = safe_int(row.get('BEDS', ''))
    result['lot_sqft'] = safe_int(row.get('LAND_SQFT', ''))

    # Calculate land_size in acres from lot_sqft
    if result['lot_sqft']:
        result['land_size'] = Decimal(str(result['lot_sqft'])) / Decimal('43560')
    else:
        result['land_size'] = None

    return result
