# Parallel Task Breakdown for 3 Agents

> **Status:** Complete - All agent tasks merged and pushed.
> **Prerequisites:** Tasks 1-3 complete (test infrastructure, CSV mapping, download functionality)

---

## Agent 1: Importer Service (pcpao_importer.py)

**Focus:** Core data processing - bulk upsert and property type mapping

**Files to modify:**
- `apps/WebScraper/services/pcpao_importer.py`
- `apps/WebScraper/services/property_types.py` (create)

### Task 1A: Add Bulk Upsert Functionality

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

### Task 1B: Create Property Type Mapping

Create `apps/WebScraper/services/property_types.py`:

```python
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

### Task 1C: Update map_csv_row_to_property to use property types

Modify `apps/WebScraper/services/pcpao_importer.py`:

```python
# Add import at top
from apps.WebScraper.services.property_types import dor_code_to_description

# In map_csv_row_to_property function, change:
result['property_type'] = dor_code_to_description(row.get('DOR_UC', ''))
```

### Agent 1 Commit Sequence

```bash
git add apps/WebScraper/services/pcpao_importer.py
git commit -m "feat: add bulk upsert for property records"

git add apps/WebScraper/services/property_types.py apps/WebScraper/services/pcpao_importer.py
git commit -m "feat: add DOR use code to property type mapping"
```

---

## Agent 2: CLI & Scheduling (New Files Only)

**Focus:** Management command and Celery task

**Files to create:**
- `apps/WebScraper/management/__init__.py`
- `apps/WebScraper/management/commands/__init__.py`
- `apps/WebScraper/management/commands/import_pcpao_data.py`
- `apps/WebScraper/tasks/import_data.py`

### Task 2A: Create Management Command

Create directory structure:
```bash
mkdir -p apps/WebScraper/management/commands
touch apps/WebScraper/management/__init__.py
touch apps/WebScraper/management/commands/__init__.py
```

Create `apps/WebScraper/management/commands/import_pcpao_data.py`:

```python
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
            self._process_csv(csv_path, quiet, limit)
        else:
            if not quiet:
                self.stdout.write('Downloading RP_PROPERTY_INFO.csv...')
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)
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

### Task 2B: Create Celery Task

Create `apps/WebScraper/tasks/import_data.py`:

```python
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
import csv
from celery import shared_task
from apps.WebScraper.services.pcpao_importer import (
    download_pcpao_file,
    map_csv_row_to_property,
    bulk_upsert_properties,
)

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

### Agent 2 Commit Sequence

```bash
git add apps/WebScraper/management/
git commit -m "feat: add import_pcpao_data management command"

git add apps/WebScraper/tasks/import_data.py
git commit -m "feat: add Celery task for scheduled PCPAO data imports"
```

---

## Agent 3: Tests & Fixtures

**Focus:** All test code and sample data

**Files to create/modify:**
- `apps/WebScraper/tests/test_data_import.py` (modify - add new test classes)
- `apps/WebScraper/fixtures/sample_pcpao_data.csv` (create)

### Task 3A: Create Sample Fixture

Create `apps/WebScraper/fixtures/` directory and sample CSV:

```bash
mkdir -p apps/WebScraper/fixtures
```

Create `apps/WebScraper/fixtures/sample_pcpao_data.csv`:

```csv
PARCEL_ID,SITE_ADDR,SITE_CITY,SITE_ZIP,OWN_NAME,JV,AV,LIV_AREA,YR_BLT,BEDS,BATHS,DOR_UC,LAND_SQFT
14-31-15-00000-000-0001,123 MAIN ST,CLEARWATER,33755,SMITH JOHN,250000,225000,1500,1985,3,2,0100,7500
14-31-15-00000-000-0002,456 OAK AVE,ST PETERSBURG,33701,DOE JANE,320000,288000,1800,1992,4,2.5,0100,8200
14-31-15-00000-000-0003,789 BEACH DR,DUNEDIN,33528,JOHNSON MIKE,185000,166500,1200,1978,2,1,0100,6000
```

### Task 3B: Add Test Classes

Add to `apps/WebScraper/tests/test_data_import.py`:

```python
# Add these imports at the top
import django
from django.test import TestCase
from django.core.management import call_command
from apps.WebScraper.models import PropertyListing
from apps.WebScraper.services.pcpao_importer import bulk_upsert_properties
from apps.WebScraper.services.property_types import dor_code_to_description


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


class TestPropertyTypes:
    def test_single_family_code(self):
        assert dor_code_to_description('0100') == 'Single Family'

    def test_condo_code(self):
        assert dor_code_to_description('0400') == 'Condominium'

    def test_unknown_code(self):
        assert dor_code_to_description('9999') == 'Unknown (9999)'


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

### Agent 3 Commit Sequence

```bash
git add apps/WebScraper/fixtures/
git commit -m "test: add sample PCPAO CSV fixture"

git add apps/WebScraper/tests/test_data_import.py
git commit -m "test: add tests for bulk upsert, property types, and search"
```

---

## Coordination Instructions

### Before Starting

Each agent should:
1. Pull latest from main: `git pull origin main`
2. Create a feature branch: `git checkout -b <agent-branch-name>`
   - Agent 1: `git checkout -b feat/bulk-import-service`
   - Agent 2: `git checkout -b feat/import-cli-celery`
   - Agent 3: `git checkout -b feat/import-tests`

### Merge Order

**Merge Agent 1 first** (bulk_upsert_properties and property_types are dependencies)

```bash
git checkout main
git merge feat/bulk-import-service
```

**Then merge Agent 2** (management command depends on bulk_upsert)

```bash
git merge feat/import-cli-celery
```

**Finally merge Agent 3** (tests depend on all implementations)

```bash
git merge feat/import-tests
```

### Post-Merge: Documentation (Any Agent)

After all branches merged, update `CLAUDE.md`:

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

---

## Dependency Graph

```
Tasks 1-3 (DONE)
     │
     ├─────────────────────────────────────────┐
     │                                         │
Agent 1                                    Agent 2 (waits for Agent 1 merge)
├─ Task 1A: bulk_upsert_properties         ├─ Task 2A: management command
├─ Task 1B: property_types.py              └─ Task 2B: Celery task
└─ Task 1C: update map_csv_row
     │                                         │
     └─────────────────────────────────────────┤
                                               │
                                           Agent 3 (waits for both)
                                           ├─ Task 3A: sample fixture
                                           └─ Task 3B: test classes
                                               │
                                               ▼
                                        Final merge & docs
```
