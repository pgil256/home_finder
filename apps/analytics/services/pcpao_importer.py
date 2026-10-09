"""
PCPAO Bulk Data Importer

Imports property data from PCPAO CSV downloads.
Data source: https://www.pcpao.gov/tools-data/data-downloads/raw-database-files

PCPAO serves files as zipped CSVs via a POST endpoint (the public download buttons
on the page POST to /dal/databasefile/downloadDatabaseFile with hdn_tbl_name and
hdn_ftype). The legacy /Data/Downloads/<file>.csv path no longer exists.
"""

import codecs
import csv
import io
import logging
import os
import zipfile
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.db import connection, transaction

from apps.analytics.models import PropertyListing, TaxDistrictMillage
from apps.analytics.services.tax_estimate import (
    HOMESTEAD_PARCEL_TYPES,
    Millage,
    buyer_tax_year,
    estimate_current_tax,
    estimate_new_owner_tax,
    homestead_rules,
)

logger = logging.getLogger(__name__)

PCPAO_DOWNLOAD_URL = 'https://www.pcpao.gov/dal/databasefile/downloadDatabaseFile'
PCPAO_DATABASE_FILES_PAGE = 'https://www.pcpao.gov/tools-data/data-downloads/raw-database-files'
PCPAO_DOWNLOAD_TIMEOUT = 600  # PCPAO files can be 100MB+; allow 10 min
PCPAO_REQUEST_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'),
    'Referer': PCPAO_DATABASE_FILES_PAGE,
    'Origin': 'https://www.pcpao.gov',
    'Accept': 'application/zip, application/octet-stream, */*',
    'Accept-Language': 'en-US,en;q=0.9',
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

    with requests.Session() as session:
        session.headers.update(PCPAO_REQUEST_HEADERS)
        response = session.post(
            PCPAO_DOWNLOAD_URL,
            data={'hdn_tbl_name': filename, 'hdn_ftype': 'csv'},
            timeout=PCPAO_DOWNLOAD_TIMEOUT,
        )

        # PCPAO rejects generic HTTP clients. Browser-like headers are usually
        # enough; priming the official landing page supplies any session cookie
        # the county adds later without weakening TLS or bypassing access rules.
        if response.status_code == 403:
            logger.warning('PCPAO rejected the initial download request; priming a browser session and retrying once')
            landing_response = session.get(PCPAO_DATABASE_FILES_PAGE, timeout=60)
            landing_response.raise_for_status()
            response = session.post(
                PCPAO_DOWNLOAD_URL,
                data={'hdn_tbl_name': filename, 'hdn_ftype': 'csv'},
                timeout=PCPAO_DOWNLOAD_TIMEOUT,
            )

        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        archive = response.content

    if 'zip' not in content_type.lower():
        raise RuntimeError(
            f'Expected zip from PCPAO, got Content-Type={content_type!r}; the download endpoint may have changed again.'
        )

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
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


def csv_encoding(csv_path: str) -> str:
    """PCPAO exports are Windows-1252 unless they start with a UTF-8 BOM."""
    with open(csv_path, 'rb') as raw_file:
        has_utf8_bom = raw_file.read(len(codecs.BOM_UTF8)) == codecs.BOM_UTF8
    return 'utf-8-sig' if has_utf8_bom else 'cp1252'


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


def _quantized(value: str | None, places: int) -> Decimal | None:
    """Round to the model field's decimal places.

    PCPAO exports float artifacts ('19.919700000000002') and 9-place
    coordinates. Unrounded values never compare equal to what the database
    returns, so every row would be rewritten on every import.
    """
    number = safe_decimal(value or '')
    if number is None:
        return None
    return number.quantize(Decimal(1).scaleb(-places))


def _yn(value: str | None) -> bool | None:
    """PCPAO flags are 'Y'/'N' or 'Yes'/'No'; anything else is unknown."""
    flag = (value or '').strip().upper()
    if flag in ('Y', 'YES'):
        return True
    if flag in ('N', 'NO'):
        return False
    return None


def _text(value: str | None, placeholders: tuple[str, ...] = ()) -> str | None:
    s = (value or '').strip()
    if not s or s.upper() in placeholders:
        return None
    return s


def _neighborhood_code(value: str | None) -> str | None:
    """NBORHOOD_CD is NNNN.NN, but some rows carry float artifacts
    ('3000.2000000000003'); normalize so neighbors group together."""
    code = _quantized(value, 2)
    return str(code) if code is not None else None


def _evac_zone(value: str | None) -> str | None:
    zone = (value or '').strip().upper()
    if zone == 'NON EVAC':
        return 'NONE'
    return zone if zone in ('A', 'B', 'C', 'D', 'E') else None


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


def map_csv_row_to_property(
    row: dict[str, str],
    millage: dict[str, Millage] | None = None,
    permits: Mapping[str, tuple[int | None, int | None]] | None = None,
) -> dict[str, Any]:
    """Map a PCPAO RP_PROPERTY_INFO row to PropertyListing fields.

    With a district -> Millage lookup (see import_millage_rates), also
    precomputes the tax estimates. Without one, the estimate fields are left
    out so an upsert keeps whatever the database already has.

    The same goes for `permits`, a parcel -> (roof year, heating/air year)
    lookup (see permits_importer.read_permit_years): with one, a parcel
    missing from it has its permit years cleared.

    Schema reference:
      - PARCEL_NUMBER, SITE_ADDRESS, STR_CITY, STR_ZIP, OWNER1
      - CNTY_JST_VALUE (just/market value), CNTY_ASD_VALUE (assessed)
      - TOTAL_LIVING_SQFT, YEAR_BUILT, ACREAGE
      - PROPERTY_USE (e.g. '0110 Single Family Home')
      - TAX_AMOUNT_NO_EX (tax before exemptions, not the owner's bill)
      - Tax inputs: ROLL_YEAR, TAX_DISTRICT, MILLAGE_RATE, SPECIAL_ASSESSMENT, HX_CAP, SALES_COMP
      - Risk: LATITUDE/LONGITUDE, EVAC_ZONE, NBORHOOD_CD, FRONTAGE, VIEWS, WATERFRONT_YN,
        SEAWALL, SUBSIDENCE_YN, CONTAMINATION_YN, DLHL_YN, TOTAL_LIVING_UNITS

    Not imported: ELEVATION_CERT is 'N/A' on every row, and HX_SAVINGS is
    blank for ~97% of parcels. Beds/baths live in RP_BUILDING (not yet imported).
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

    result['roll_year'] = safe_int(row.get('ROLL_YEAR', ''))
    result['tax_district'] = _text(row.get('TAX_DISTRICT'))
    result['millage_rate'] = _quantized(row.get('MILLAGE_RATE'), 4)
    result['special_assessment'] = _quantized(row.get('SPECIAL_ASSESSMENT'), 2)
    result['homestead_cap'] = _yn(row.get('HX_CAP'))
    result['sales_comp_value'] = _quantized(row.get('SALES_COMP'), 2)

    result['latitude'] = _quantized(row.get('LATITUDE'), 6)
    result['longitude'] = _quantized(row.get('LONGITUDE'), 6)
    result['evac_zone'] = _evac_zone(row.get('EVAC_ZONE'))
    result['neighborhood_code'] = _neighborhood_code(row.get('NBORHOOD_CD'))
    result['frontage'] = _text(row.get('FRONTAGE'))
    result['views'] = _text(row.get('VIEWS'), placeholders=('NONE', 'DO NOT USE'))
    result['waterfront'] = _yn(row.get('WATERFRONT_YN'))
    result['seawall'] = _yn(row.get('SEAWALL'))
    result['subsidence'] = _yn(row.get('SUBSIDENCE_YN'))
    result['contamination'] = _yn(row.get('CONTAMINATION_YN'))
    result['historic_landmark'] = _yn(row.get('DLHL_YN'))
    result['living_units'] = safe_int(row.get('TOTAL_LIVING_UNITS', ''))

    if millage is not None:
        result.update(_tax_estimates(row, result, millage))

    if permits is not None:
        result['roof_permit_year'], result['hvac_permit_year'] = permits.get(result['parcel_id'], (None, None))

    return result


def _tax_estimates(row: dict[str, str], prop: dict[str, Any], millage: dict[str, Millage]) -> dict[str, int | None]:
    estimates: dict[str, int | None] = dict.fromkeys(('est_tax_current', 'est_tax_homestead', 'est_tax_no_homestead'))
    district = millage.get(prop['tax_district'] or '')
    just_value = prop['market_value']
    if district is None or just_value is None:
        return estimates

    special_assessment = prop['special_assessment']
    county_taxable = safe_decimal(row.get('CNTY_TAXABLE_VALUE', ''))
    school_taxable = safe_decimal(row.get('SCHL_TAXABLE_VALUE', ''))
    if county_taxable is not None and school_taxable is not None:
        estimates['est_tax_current'] = estimate_current_tax(
            county_taxable, school_taxable, district, special_assessment
        )

    estimates['est_tax_no_homestead'] = estimate_new_owner_tax(just_value, district, special_assessment)
    # Stays None for parcels nobody can homestead: commercial, or no dwelling.
    if row.get('PARCEL_TYPE') in HOMESTEAD_PARCEL_TYPES and (prop['building_sqft'] or 0) > 0:
        estimates['est_tax_homestead'] = estimate_new_owner_tax(
            just_value, district, special_assessment, homestead_rules(buyer_tax_year())
        )
    return estimates


def import_millage_rates(csv_path: str) -> dict[str, Millage]:
    """Replace TaxDistrictMillage with an RP_MILLAGE_RATES file.

    Each row is one taxing authority's rate in one district; levies whose
    TAX_AUTH_NAME mentions SCHOOL are summed separately. Returns the most
    recent year's millage per district.
    """
    sums: dict[tuple[str, int, str], list[Decimal]] = {}
    with open(csv_path, encoding=csv_encoding(csv_path), newline='') as f:
        for row in csv.DictReader(f):
            district = row['MILL_CD'].strip()
            description = row['TAX_RATE_DSCR'].strip()  # e.g. '2025 Final'
            year = safe_int(description[:4])
            rate = _quantized(row['TAX_RATE_DISPLAY'], 4)
            if not district or year is None or rate is None:
                continue
            total_and_school = sums.setdefault((district, year, description), [Decimal(0), Decimal(0)])
            total_and_school[0] += rate
            if 'SCHOOL' in row['TAX_AUTH_NAME'].upper():
                total_and_school[1] += rate

    # If a year has both proposed and final rates, keep the final ones.
    chosen: dict[tuple[str, int], tuple[str, list[Decimal]]] = {}
    for (district, year, description), total_and_school in sorted(sums.items()):
        current = chosen.get((district, year))
        if current is None or 'FINAL' in description.upper():
            chosen[(district, year)] = (description, total_and_school)

    rows = [
        TaxDistrictMillage(
            district_code=district,
            tax_year=year,
            rate_description=description,
            total_mills=total,
            school_mills=school,
        )
        for (district, year), (description, (total, school)) in chosen.items()
    ]
    with transaction.atomic():
        TaxDistrictMillage.objects.all().delete()
        TaxDistrictMillage.objects.bulk_create(rows)
    return stored_millage()


def stored_millage() -> dict[str, Millage]:
    """Most recent millage per district from the database."""
    latest: dict[str, Millage] = {}
    for row in TaxDistrictMillage.objects.order_by('district_code', 'tax_year'):
        latest[row.district_code] = Millage(total=row.total_mills, school=row.school_mills)
    return latest


def bulk_upsert_properties(properties: list[dict[str, Any]], batch_size: int = 1000) -> dict[str, int]:
    """
    Bulk insert or update property records.

    Uses batch operations to avoid N+1 query pattern:
    - Single query to find existing records
    - bulk_create for new records
    - one upsert per batch for existing records that changed

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
            'roll_year',
            'tax_district',
            'millage_rate',
            'special_assessment',
            'homestead_cap',
            'sales_comp_value',
            'latitude',
            'longitude',
            'evac_zone',
            'neighborhood_code',
            'frontage',
            'views',
            'waterfront',
            'seawall',
            'subsidence',
            'contamination',
            'historic_landmark',
            'living_units',
            'est_tax_current',
            'est_tax_homestead',
            'est_tax_no_homestead',
            'roof_permit_year',
            'hvac_permit_year',
        ]

        for prop in valid_properties:
            parcel_id = prop['parcel_id']
            existing = existing_records.get(parcel_id)

            if existing:
                # Avoid rewriting unchanged rows. PostgreSQL keeps the old row
                # version for every UPDATE; rewriting the full county dataset
                # each month can exhaust a size-limited database with dead rows.
                changed = False
                for field in update_fields:
                    if field in prop and getattr(existing, field) != prop[field]:
                        setattr(existing, field, prop[field])
                        changed = True
                if changed:
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

        # Changed rows go in as INSERT ... ON CONFLICT (parcel_id) DO UPDATE,
        # one statement per batch. bulk_update builds a CASE expression per
        # field per row, which made a backfill that touches every row about
        # 20x slower than a fresh load. Clearing the pk lets the insert half
        # take a throwaway id; the parcel_id conflict routes each row to the
        # update half, which keeps the existing id and every column outside
        # update_fields.
        if properties_to_update:
            for existing in properties_to_update:
                existing.pk = None
            PropertyListing.objects.bulk_create(
                properties_to_update,
                batch_size=batch_size,
                update_conflicts=True,
                unique_fields=['parcel_id'],
                update_fields=update_fields,
            )
            stats['updated'] = len(properties_to_update)

    return stats


def vacuum_property_listing_table() -> bool:
    """Make dead PostgreSQL row space reusable before a county refresh."""
    if connection.vendor != 'postgresql':
        return False

    table_name = connection.ops.quote_name(PropertyListing._meta.db_table)
    with connection.cursor() as cursor:
        # A parallel worker can require enough temporary index space to fail
        # when a size-limited Neon project is already near its ceiling.
        cursor.execute(f'VACUUM (ANALYZE, PARALLEL 0) {table_name}')
    return True
