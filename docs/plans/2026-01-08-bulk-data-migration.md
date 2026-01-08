# Bulk Data Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Selenium-based scraping with PCPAO bulk CSV data imports for instant searches and simplified architecture.

**Architecture:** Download CSV files from PCPAO's public data portal, process with Pandas, and bulk upsert into SQLite. Searches become instant database queries. Tax data handled on-demand via lightweight HTTP requests (not Selenium).

**Tech Stack:** Django management commands, Pandas, requests, existing PropertyListing model

---

## Task 1: Create Test Infrastructure

**Files:**
- Create: `apps/WebScraper/tests/__init__.py`
- Create: `apps/WebScraper/tests/test_data_import.py`

**Step 1: Create tests directory**

```bash
mkdir -p apps/WebScraper/tests
touch apps/WebScraper/tests/__init__.py
```

**Step 2: Write initial test file with test for CSV field mapping**

```python
# apps/WebScraper/tests/test_data_import.py
import pytest
from decimal import Decimal
from apps.WebScraper.services.pcpao_importer import map_csv_row_to_property


class TestCSVFieldMapping:
    def test_map_csv_row_extracts_parcel_id(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': 'SMITH JOHN',
            'JV': '250000',
            'AV': '225000',
            'LIV_AREA': '1500',
            'YR_BLT': '1985',
            'BEDS': '3',
            'BATHS': '2',
            'DOR_UC': '0100',
            'LAND_SQFT': '7500',
        }
        result = map_csv_row_to_property(row)
        assert result['parcel_id'] == '14-31-15-00000-000-0001'

    def test_map_csv_row_extracts_address_fields(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': 'SMITH JOHN',
            'JV': '250000',
            'AV': '225000',
            'LIV_AREA': '1500',
            'YR_BLT': '1985',
            'BEDS': '3',
            'BATHS': '2',
            'DOR_UC': '0100',
            'LAND_SQFT': '7500',
        }
        result = map_csv_row_to_property(row)
        assert result['address'] == '123 MAIN ST'
        assert result['city'] == 'CLEARWATER'
        assert result['zip_code'] == '33755'

    def test_map_csv_row_extracts_valuation(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': 'SMITH JOHN',
            'JV': '250000',
            'AV': '225000',
            'LIV_AREA': '1500',
            'YR_BLT': '1985',
            'BEDS': '3',
            'BATHS': '2',
            'DOR_UC': '0100',
            'LAND_SQFT': '7500',
        }
        result = map_csv_row_to_property(row)
        assert result['market_value'] == Decimal('250000')
        assert result['assessed_value'] == Decimal('225000')

    def test_map_csv_row_handles_empty_values(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': '',
            'JV': '',
            'AV': '',
            'LIV_AREA': '',
            'YR_BLT': '',
            'BEDS': '',
            'BATHS': '',
            'DOR_UC': '0100',
            'LAND_SQFT': '',
        }
        result = map_csv_row_to_property(row)
        assert result['owner_name'] is None
        assert result['market_value'] is None
        assert result['building_sqft'] is None
```

**Step 3: Run test to verify it fails**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'apps.WebScraper.services'"

**Step 4: Commit test infrastructure**

```bash
git add apps/WebScraper/tests/
git commit -m "test: add test infrastructure for bulk data import"
```

---

## Task 2: Implement CSV Field Mapping

**Files:**
- Create: `apps/WebScraper/services/__init__.py`
- Create: `apps/WebScraper/services/pcpao_importer.py`

**Step 1: Create services directory**

```bash
mkdir -p apps/WebScraper/services
touch apps/WebScraper/services/__init__.py
```

**Step 2: Write minimal implementation for field mapping**

```python
# apps/WebScraper/services/pcpao_importer.py
"""
PCPAO Bulk Data Importer

Imports property data from PCPAO CSV downloads.
Data source: https://www.pcpao.gov/tools-data/data-downloads/raw-database-files
"""
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional


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
```

**Step 3: Run tests to verify they pass**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py -v
```

Expected: All 4 tests PASS

**Step 4: Commit implementation**

```bash
git add apps/WebScraper/services/
git commit -m "feat: add CSV field mapping for PCPAO bulk import"
```

---

## Task 3: Add CSV Download Functionality

**Files:**
- Modify: `apps/WebScraper/tests/test_data_import.py`
- Modify: `apps/WebScraper/services/pcpao_importer.py`

**Step 1: Add test for download function**

Add to `apps/WebScraper/tests/test_data_import.py`:

```python
import tempfile
import os
from unittest.mock import patch, MagicMock
from apps.WebScraper.services.pcpao_importer import download_pcpao_file, PCPAO_DATA_URL


class TestCSVDownload:
    def test_download_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_response = MagicMock()
            mock_response.iter_content = lambda chunk_size: [b'PARCEL_ID,SITE_ADDR\n', b'123,Main St\n']
            mock_response.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_response) as mock_get:
                mock_get.return_value.__enter__ = lambda s: mock_response
                mock_get.return_value.__exit__ = MagicMock(return_value=False)

                filepath = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)

                assert os.path.exists(filepath)
                assert filepath.endswith('.csv')

    def test_download_uses_correct_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_response = MagicMock()
            mock_response.iter_content = lambda chunk_size: [b'data']
            mock_response.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_response) as mock_get:
                mock_get.return_value.__enter__ = lambda s: mock_response
                mock_get.return_value.__exit__ = MagicMock(return_value=False)

                download_pcpao_file('RP_PROPERTY_INFO', tmpdir)

                call_url = mock_get.call_args[0][0]
                assert 'RP_PROPERTY_INFO' in call_url
```

**Step 2: Run test to verify it fails**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py::TestCSVDownload -v
```

Expected: FAIL with "cannot import name 'download_pcpao_file'"

**Step 3: Implement download function**

Add to `apps/WebScraper/services/pcpao_importer.py`:

```python
import os
import requests
import logging

logger = logging.getLogger(__name__)

# PCPAO data download URL pattern
PCPAO_DATA_URL = "https://www.pcpao.gov/Data/Downloads/{filename}.csv"


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
```

**Step 4: Run tests to verify they pass**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/WebScraper/tests/test_data_import.py apps/WebScraper/services/pcpao_importer.py
git commit -m "feat: add PCPAO CSV download functionality"
```

---

## Task 4: Add Bulk Upsert Functionality

**Files:**
- Modify: `apps/WebScraper/tests/test_data_import.py`
- Modify: `apps/WebScraper/services/pcpao_importer.py`

**Step 1: Add test for bulk upsert**

Add to `apps/WebScraper/tests/test_data_import.py`:

```python
import django
from django.test import TestCase
from apps.WebScraper.models import PropertyListing
from apps.WebScraper.services.pcpao_importer import bulk_upsert_properties


class TestBulkUpsert(TestCase):
    def test_bulk_upsert_creates_new_records(self):
        properties = [
            {
                'parcel_id': '14-31-15-00000-000-0001',
                'address': '123 MAIN ST',
                'city': 'CLEARWATER',
                'zip_code': '33755',
                'property_type': '0100',
            },
            {
                'parcel_id': '14-31-15-00000-000-0002',
                'address': '456 OAK AVE',
                'city': 'ST PETERSBURG',
                'zip_code': '33701',
                'property_type': '0100',
            },
        ]

        stats = bulk_upsert_properties(properties)

        assert stats['created'] == 2
        assert stats['updated'] == 0
        assert PropertyListing.objects.count() == 2

    def test_bulk_upsert_updates_existing_records(self):
        PropertyListing.objects.create(
            parcel_id='14-31-15-00000-000-0001',
            address='OLD ADDRESS',
            city='CLEARWATER',
            zip_code='33755',
            property_type='0100',
        )

        properties = [
            {
                'parcel_id': '14-31-15-00000-000-0001',
                'address': 'NEW ADDRESS',
                'city': 'CLEARWATER',
                'zip_code': '33755',
                'property_type': '0100',
            },
        ]

        stats = bulk_upsert_properties(properties)

        assert stats['created'] == 0
        assert stats['updated'] == 1

        listing = PropertyListing.objects.get(parcel_id='14-31-15-00000-000-0001')
        assert listing.address == 'NEW ADDRESS'
```

**Step 2: Run test to verify it fails**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py::TestBulkUpsert -v
```

Expected: FAIL with "cannot import name 'bulk_upsert_properties'"

**Step 3: Implement bulk upsert**

Add to `apps/WebScraper/services/pcpao_importer.py`:

```python
from typing import List
from django.db import transaction
from apps.WebScraper.models import PropertyListing


def bulk_upsert_properties(properties: List[Dict[str, Any]], batch_size: int = 1000) -> Dict[str, int]:
    """
    Bulk insert or update property records.

    Args:
        properties: List of property dictionaries with PropertyListing fields
        batch_size: Number of records to process per batch

    Returns:
        Dictionary with 'created' and 'updated' counts
    """
    stats = {'created': 0, 'updated': 0}

    with transaction.atomic():
        for prop in properties:
            parcel_id = prop.get('parcel_id')
            if not parcel_id:
                continue

            obj, created = PropertyListing.objects.update_or_create(
                parcel_id=parcel_id,
                defaults={k: v for k, v in prop.items() if k != 'parcel_id'}
            )

            if created:
                stats['created'] += 1
            else:
                stats['updated'] += 1

    return stats
```

**Step 4: Run tests to verify they pass**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py::TestBulkUpsert -v --ds=home_finder.settings
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/WebScraper/tests/test_data_import.py apps/WebScraper/services/pcpao_importer.py
git commit -m "feat: add bulk upsert for property records"
```

---

## Task 5: Create Management Command

**Files:**
- Create: `apps/WebScraper/management/__init__.py`
- Create: `apps/WebScraper/management/commands/__init__.py`
- Create: `apps/WebScraper/management/commands/import_pcpao_data.py`

**Step 1: Create directory structure**

```bash
mkdir -p apps/WebScraper/management/commands
touch apps/WebScraper/management/__init__.py
touch apps/WebScraper/management/commands/__init__.py
```

**Step 2: Write management command**

```python
# apps/WebScraper/management/commands/import_pcpao_data.py
"""
Import PCPAO bulk data into the database.

Usage:
    python manage.py import_pcpao_data
    python manage.py import_pcpao_data --file /path/to/RP_PROPERTY_INFO.csv
    python manage.py import_pcpao_data --quiet
"""
import os
import csv
import tempfile
import logging
from django.core.management.base import BaseCommand
from apps.WebScraper.services.pcpao_importer import (
    download_pcpao_file,
    map_csv_row_to_property,
    bulk_upsert_properties,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import property data from PCPAO bulk CSV files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Path to local CSV file (skips download)',
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress progress output',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of records to import (for testing)',
        )

    def handle(self, *args, **options):
        quiet = options['quiet']
        limit = options.get('limit')

        if not quiet:
            self.stdout.write('Starting PCPAO data import...')

        # Get CSV file path
        if options['file']:
            csv_path = options['file']
            if not os.path.exists(csv_path):
                self.stderr.write(f'File not found: {csv_path}')
                return
        else:
            if not quiet:
                self.stdout.write('Downloading RP_PROPERTY_INFO.csv...')
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)
                self._process_csv(csv_path, quiet, limit)
                return

        self._process_csv(csv_path, quiet, limit)

    def _process_csv(self, csv_path: str, quiet: bool, limit: int = None):
        """Process CSV file and import records."""
        properties = []
        count = 0

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                prop = map_csv_row_to_property(row)
                if prop.get('parcel_id'):
                    properties.append(prop)
                    count += 1

                    if limit and count >= limit:
                        break

                    # Process in batches of 5000
                    if len(properties) >= 5000:
                        stats = bulk_upsert_properties(properties)
                        if not quiet:
                            self.stdout.write(
                                f'Processed {count} records '
                                f'(created: {stats["created"]}, updated: {stats["updated"]})'
                            )
                        properties = []

        # Process remaining records
        if properties:
            stats = bulk_upsert_properties(properties)
            if not quiet:
                self.stdout.write(
                    f'Processed {count} records '
                    f'(created: {stats["created"]}, updated: {stats["updated"]})'
                )

        if not quiet:
            self.stdout.write(self.style.SUCCESS(f'Import complete. Total records: {count}'))
```

**Step 3: Test the command manually**

```bash
source venv/Scripts/activate && python manage.py import_pcpao_data --help
```

Expected: Help text displayed

**Step 4: Commit**

```bash
git add apps/WebScraper/management/
git commit -m "feat: add import_pcpao_data management command"
```

---

## Task 6: Add Sample Data for Testing

**Files:**
- Create: `apps/WebScraper/fixtures/sample_pcpao_data.csv`
- Modify: `apps/WebScraper/tests/test_data_import.py`

**Step 1: Create sample CSV file**

```csv
PARCEL_ID,SITE_ADDR,SITE_CITY,SITE_ZIP,OWN_NAME,JV,AV,LIV_AREA,YR_BLT,BEDS,BATHS,DOR_UC,LAND_SQFT
14-31-15-00000-000-0001,123 MAIN ST,CLEARWATER,33755,SMITH JOHN,250000,225000,1500,1985,3,2,0100,7500
14-31-15-00000-000-0002,456 OAK AVE,ST PETERSBURG,33701,DOE JANE,320000,288000,1800,1992,4,2.5,0100,8200
14-31-15-00000-000-0003,789 BEACH DR,DUNEDIN,33528,JOHNSON MIKE,185000,166500,1200,1978,2,1,0100,6000
```

**Step 2: Add integration test**

Add to `apps/WebScraper/tests/test_data_import.py`:

```python
import os
from django.core.management import call_command


class TestImportCommand(TestCase):
    def test_import_from_local_file(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__),
            '../fixtures/sample_pcpao_data.csv'
        )

        call_command('import_pcpao_data', file=fixture_path, quiet=True)

        assert PropertyListing.objects.count() == 3

        clearwater = PropertyListing.objects.get(parcel_id='14-31-15-00000-000-0001')
        assert clearwater.city == 'CLEARWATER'
        assert clearwater.market_value == Decimal('250000')

    def test_import_with_limit(self):
        fixture_path = os.path.join(
            os.path.dirname(__file__),
            '../fixtures/sample_pcpao_data.csv'
        )

        call_command('import_pcpao_data', file=fixture_path, quiet=True, limit=2)

        assert PropertyListing.objects.count() == 2
```

**Step 3: Create fixtures directory and CSV**

```bash
mkdir -p apps/WebScraper/fixtures
```

**Step 4: Run tests**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py::TestImportCommand -v --ds=home_finder.settings
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/WebScraper/fixtures/ apps/WebScraper/tests/test_data_import.py
git commit -m "test: add sample data and integration tests for import command"
```

---

## Task 7: Update Property Type Mapping

**Files:**
- Create: `apps/WebScraper/services/property_types.py`
- Modify: `apps/WebScraper/services/pcpao_importer.py`
- Modify: `apps/WebScraper/tests/test_data_import.py`

**Step 1: Add test for property type conversion**

Add to `apps/WebScraper/tests/test_data_import.py`:

```python
from apps.WebScraper.services.property_types import dor_code_to_description


class TestPropertyTypes:
    def test_single_family_code(self):
        assert dor_code_to_description('0100') == 'Single Family'

    def test_condo_code(self):
        assert dor_code_to_description('0400') == 'Condominium'

    def test_unknown_code(self):
        assert dor_code_to_description('9999') == 'Unknown (9999)'
```

**Step 2: Run test to verify it fails**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py::TestPropertyTypes -v
```

Expected: FAIL with "cannot import name 'dor_code_to_description'"

**Step 3: Implement property type mapping**

```python
# apps/WebScraper/services/property_types.py
"""
Florida Department of Revenue (DOR) Use Codes to human-readable descriptions.

Reference: https://floridarevenue.com/property/Documents/pt_dr405.pdf
"""

DOR_USE_CODES = {
    '0000': 'Vacant Residential',
    '0100': 'Single Family',
    '0200': 'Mobile Home',
    '0300': 'Multi-Family (2-9 units)',
    '0400': 'Condominium',
    '0500': 'Cooperatives',
    '0600': 'Retirement Homes',
    '0700': 'Miscellaneous Residential',
    '0800': 'Multi-Family (10+ units)',
    '0900': 'Residential Common Elements',
    '1000': 'Vacant Commercial',
    '1100': 'Stores, One Story',
    '1200': 'Mixed Use (Store/Office/Residential)',
    '1300': 'Department Stores',
    '1400': 'Supermarkets',
    '1500': 'Regional Shopping Centers',
    '1600': 'Community Shopping Centers',
    '1700': 'Office Buildings (1-4 stories)',
    '1800': 'Office Buildings (5+ stories)',
    '1900': 'Professional Service Buildings',
    '2000': 'Airports, Marinas, Bus Terminals',
    '2100': 'Restaurants, Cafeterias',
    '2200': 'Drive-In Restaurants',
    '2300': 'Financial Institutions',
    '2400': 'Insurance Company Offices',
    '2500': 'Repair Service Shops',
    '2600': 'Service Stations',
    '2700': 'Auto Sales, Repair, Storage',
    '2800': 'Parking Lots',
    '2900': 'Wholesale Outlets',
    '3000': 'Florist, Greenhouse',
    '3100': 'Drive-In Theater',
    '3200': 'Enclosed Theater',
    '3300': 'Nightclubs, Bars',
    '3400': 'Bowling Alleys',
    '3500': 'Tourist Attractions',
    '3600': 'Camps',
    '3700': 'Race Tracks',
    '3800': 'Golf Courses',
    '3900': 'Hotels, Motels',
    '4000': 'Vacant Industrial',
    '4100': 'Light Manufacturing',
    '4200': 'Heavy Manufacturing',
    '4300': 'Lumber Yards',
    '4400': 'Packing Plants',
    '4500': 'Canneries',
    '4600': 'Other Food Processing',
    '4700': 'Mineral Processing',
    '4800': 'Warehousing',
    '4900': 'Open Storage',
}


def dor_code_to_description(code: str) -> str:
    """Convert DOR use code to human-readable description."""
    code = code.strip() if code else ''
    return DOR_USE_CODES.get(code, f'Unknown ({code})')
```

**Step 4: Update importer to use property type mapping**

Modify `map_csv_row_to_property` in `pcpao_importer.py`:

```python
from apps.WebScraper.services.property_types import dor_code_to_description

# In map_csv_row_to_property function, change:
result['property_type'] = dor_code_to_description(row.get('DOR_UC', ''))
```

**Step 5: Run tests**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py -v --ds=home_finder.settings
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add apps/WebScraper/services/property_types.py apps/WebScraper/services/pcpao_importer.py apps/WebScraper/tests/test_data_import.py
git commit -m "feat: add DOR use code to property type mapping"
```

---

## Task 8: Add Data Import Scheduling (Optional Celery)

**Files:**
- Create: `apps/WebScraper/tasks/import_data.py`

**Step 1: Create Celery task for scheduled imports**

```python
# apps/WebScraper/tasks/import_data.py
"""
Celery tasks for scheduled data imports.

Usage:
    # Run manually
    from apps.WebScraper.tasks.import_data import import_pcpao_data_task
    import_pcpao_data_task.delay()

    # Schedule in Celery Beat (celeryconfig.py):
    # CELERYBEAT_SCHEDULE = {
    #     'import-pcpao-daily': {
    #         'task': 'apps.WebScraper.tasks.import_data.import_pcpao_data_task',
    #         'schedule': crontab(hour=2, minute=0),
    #     },
    # }
"""
import tempfile
import logging
from celery import shared_task
from apps.WebScraper.services.pcpao_importer import (
    download_pcpao_file,
    map_csv_row_to_property,
    bulk_upsert_properties,
)
import csv

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def import_pcpao_data_task(self):
    """
    Download and import PCPAO data.

    This task can be scheduled to run daily via Celery Beat.
    """
    logger.info('Starting scheduled PCPAO data import')

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)

        properties = []
        total_created = 0
        total_updated = 0
        count = 0

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                prop = map_csv_row_to_property(row)
                if prop.get('parcel_id'):
                    properties.append(prop)
                    count += 1

                    if len(properties) >= 5000:
                        stats = bulk_upsert_properties(properties)
                        total_created += stats['created']
                        total_updated += stats['updated']
                        properties = []

                        # Update task progress
                        self.update_state(
                            state='PROGRESS',
                            meta={'current': count, 'created': total_created, 'updated': total_updated}
                        )

        if properties:
            stats = bulk_upsert_properties(properties)
            total_created += stats['created']
            total_updated += stats['updated']

    logger.info(f'Import complete: {count} records ({total_created} created, {total_updated} updated)')

    return {
        'total': count,
        'created': total_created,
        'updated': total_updated,
    }
```

**Step 2: Test task runs without error**

```bash
source venv/Scripts/activate && python -c "from apps.WebScraper.tasks.import_data import import_pcpao_data_task; print('Task loaded successfully')"
```

**Step 3: Commit**

```bash
git add apps/WebScraper/tasks/import_data.py
git commit -m "feat: add Celery task for scheduled PCPAO data imports"
```

---

## Task 9: Update Search Views to Use Database

**Files:**
- Modify: `apps/WebScraper/views.py`
- Modify: `apps/WebScraper/tests/test_data_import.py`

**Step 1: Add test for database search**

Add to `apps/WebScraper/tests/test_data_import.py`:

```python
from django.test import Client
from django.urls import reverse


class TestPropertySearch(TestCase):
    def setUp(self):
        PropertyListing.objects.create(
            parcel_id='14-31-15-00000-000-0001',
            address='123 MAIN ST',
            city='CLEARWATER',
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal('250000'),
        )
        PropertyListing.objects.create(
            parcel_id='14-31-15-00000-000-0002',
            address='456 OAK AVE',
            city='ST PETERSBURG',
            zip_code='33701',
            property_type='Single Family',
            market_value=Decimal('320000'),
        )

    def test_search_by_city(self):
        results = PropertyListing.objects.filter(city__icontains='clearwater')
        assert results.count() == 1
        assert results.first().address == '123 MAIN ST'

    def test_search_by_price_range(self):
        results = PropertyListing.objects.filter(
            market_value__gte=200000,
            market_value__lte=300000
        )
        assert results.count() == 1
```

**Step 2: Run test**

```bash
source venv/Scripts/activate && python -m pytest apps/WebScraper/tests/test_data_import.py::TestPropertySearch -v --ds=home_finder.settings
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add apps/WebScraper/tests/test_data_import.py
git commit -m "test: add property search tests using database"
```

---

## Task 10: Clean Up and Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/plans/2026-01-08-architecture-alternatives.md`

**Step 1: Update CLAUDE.md with new commands**

Add to the Development Commands section:

```markdown
### Data Import
```bash
# Import PCPAO bulk data (downloads from county website)
python3 manage.py import_pcpao_data

# Import from local CSV file
python3 manage.py import_pcpao_data --file /path/to/RP_PROPERTY_INFO.csv

# Import with limit (for testing)
python3 manage.py import_pcpao_data --limit 1000

# Quiet mode (for cron jobs)
python3 manage.py import_pcpao_data --quiet
```
```

**Step 2: Mark architecture document as implemented**

Add to the top of `2026-01-08-architecture-alternatives.md`:

```markdown
> **Status:** Implemented - see `apps/WebScraper/services/pcpao_importer.py` and `manage.py import_pcpao_data`
```

**Step 3: Commit**

```bash
git add CLAUDE.md docs/plans/2026-01-08-architecture-alternatives.md
git commit -m "docs: update documentation with bulk data import commands"
```

---

## Summary

This plan migrates from Selenium scraping to bulk CSV imports:

| Component | Before | After |
|-----------|--------|-------|
| Data source | Selenium scraping | PCPAO CSV downloads |
| Search speed | 30-60 seconds | < 1 second |
| Dependencies | Chrome, ChromeDriver, Selenium | requests, Pandas |
| Data freshness | On-demand | Daily (scheduled import) |
| Coverage | Limited by search | All 400k parcels |

**Files created:**
- `apps/WebScraper/services/pcpao_importer.py` - Core import logic
- `apps/WebScraper/services/property_types.py` - DOR code mapping
- `apps/WebScraper/management/commands/import_pcpao_data.py` - CLI command
- `apps/WebScraper/tasks/import_data.py` - Celery task (optional)
- `apps/WebScraper/tests/test_data_import.py` - Test suite
- `apps/WebScraper/fixtures/sample_pcpao_data.csv` - Test data

**Selenium scrapers preserved** (can be deprecated later):
- `apps/WebScraper/tasks/pcpao_scraper.py`
- `apps/WebScraper/tasks/tax_collector_scraper.py`
