"""
PCPAO Bulk Data Importer

Imports property data from PCPAO CSV downloads.
Data source: https://www.pcpao.gov/tools-data/data-downloads/raw-database-files

PCPAO serves files as zipped CSVs via a POST endpoint (the public download buttons
on the page POST to /dal/databasefile/downloadDatabaseFile with hdn_tbl_name and
hdn_ftype). The legacy /Data/Downloads/<file>.csv path no longer exists.
"""

import io
import logging
import os
import zipfile
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.db import transaction

from apps.WebScraper.models import PropertyListing

logger = logging.getLogger(__name__)

PCPAO_DOWNLOAD_URL = 'https://www.pcpao.gov/dal/databasefile/downloadDatabaseFile'
PCPAO_DOWNLOAD_TIMEOUT = 600  # PCPAO files can be 100MB+; allow 10 min


# PCPAO CSV column to PropertyListing field mapping
# Based on RP_PROPERTY_INFO file structure
FIELD_MAPPING = {
    'PARCEL_ID': 'parcel_id',
    'SITE_ADDR': 'address',
    'SITE_CITY': 'city',
    'SITE_ZIP': 'zip_code',
    'OWN_NAME': 'owner_name',
    'JV': 'market_value',  # Just Value = Market Value
    'AV': 'assessed_value',  # Assessed Value
    'LIV_AREA': 'building_sqft',  # Living Area
    'YR_BLT': 'year_built',
    'BEDS': 'bedrooms',
    'BATHS': 'bathrooms',
    'DOR_UC': 'property_type',  # DOR Use Code
    'LAND_SQFT': 'lot_sqft',
    'TAX_AMOUNT_NO_EX': 'tax_amount',  # Tax amount from PCPAO
}


def download_pcpao_file(filename: str, output_dir: str) -> str:
    """
    Download a PCPAO data file. PCPAO returns a zip; we extract the CSV inside.

    Args:
        filename: Database table name (e.g., 'RP_PROPERTY_INFO')
        output_dir: Directory to save the extracted CSV file

    Returns:
        Path to the extracted CSV file.
    """
    output_path = os.path.join(output_dir, f'{filename}.csv')
    logger.info(f'Downloading {filename} from {PCPAO_DOWNLOAD_URL}')

    response = requests.post(
        PCPAO_DOWNLOAD_URL,
        data={'hdn_tbl_name': filename, 'hdn_ftype': 'csv'},
        timeout=PCPAO_DOWNLOAD_TIMEOUT,
    )
    response.raise_for_status()

    content_type = response.headers.get('Content-Type', '')
    if 'zip' not in content_type.lower():
        raise RuntimeError(
            f'Expected zip from PCPAO, got Content-Type={content_type!r}; the download endpoint may have changed again.'
        )

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
        if not csv_names:
            raise RuntimeError(f'No CSV inside PCPAO zip: {zf.namelist()}')
        # Prefer the file whose basename matches the requested table
        target = next(
            (n for n in csv_names if filename.lower() in n.lower()),
            csv_names[0],
        )
        with zf.open(target) as src, open(output_path, 'wb') as dst:
            dst.write(src.read())

    logger.info(f'Extracted {target} to {output_path}')
    return output_path


def safe_decimal(value: str) -> Decimal | None:
    """Convert string to Decimal, returning None for empty/invalid values."""
    if not value or value.strip() == '':
        return None
    try:
        return Decimal(value.replace(',', '').strip())
    except InvalidOperation:
        return None


def safe_int(value: str) -> int | None:
    """Convert string to int, returning None for empty/invalid values."""
    if not value or value.strip() == '':
        return None
    try:
        return int(float(value.replace(',', '').strip()))
    except (ValueError, TypeError):
        return None


_CITY_FIXUPS = {
    'St Petersburg': 'St. Petersburg',
    'St Pete Beach': 'St. Pete Beach',
}


def _normalize_city(value: str | None) -> str | None:
    """PCPAO ships city names uppercased ('ST PETERSBURG'); convert to the
    canonical title-cased form the search form's dropdown uses
    ('St. Petersburg')."""
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    titled = s.title().replace("'S", "'s")
    return _CITY_FIXUPS.get(titled, titled)


def _split_property_use(value: str) -> str | None:
    """PROPERTY_USE in the new schema looks like '0110 Single Family Home'.
    Return the human-readable description (everything after the leading code)."""
    if not value:
        return None
    parts = value.strip().split(None, 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1].strip() or None
    return value.strip() or None


def map_csv_row_to_property(row: dict[str, str]) -> dict[str, Any]:
    """Map a PCPAO RP_PROPERTY_INFO row to PropertyListing fields.

    Schema reference:
      - PARCEL_NUMBER, SITE_ADDRESS, STR_CITY, STR_ZIP, OWNER1
      - CNTY_JST_VALUE (just/market value), CNTY_ASD_VALUE (assessed)
      - TOTAL_LIVING_SQFT, YEAR_BUILT, ACREAGE
      - PROPERTY_USE (e.g. '0110 Single Family Home')
      - TAX_AMOUNT_NO_EX

    Beds/baths aren't in this table — they live in RP_BUILDING (not yet imported).
    """
    result: dict[str, Any] = {}

    result['parcel_id'] = row.get('PARCEL_NUMBER', '').strip()
    result['address'] = (row.get('SITE_ADDRESS') or '').strip() or None
    result['city'] = _normalize_city(row.get('STR_CITY'))
    result['zip_code'] = (row.get('STR_ZIP') or '').strip() or None
    result['owner_name'] = (row.get('OWNER1') or '').strip() or None
    result['property_type'] = _split_property_use(row.get('PROPERTY_USE', '')) or 'Unknown'

    result['market_value'] = safe_decimal(row.get('CNTY_JST_VALUE', ''))
    result['assessed_value'] = safe_decimal(row.get('CNTY_ASD_VALUE', ''))

    result['building_sqft'] = safe_int(row.get('TOTAL_LIVING_SQFT', ''))
    result['year_built'] = safe_int(row.get('YEAR_BUILT', ''))

    # ACREAGE → land_size (acres) and lot_sqft (1 acre = 43,560 sqft)
    acreage = safe_decimal(row.get('ACREAGE', ''))
    if acreage is not None:
        result['land_size'] = acreage
        result['lot_sqft'] = int(acreage * Decimal('43560'))
    else:
        result['land_size'] = None
        result['lot_sqft'] = None

    result['tax_amount'] = safe_decimal(row.get('TAX_AMOUNT_NO_EX', ''))
    if result['tax_amount'] is not None:
        result['tax_status'] = 'From PCPAO'

    return result


def bulk_upsert_properties(properties: list[dict[str, Any]], batch_size: int = 1000) -> dict[str, int]:
    """
    Bulk insert or update property records.

    Uses batch operations to avoid N+1 query pattern:
    - Single query to find existing records
    - bulk_create for new records
    - bulk_update for existing records

    Args:
        properties: List of property dictionaries with PropertyListing fields
        batch_size: Number of records to process per batch

    Returns:
        Dictionary with 'created' and 'updated' counts
    """
    stats = {'created': 0, 'updated': 0}

    # Filter out properties without parcel_id
    valid_properties = [p for p in properties if p.get('parcel_id')]
    if not valid_properties:
        return stats

    # Get all parcel IDs we're processing
    parcel_ids = [p['parcel_id'] for p in valid_properties]

    with transaction.atomic():
        # Single query to find all existing records (N+1 fix)
        existing_records = {p.parcel_id: p for p in PropertyListing.objects.filter(parcel_id__in=parcel_ids)}

        # Separate into new and existing
        new_properties = []
        properties_to_update = []

        # Fields to update (excluding parcel_id which is the lookup key)
        update_fields = [
            'address',
            'city',
            'zip_code',
            'owner_name',
            'market_value',
            'assessed_value',
            'building_sqft',
            'year_built',
            'bedrooms',
            'bathrooms',
            'property_type',
            'land_size',
            'lot_sqft',
            'tax_amount',
            'tax_status',
        ]

        for prop in valid_properties:
            parcel_id = prop['parcel_id']
            existing = existing_records.get(parcel_id)

            if existing:
                # Update existing record in memory
                for field in update_fields:
                    if field in prop:
                        setattr(existing, field, prop[field])
                properties_to_update.append(existing)
            else:
                # Create new PropertyListing instance
                new_properties.append(
                    PropertyListing(parcel_id=parcel_id, **{k: v for k, v in prop.items() if k != 'parcel_id'})
                )

        # Bulk create new records (single query)
        if new_properties:
            PropertyListing.objects.bulk_create(new_properties, batch_size=batch_size)
            stats['created'] = len(new_properties)

        # Bulk update existing records (single query)
        if properties_to_update:
            PropertyListing.objects.bulk_update(properties_to_update, update_fields, batch_size=batch_size)
            stats['updated'] = len(properties_to_update)

    return stats
