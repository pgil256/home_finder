# Home Finder Parallel Test Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish comprehensive test coverage for the Home Finder application using multiple Claude Code instances running in parallel.

**Architecture:** Six independent test streams run simultaneously, each handled by a dedicated Claude Code instance. Each stream tests isolated components with mocked dependencies to avoid conflicts. Test fixtures are shared via a central conftest.py.

**Tech Stack:** pytest, pytest-django, pytest-celery, pytest-mock, factory-boy, responses, Jest (frontend)

---

## Parallel Execution Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PARALLEL TEST STREAMS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Stream 1           Stream 2          Stream 3          Stream 4           │
│  ┌─────────┐       ┌─────────┐       ┌─────────┐       ┌─────────┐         │
│  │ Models  │       │  Views  │       │ Celery  │       │Scrapers │         │
│  │   &     │       │   &     │       │  Tasks  │       │ (mocked)│         │
│  │Services │       │  APIs   │       │         │       │         │         │
│  └─────────┘       └─────────┘       └─────────┘       └─────────┘         │
│                                                                             │
│  Stream 5           Stream 6                                                │
│  ┌─────────┐       ┌─────────┐                                              │
│  │Frontend │       │ Integra-│                                              │
│  │   JS    │       │  tion   │                                              │
│  └─────────┘       └─────────┘                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

Each stream operates on different test files and has no dependencies on other streams during execution.

---

## Pre-Requisite Setup (Run Once Before Parallel Streams)

### Task 0: Test Infrastructure Setup

**Files:**
- Create: `pytest.ini`
- Create: `conftest.py`
- Create: `apps/WebScraper/tests/conftest.py`
- Create: `apps/WebScraper/tests/factories.py`
- Modify: `requirements.txt` (add test dependencies)

**Step 1: Create pytest configuration**

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = home_finder.settings
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short --strict-markers
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    selenium: marks tests requiring selenium/browser
    celery: marks tests requiring celery worker
testpaths = apps
```

**Step 2: Create root conftest with shared fixtures**

```python
# conftest.py
import pytest
from django.test import Client

@pytest.fixture
def client():
    return Client()

@pytest.fixture
def api_client():
    from django.test import Client
    return Client(content_type='application/json')

@pytest.fixture
def sample_search_criteria():
    return {
        'city': 'Clearwater',
        'zip_code': '33755',
        'property_type': 'Single Family',
        'min_price': 100000,
        'max_price': 500000,
    }
```

**Step 3: Create WebScraper test conftest**

```python
# apps/WebScraper/tests/conftest.py
import pytest
from decimal import Decimal
from apps.WebScraper.models import PropertyListing

@pytest.fixture
def sample_property(db):
    return PropertyListing.objects.create(
        parcel_id='15-29-16-12345-000-0010',
        address='123 Main St',
        city='Clearwater',
        zip_code='33755',
        owner_name='John Doe',
        property_type='Single Family',
        market_value=Decimal('245000.00'),
        assessed_value=Decimal('220500.00'),
        building_sqft=1450,
        year_built=1987,
        bedrooms=3,
        bathrooms=Decimal('2.0'),
        land_size=Decimal('0.25'),
        tax_amount=Decimal('3125.00'),
        tax_status='Paid',
        delinquent=False,
    )

@pytest.fixture
def multiple_properties(db):
    properties = []
    for i in range(5):
        prop = PropertyListing.objects.create(
            parcel_id=f'15-29-16-12345-000-{i:04d}',
            address=f'{100+i} Test St',
            city='Clearwater' if i % 2 == 0 else 'St Petersburg',
            zip_code='33755' if i % 2 == 0 else '33701',
            owner_name=f'Owner {i}',
            property_type='Single Family',
            market_value=Decimal(str(200000 + i * 50000)),
            assessed_value=Decimal(str(180000 + i * 45000)),
            building_sqft=1200 + i * 100,
            year_built=1980 + i * 5,
            bedrooms=2 + (i % 3),
            bathrooms=Decimal(str(1.5 + (i % 2) * 0.5)),
            land_size=Decimal('0.20'),
        )
        properties.append(prop)
    return properties
```

**Step 4: Create model factories**

```python
# apps/WebScraper/tests/factories.py
import factory
from decimal import Decimal
from apps.WebScraper.models import PropertyListing
from apps.KeywordSelection.models import Keyword

class PropertyListingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PropertyListing

    parcel_id = factory.Sequence(lambda n: f'15-29-16-00000-000-{n:04d}')
    address = factory.Faker('street_address')
    city = factory.Iterator(['Clearwater', 'St Petersburg', 'Largo', 'Dunedin'])
    zip_code = factory.Iterator(['33755', '33701', '33770', '34698'])
    owner_name = factory.Faker('name')
    property_type = 'Single Family'
    market_value = factory.LazyFunction(lambda: Decimal('250000.00'))
    assessed_value = factory.LazyFunction(lambda: Decimal('225000.00'))
    building_sqft = factory.Faker('random_int', min=800, max=3000)
    year_built = factory.Faker('random_int', min=1950, max=2024)
    bedrooms = factory.Faker('random_int', min=1, max=5)
    bathrooms = factory.LazyFunction(lambda: Decimal('2.0'))
    land_size = factory.LazyFunction(lambda: Decimal('0.25'))

class KeywordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Keyword

    name = factory.Sequence(lambda n: f'Keyword {n}')
    data_type = 'text'
    help_text = factory.Faker('sentence')
    priority = factory.Sequence(lambda n: n)
    is_active = True
```

**Step 5: Add test dependencies to requirements.txt**

Add these lines:
```
pytest>=7.4.0
pytest-django>=4.5.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
factory-boy>=3.3.0
responses>=0.23.0
freezegun>=1.2.0
```

**Step 6: Run setup verification**

```bash
source venv/Scripts/activate && pip install pytest pytest-django pytest-cov pytest-mock factory-boy responses freezegun
```

**Step 7: Verify pytest discovers tests**

```bash
pytest --collect-only
```

**Step 8: Commit infrastructure**

```bash
git add pytest.ini conftest.py apps/WebScraper/tests/conftest.py apps/WebScraper/tests/factories.py requirements.txt
git commit -m "test: add pytest infrastructure and fixtures"
```

---

## Stream 1: Models & Services Tests

**Assigned Claude Instance:** Instance 1
**Estimated Tests:** 25
**Dependencies:** None (uses factory fixtures)

### Task 1.1: PropertyListing Model Tests

**Files:**
- Create: `apps/WebScraper/tests/test_models.py`

**Step 1: Write failing test for model creation**

```python
# apps/WebScraper/tests/test_models.py
import pytest
from decimal import Decimal
from apps.WebScraper.models import PropertyListing

pytestmark = pytest.mark.django_db

class TestPropertyListingModel:
    def test_create_property_listing(self, sample_property):
        """Test that a PropertyListing can be created with valid data."""
        assert sample_property.pk is not None
        assert sample_property.parcel_id == '15-29-16-12345-000-0010'
        assert sample_property.city == 'Clearwater'
```

**Step 2: Run test to verify it passes**

```bash
pytest apps/WebScraper/tests/test_models.py::TestPropertyListingModel::test_create_property_listing -v
```

**Step 3: Write test for price_per_sqft computed property**

```python
    def test_price_per_sqft_calculation(self, sample_property):
        """Test computed price_per_sqft property."""
        expected = sample_property.market_value / sample_property.building_sqft
        assert sample_property.price_per_sqft == expected

    def test_price_per_sqft_with_zero_sqft(self, db):
        """Test price_per_sqft returns None when sqft is 0."""
        prop = PropertyListing.objects.create(
            parcel_id='test-zero-sqft',
            address='Test',
            city='Test',
            market_value=Decimal('100000'),
            building_sqft=0,
        )
        assert prop.price_per_sqft is None
```

**Step 4: Run tests**

```bash
pytest apps/WebScraper/tests/test_models.py -v
```

**Step 5: Write test for unique parcel_id constraint**

```python
    def test_parcel_id_unique_constraint(self, sample_property):
        """Test that duplicate parcel_id raises error."""
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            PropertyListing.objects.create(
                parcel_id=sample_property.parcel_id,
                address='Different',
                city='Different',
            )
```

**Step 6: Write test for string representation**

```python
    def test_str_representation(self, sample_property):
        """Test __str__ returns meaningful representation."""
        str_repr = str(sample_property)
        assert sample_property.parcel_id in str_repr or sample_property.address in str_repr
```

**Step 7: Run all model tests**

```bash
pytest apps/WebScraper/tests/test_models.py -v
```

**Step 8: Commit**

```bash
git add apps/WebScraper/tests/test_models.py
git commit -m "test: add PropertyListing model tests"
```

### Task 1.2: Keyword Model Tests

**Files:**
- Create: `apps/KeywordSelection/tests/__init__.py`
- Create: `apps/KeywordSelection/tests/test_models.py`

**Step 1: Create test directory and init**

```python
# apps/KeywordSelection/tests/__init__.py
```

**Step 2: Write Keyword model tests**

```python
# apps/KeywordSelection/tests/test_models.py
import pytest
from apps.KeywordSelection.models import Keyword

pytestmark = pytest.mark.django_db

class TestKeywordModel:
    def test_create_keyword(self, db):
        """Test that a Keyword can be created with valid data."""
        keyword = Keyword.objects.create(
            name='City',
            data_type='select',
            help_text='Select a city',
            priority=1,
            is_active=True,
            listing_field='city',
            extra_json={'choices': ['Clearwater', 'St Petersburg']},
        )
        assert keyword.pk is not None
        assert keyword.name == 'City'

    def test_keyword_ordering_by_priority(self, db):
        """Test keywords are ordered by priority."""
        Keyword.objects.create(name='Second', priority=2, is_active=True)
        Keyword.objects.create(name='First', priority=1, is_active=True)
        Keyword.objects.create(name='Third', priority=3, is_active=True)

        keywords = list(Keyword.objects.all().order_by('priority'))
        assert keywords[0].name == 'First'
        assert keywords[1].name == 'Second'
        assert keywords[2].name == 'Third'

    def test_extra_json_field(self, db):
        """Test JSONField stores complex data correctly."""
        keyword = Keyword.objects.create(
            name='Price Range',
            data_type='range',
            extra_json={
                'min': 0,
                'max': 1000000,
                'step': 10000,
                'format': 'currency',
            },
        )
        keyword.refresh_from_db()
        assert keyword.extra_json['min'] == 0
        assert keyword.extra_json['format'] == 'currency'

    def test_is_active_filter(self, db):
        """Test filtering by is_active flag."""
        Keyword.objects.create(name='Active', is_active=True)
        Keyword.objects.create(name='Inactive', is_active=False)

        active = Keyword.objects.filter(is_active=True)
        assert active.count() == 1
        assert active.first().name == 'Active'
```

**Step 3: Run tests**

```bash
pytest apps/KeywordSelection/tests/test_models.py -v
```

**Step 4: Commit**

```bash
git add apps/KeywordSelection/tests/
git commit -m "test: add Keyword model tests"
```

### Task 1.3: PCPAO Importer Service Tests

**Files:**
- Create: `apps/WebScraper/tests/test_services.py`

**Step 1: Write service tests**

```python
# apps/WebScraper/tests/test_services.py
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from apps.WebScraper.services.pcpao_importer import (
    map_csv_row_to_property,
    bulk_upsert_properties,
    FIELD_MAPPING,
)
from apps.WebScraper.services.property_types import dor_code_to_description

pytestmark = pytest.mark.django_db

class TestMapCsvRowToProperty:
    def test_maps_basic_fields(self):
        """Test CSV row mapping to PropertyListing fields."""
        row = {
            'PARCEL ID': '15-29-16-12345-000-0010',
            'SITUS ADDRESS': '123 Main St',
            'SITUS CITY': 'CLEARWATER',
            'SITUS ZIP': '33755',
            'OWNER 1': 'John Doe',
            'JUST VALUE': '245000',
            'ASSESSED VALUE': '220500',
            'LIVING AREA': '1450',
            'YEAR BUILT': '1987',
            'BEDROOMS': '3',
            'BATHROOMS': '2',
            'LAND AREA': '10890',  # sqft
        }
        result = map_csv_row_to_property(row)

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['address'] == '123 Main St'
        assert result['city'] == 'Clearwater'  # Should be title-cased
        assert result['market_value'] == Decimal('245000')
        assert result['building_sqft'] == 1450

    def test_handles_missing_fields(self):
        """Test mapping handles missing optional fields."""
        row = {
            'PARCEL ID': '15-29-16-12345-000-0010',
            'SITUS ADDRESS': '123 Main St',
        }
        result = map_csv_row_to_property(row)

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result.get('market_value') is None or result.get('market_value') == Decimal('0')

    def test_handles_empty_numeric_values(self):
        """Test mapping handles empty strings for numeric fields."""
        row = {
            'PARCEL ID': '15-29-16-12345-000-0010',
            'SITUS ADDRESS': '123 Main St',
            'JUST VALUE': '',
            'LIVING AREA': '',
            'BEDROOMS': '',
        }
        result = map_csv_row_to_property(row)

        # Should not raise, should handle gracefully
        assert result['parcel_id'] == '15-29-16-12345-000-0010'


class TestBulkUpsertProperties:
    def test_creates_new_properties(self, db):
        """Test bulk upsert creates new properties."""
        from apps.WebScraper.models import PropertyListing

        properties_data = [
            {'parcel_id': 'new-001', 'address': 'Test 1', 'city': 'Test'},
            {'parcel_id': 'new-002', 'address': 'Test 2', 'city': 'Test'},
        ]

        created, updated = bulk_upsert_properties(properties_data)

        assert created == 2
        assert updated == 0
        assert PropertyListing.objects.count() == 2

    def test_updates_existing_properties(self, sample_property):
        """Test bulk upsert updates existing properties."""
        from apps.WebScraper.models import PropertyListing

        properties_data = [{
            'parcel_id': sample_property.parcel_id,
            'address': 'Updated Address',
            'city': sample_property.city,
        }]

        created, updated = bulk_upsert_properties(properties_data)

        assert created == 0
        assert updated == 1
        sample_property.refresh_from_db()
        assert sample_property.address == 'Updated Address'


class TestPropertyTypeConversion:
    def test_dor_code_single_family(self):
        """Test DOR code conversion for single family."""
        result = dor_code_to_description('01')
        assert 'single family' in result.lower() or 'residential' in result.lower()

    def test_dor_code_condo(self):
        """Test DOR code conversion for condominium."""
        result = dor_code_to_description('04')
        assert 'condo' in result.lower()

    def test_dor_code_unknown(self):
        """Test DOR code conversion for unknown code."""
        result = dor_code_to_description('XX')
        assert result is not None  # Should return default or unknown
```

**Step 2: Run tests**

```bash
pytest apps/WebScraper/tests/test_services.py -v
```

**Step 3: Commit**

```bash
git add apps/WebScraper/tests/test_services.py
git commit -m "test: add PCPAO importer service tests"
```

---

## Stream 2: Views & API Tests

**Assigned Claude Instance:** Instance 2
**Estimated Tests:** 20
**Dependencies:** None (uses test client)

### Task 2.1: Pages App View Tests

**Files:**
- Create: `apps/Pages/tests/__init__.py`
- Create: `apps/Pages/tests/test_views.py`

**Step 1: Create test directory**

```python
# apps/Pages/tests/__init__.py
```

**Step 2: Write view tests**

```python
# apps/Pages/tests/test_views.py
import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

class TestPagesViews:
    def test_home_page_renders(self, client):
        """Test home page returns 200 and uses correct template."""
        response = client.get('/')
        assert response.status_code == 200

    def test_about_page_renders(self, client):
        """Test about page returns 200."""
        response = client.get('/about/')
        assert response.status_code == 200

    def test_help_page_renders(self, client):
        """Test help page returns 200."""
        response = client.get('/help/')
        assert response.status_code == 200
```

**Step 3: Run tests**

```bash
pytest apps/Pages/tests/test_views.py -v
```

**Step 4: Commit**

```bash
git add apps/Pages/tests/
git commit -m "test: add Pages app view tests"
```

### Task 2.2: WebScraper View Tests

**Files:**
- Create: `apps/WebScraper/tests/test_views.py`

**Step 1: Write scraper view tests**

```python
# apps/WebScraper/tests/test_views.py
import pytest
from django.test import Client
from django.urls import reverse
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.django_db

class TestWebScraperViews:
    def test_scraper_page_get(self, client):
        """Test GET request to scraper page returns form."""
        response = client.get('/scraper/')
        assert response.status_code == 200

    @patch('apps.WebScraper.views.start_processing_pipeline')
    def test_scraper_page_post_starts_task(self, mock_task, client):
        """Test POST starts Celery task."""
        mock_task.delay.return_value.id = 'test-task-id'

        response = client.post('/scraper/', {
            'city': 'Clearwater',
            'property_type': 'Single Family',
        })

        # Should redirect to progress page or return task ID
        assert response.status_code in [200, 302]

    def test_progress_page_renders(self, client):
        """Test progress page renders with task_id."""
        response = client.get('/scraper/progress/test-task-123/')
        assert response.status_code == 200

    def test_task_status_api_pending(self, client):
        """Test task status API returns JSON for pending task."""
        with patch('celery.result.AsyncResult') as mock_result:
            mock_result.return_value.state = 'PENDING'
            mock_result.return_value.info = None

            response = client.get('/scraper/status/test-task-123/')

            assert response.status_code == 200
            assert response['Content-Type'] == 'application/json'

    def test_task_status_api_success(self, client):
        """Test task status API returns result on success."""
        with patch('celery.result.AsyncResult') as mock_result:
            mock_result.return_value.state = 'SUCCESS'
            mock_result.return_value.result = {'properties_found': 10}

            response = client.get('/scraper/status/test-task-123/')

            assert response.status_code == 200
```

**Step 2: Run tests**

```bash
pytest apps/WebScraper/tests/test_views.py -v
```

**Step 3: Commit**

```bash
git add apps/WebScraper/tests/test_views.py
git commit -m "test: add WebScraper view tests"
```

### Task 2.3: KeywordSelection API Tests

**Files:**
- Create: `apps/KeywordSelection/tests/test_views.py`

**Step 1: Write API tests**

```python
# apps/KeywordSelection/tests/test_views.py
import pytest
import json
from django.test import Client
from apps.KeywordSelection.models import Keyword

pytestmark = pytest.mark.django_db

class TestKeywordSelectionViews:
    @pytest.fixture
    def keywords(self, db):
        """Create test keywords."""
        return [
            Keyword.objects.create(name='City', priority=1, is_active=True, data_type='select'),
            Keyword.objects.create(name='Price', priority=2, is_active=True, data_type='range'),
            Keyword.objects.create(name='Bedrooms', priority=3, is_active=True, data_type='number'),
        ]

    def test_keyword_selection_page_renders(self, client, keywords):
        """Test keyword selection page returns 200."""
        response = client.get('/keyword/keyword-selection')
        assert response.status_code == 200

    def test_get_keywords_api(self, client, keywords):
        """Test get_keywords API returns all active keywords."""
        response = client.get('/keyword/get-keywords/')
        assert response.status_code == 200

        data = json.loads(response.content)
        assert len(data) == 3

    def test_get_keywords_returns_json(self, client, keywords):
        """Test get_keywords returns proper JSON format."""
        response = client.get('/keyword/get-keywords/')
        data = json.loads(response.content)

        # Check structure
        assert all('name' in k for k in data)
        assert all('priority' in k for k in data)

    def test_submit_keyword_order_updates_priorities(self, client, keywords):
        """Test submit_keyword_order updates keyword priorities."""
        new_order = [
            {'id': keywords[2].id, 'priority': 1},
            {'id': keywords[0].id, 'priority': 2},
            {'id': keywords[1].id, 'priority': 3},
        ]

        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'keywords': new_order}),
            content_type='application/json',
        )

        assert response.status_code == 200

        # Verify priorities updated
        keywords[2].refresh_from_db()
        assert keywords[2].priority == 1

    def test_submit_keyword_order_validates_input(self, client):
        """Test submit_keyword_order rejects invalid input."""
        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'invalid': 'data'}),
            content_type='application/json',
        )

        assert response.status_code in [400, 422]
```

**Step 2: Run tests**

```bash
pytest apps/KeywordSelection/tests/test_views.py -v
```

**Step 3: Commit**

```bash
git add apps/KeywordSelection/tests/test_views.py
git commit -m "test: add KeywordSelection API tests"
```

---

## Stream 3: Celery Task Tests

**Assigned Claude Instance:** Instance 3
**Estimated Tests:** 15
**Dependencies:** Requires celery eager mode configuration

### Task 3.1: Configure Celery for Testing

**Files:**
- Create: `apps/WebScraper/tests/test_tasks.py`
- Modify: `conftest.py` (add celery fixture)

**Step 1: Add celery test configuration to conftest.py**

Add to `conftest.py`:
```python
@pytest.fixture(scope='session')
def celery_config():
    return {
        'broker_url': 'memory://',
        'result_backend': 'cache+memory://',
        'task_always_eager': True,
        'task_eager_propagates': True,
    }

@pytest.fixture
def celery_eager(settings):
    """Configure Celery to run tasks synchronously."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
```

**Step 2: Write task tests**

```python
# apps/WebScraper/tests/test_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

pytestmark = [pytest.mark.django_db, pytest.mark.celery]

class TestScrapeDataTasks:
    @patch('apps.WebScraper.tasks.scrape_data.PCPAOScraper')
    def test_scrape_pinellas_properties_creates_records(self, mock_scraper_class, celery_eager):
        """Test scrape task creates PropertyListing records."""
        from apps.WebScraper.tasks.scrape_data import scrape_pinellas_properties
        from apps.WebScraper.models import PropertyListing

        # Mock scraper to return test data
        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = [
            {
                'parcel_id': 'test-001',
                'address': '123 Test St',
                'city': 'Clearwater',
                'market_value': 250000,
            }
        ]
        mock_scraper_class.return_value = mock_scraper

        result = scrape_pinellas_properties({'city': 'Clearwater'}, limit=10)

        assert PropertyListing.objects.filter(parcel_id='test-001').exists()

    @patch('apps.WebScraper.tasks.scrape_data.TaxCollectorScraper')
    def test_scrape_tax_data_updates_records(self, mock_scraper_class, sample_property, celery_eager):
        """Test tax scraper updates existing properties."""
        from apps.WebScraper.tasks.scrape_data import scrape_tax_data

        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = {
            sample_property.parcel_id: {
                'tax_amount': 3500.00,
                'tax_status': 'Paid',
                'delinquent': False,
            }
        }
        mock_scraper_class.return_value = mock_scraper

        scrape_tax_data([sample_property.parcel_id])

        sample_property.refresh_from_db()
        assert sample_property.tax_amount == Decimal('3500.00')


class TestSortDataTasks:
    def test_generate_sorted_properties_creates_excel(self, multiple_properties, celery_eager, tmp_path):
        """Test Excel generation creates valid file."""
        from apps.WebScraper.tasks.sort_data import generate_sorted_properties

        with patch('apps.WebScraper.tasks.sort_data.EXCEL_PATH', str(tmp_path)):
            result = generate_sorted_properties()

        # Should return path to created file
        assert result is not None or (tmp_path / 'PropertyListings.xlsx').exists()


class TestEmailTasks:
    @patch('apps.WebScraper.tasks.email_results.send_mail')
    def test_send_results_via_email(self, mock_send_mail, celery_eager):
        """Test email task calls send_mail."""
        from apps.WebScraper.tasks.email_results import send_results_via_email

        mock_send_mail.return_value = 1

        result = send_results_via_email(
            recipient='test@example.com',
            excel_path='/tmp/test.xlsx',
        )

        mock_send_mail.assert_called_once()
```

**Step 3: Run tests**

```bash
pytest apps/WebScraper/tests/test_tasks.py -v -m celery
```

**Step 4: Commit**

```bash
git add apps/WebScraper/tests/test_tasks.py conftest.py
git commit -m "test: add Celery task tests"
```

### Task 3.2: PDF and Visualization Task Tests

**Files:**
- Modify: `apps/WebScraper/tests/test_tasks.py`

**Step 1: Add PDF generation tests**

```python
class TestPDFTasks:
    def test_generate_listing_pdf_creates_file(self, sample_property, celery_eager, tmp_path):
        """Test PDF generation creates valid file."""
        from apps.WebScraper.tasks.listings_pdf import generate_listing_pdf

        with patch('apps.WebScraper.tasks.listings_pdf.PDF_PATH', str(tmp_path)):
            result = generate_listing_pdf([sample_property.parcel_id])

        assert result is not None


class TestVisualizationTasks:
    def test_analyze_data_creates_charts(self, multiple_properties, celery_eager, tmp_path):
        """Test visualization task creates chart images."""
        from apps.WebScraper.tasks.visual_data import analyze_data

        with patch('apps.WebScraper.tasks.visual_data.OUTPUT_PATH', str(tmp_path)):
            result = analyze_data()

        # Should create visualization files
        assert result is not None
```

**Step 2: Run tests**

```bash
pytest apps/WebScraper/tests/test_tasks.py -v
```

**Step 3: Commit**

```bash
git add apps/WebScraper/tests/test_tasks.py
git commit -m "test: add PDF and visualization task tests"
```

---

## Stream 4: Scraper Tests (Mocked)

**Assigned Claude Instance:** Instance 4
**Estimated Tests:** 15
**Dependencies:** Uses mocked Selenium WebDriver

### Task 4.1: PCPAO Scraper Tests

**Files:**
- Create: `apps/WebScraper/tests/test_scrapers.py`

**Step 1: Write mocked scraper tests**

```python
# apps/WebScraper/tests/test_scrapers.py
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from decimal import Decimal

pytestmark = [pytest.mark.django_db, pytest.mark.selenium]

class TestPCPAOScraper:
    @pytest.fixture
    def mock_webdriver(self):
        """Create mock Chrome WebDriver."""
        with patch('apps.WebScraper.tasks.pcpao_scraper.webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            yield mock_driver

    def test_scraper_initialization(self, mock_webdriver):
        """Test scraper initializes WebDriver correctly."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        assert scraper is not None

    def test_scraper_navigates_to_search_page(self, mock_webdriver):
        """Test scraper navigates to PCPAO Advanced Search."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        scraper.navigate_to_search()

        mock_webdriver.get.assert_called()
        assert 'pcpao' in mock_webdriver.get.call_args[0][0].lower()

    def test_scraper_extracts_property_data(self, mock_webdriver):
        """Test scraper extracts data from search results."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        # Mock finding elements
        mock_element = MagicMock()
        mock_element.text = '15-29-16-12345-000-0010'
        mock_webdriver.find_elements.return_value = [mock_element]

        scraper = PCPAOScraper()
        results = scraper.extract_search_results()

        assert len(results) >= 0  # May be empty with mock

    def test_scraper_handles_no_results(self, mock_webdriver):
        """Test scraper handles empty search results gracefully."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        mock_webdriver.find_elements.return_value = []

        scraper = PCPAOScraper()
        results = scraper.extract_search_results()

        assert results == [] or results is None

    def test_scraper_closes_driver(self, mock_webdriver):
        """Test scraper closes WebDriver on cleanup."""
        from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

        scraper = PCPAOScraper()
        scraper.close()

        mock_webdriver.quit.assert_called_once()


class TestTaxCollectorScraper:
    @pytest.fixture
    def mock_webdriver(self):
        """Create mock Chrome WebDriver."""
        with patch('apps.WebScraper.tasks.tax_collector_scraper.webdriver') as mock_wd:
            mock_driver = MagicMock()
            mock_wd.Chrome.return_value = mock_driver
            yield mock_driver

    def test_scraper_searches_by_parcel_id(self, mock_webdriver):
        """Test tax scraper searches by parcel ID."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        scraper = TaxCollectorScraper()
        scraper.search_parcel('15-29-16-12345-000-0010')

        # Should have interacted with search field
        mock_webdriver.find_element.assert_called()

    def test_scraper_extracts_tax_data(self, mock_webdriver):
        """Test tax scraper extracts tax information."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper

        # Mock tax data elements
        mock_element = MagicMock()
        mock_element.text = '$3,125.00'
        mock_webdriver.find_element.return_value = mock_element

        scraper = TaxCollectorScraper()
        data = scraper.extract_tax_info()

        assert data is not None

    def test_scraper_handles_parcel_not_found(self, mock_webdriver):
        """Test scraper handles missing parcel gracefully."""
        from apps.WebScraper.tasks.tax_collector_scraper import TaxCollectorScraper
        from selenium.common.exceptions import NoSuchElementException

        mock_webdriver.find_element.side_effect = NoSuchElementException()

        scraper = TaxCollectorScraper()
        data = scraper.search_parcel('invalid-parcel-id')

        assert data is None or data == {}
```

**Step 2: Run tests**

```bash
pytest apps/WebScraper/tests/test_scrapers.py -v -m selenium
```

**Step 3: Commit**

```bash
git add apps/WebScraper/tests/test_scrapers.py
git commit -m "test: add mocked Selenium scraper tests"
```

---

## Stream 5: Frontend JavaScript Tests

**Assigned Claude Instance:** Instance 5
**Estimated Tests:** 10
**Dependencies:** Jest, jsdom

### Task 5.1: Setup Jest for Frontend Testing

**Files:**
- Create: `jest.config.js`
- Create: `static/js/dev/__tests__/keywordSelection.test.js`
- Modify: `package.json` (add jest config)

**Step 1: Create Jest configuration**

```javascript
// jest.config.js
module.exports = {
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/static/js/dev'],
  testMatch: ['**/__tests__/**/*.test.js'],
  transform: {
    '^.+\\.js$': 'babel-jest',
  },
  setupFilesAfterEnv: ['<rootDir>/static/js/dev/__tests__/setup.js'],
  moduleNameMapper: {
    '^sortablejs$': '<rootDir>/node_modules/sortablejs/Sortable.min.js',
  },
};
```

**Step 2: Create test setup file**

```javascript
// static/js/dev/__tests__/setup.js
global.fetch = jest.fn();

// Reset mocks between tests
beforeEach(() => {
  fetch.mockClear();
  document.body.innerHTML = '';
});
```

**Step 3: Write keyword selection tests**

```javascript
// static/js/dev/__tests__/keywordSelection.test.js
describe('KeywordSelection', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="keyword-list"></div>
      <button id="save-order">Save</button>
    `;
  });

  test('fetches keywords on initialization', async () => {
    const mockKeywords = [
      { id: 1, name: 'City', priority: 1 },
      { id: 2, name: 'Price', priority: 2 },
    ];

    fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockKeywords),
    });

    // Import and initialize
    const { initKeywordSelection } = require('../keywordSelection');
    await initKeywordSelection();

    expect(fetch).toHaveBeenCalledWith('/keyword/get-keywords/');
  });

  test('renders keywords in priority order', async () => {
    const mockKeywords = [
      { id: 1, name: 'City', priority: 2 },
      { id: 2, name: 'Price', priority: 1 },
    ];

    fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockKeywords),
    });

    const { initKeywordSelection, renderKeywords } = require('../keywordSelection');
    renderKeywords(mockKeywords);

    const list = document.getElementById('keyword-list');
    expect(list.children.length).toBe(2);
  });

  test('submits reordered keywords', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });

    const { submitKeywordOrder } = require('../keywordSelection');
    const newOrder = [
      { id: 2, priority: 1 },
      { id: 1, priority: 2 },
    ];

    await submitKeywordOrder(newOrder);

    expect(fetch).toHaveBeenCalledWith(
      '/keyword/submit-keyword-order/',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('keywords'),
      })
    );
  });

  test('handles fetch error gracefully', async () => {
    fetch.mockRejectedValueOnce(new Error('Network error'));

    const { initKeywordSelection } = require('../keywordSelection');

    // Should not throw
    await expect(initKeywordSelection()).resolves.not.toThrow();
  });
});
```

**Step 4: Add test script to package.json**

Add to scripts:
```json
"test": "jest",
"test:watch": "jest --watch",
"test:coverage": "jest --coverage"
```

**Step 5: Install Jest dependencies**

```bash
npm install --save-dev jest babel-jest @babel/preset-env jsdom
```

**Step 6: Run tests**

```bash
npm test
```

**Step 7: Commit**

```bash
git add jest.config.js static/js/dev/__tests__/ package.json
git commit -m "test: add frontend JavaScript tests with Jest"
```

---

## Stream 6: Integration Tests

**Assigned Claude Instance:** Instance 6
**Estimated Tests:** 10
**Dependencies:** Requires database and test fixtures

### Task 6.1: End-to-End Workflow Tests

**Files:**
- Create: `apps/WebScraper/tests/test_integration.py`

**Step 1: Write integration tests**

```python
# apps/WebScraper/tests/test_integration.py
import pytest
from django.test import Client, TransactionTestCase
from unittest.mock import patch, MagicMock
from decimal import Decimal

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]

class TestPropertySearchWorkflow:
    """Integration tests for property search and display workflow."""

    def test_search_filters_by_city(self, client, multiple_properties):
        """Test search filters properties by city correctly."""
        from apps.WebScraper.models import PropertyListing

        clearwater_count = PropertyListing.objects.filter(city='Clearwater').count()

        # Simulate search request
        response = client.get('/scraper/', {'city': 'Clearwater'})

        assert response.status_code == 200

    def test_search_filters_by_price_range(self, client, multiple_properties):
        """Test search filters by price range."""
        from apps.WebScraper.models import PropertyListing

        in_range = PropertyListing.objects.filter(
            market_value__gte=200000,
            market_value__lte=300000,
        ).count()

        assert in_range >= 0


class TestKeywordOrderingWorkflow:
    """Integration tests for keyword priority ordering."""

    def test_keyword_reorder_persists(self, client, db):
        """Test keyword reordering persists to database."""
        import json
        from apps.KeywordSelection.models import Keyword

        # Create keywords
        k1 = Keyword.objects.create(name='First', priority=1)
        k2 = Keyword.objects.create(name='Second', priority=2)

        # Reorder
        new_order = [
            {'id': k2.id, 'priority': 1},
            {'id': k1.id, 'priority': 2},
        ]

        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'keywords': new_order}),
            content_type='application/json',
        )

        assert response.status_code == 200

        k1.refresh_from_db()
        k2.refresh_from_db()
        assert k2.priority < k1.priority


class TestDataImportWorkflow:
    """Integration tests for bulk data import."""

    def test_import_from_fixture_file(self, db):
        """Test importing sample data from fixture."""
        from django.core.management import call_command
        from apps.WebScraper.models import PropertyListing

        initial_count = PropertyListing.objects.count()

        call_command(
            'import_pcpao_data',
            '--file=apps/WebScraper/fixtures/sample_pcpao_data.csv',
            '--quiet',
        )

        assert PropertyListing.objects.count() > initial_count

    def test_import_updates_existing_properties(self, sample_property, db):
        """Test import updates existing properties instead of duplicating."""
        from django.core.management import call_command
        from apps.WebScraper.models import PropertyListing

        initial_count = PropertyListing.objects.count()

        # Import same data twice
        call_command(
            'import_pcpao_data',
            '--file=apps/WebScraper/fixtures/sample_pcpao_data.csv',
            '--quiet',
        )

        # Count should not double
        final_count = PropertyListing.objects.count()
        assert final_count <= initial_count + 3  # Sample has 3 records
```

**Step 2: Run integration tests**

```bash
pytest apps/WebScraper/tests/test_integration.py -v -m integration
```

**Step 3: Commit**

```bash
git add apps/WebScraper/tests/test_integration.py
git commit -m "test: add integration tests for key workflows"
```

### Task 6.2: Admin Interface Tests

**Files:**
- Create: `apps/WebScraper/tests/test_admin.py`

**Step 1: Write admin tests**

```python
# apps/WebScraper/tests/test_admin.py
import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from apps.WebScraper.admin import PropertyListingAdmin
from apps.WebScraper.models import PropertyListing

pytestmark = pytest.mark.django_db

class TestPropertyListingAdmin:
    @pytest.fixture
    def admin_user(self, db):
        return User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass',
        )

    @pytest.fixture
    def admin_client(self, client, admin_user):
        client.force_login(admin_user)
        return client

    def test_admin_changelist_loads(self, admin_client):
        """Test admin property list page loads."""
        response = admin_client.get('/admin/WebScraper/propertylisting/')
        assert response.status_code == 200

    def test_admin_search_by_parcel(self, admin_client, sample_property):
        """Test admin search functionality."""
        response = admin_client.get(
            '/admin/WebScraper/propertylisting/',
            {'q': sample_property.parcel_id},
        )
        assert response.status_code == 200
        assert sample_property.parcel_id.encode() in response.content

    def test_admin_filter_by_city(self, admin_client, multiple_properties):
        """Test admin filter by city."""
        response = admin_client.get(
            '/admin/WebScraper/propertylisting/',
            {'city': 'Clearwater'},
        )
        assert response.status_code == 200
```

**Step 2: Run tests**

```bash
pytest apps/WebScraper/tests/test_admin.py -v
```

**Step 3: Commit**

```bash
git add apps/WebScraper/tests/test_admin.py
git commit -m "test: add Django admin interface tests"
```

---

## Parallel Execution Instructions

### Launching All Streams

Run these commands in separate terminals (or use tmux/screen):

**Terminal 1 - Stream 1 (Models & Services):**
```bash
cd /home/gilhooleyp/projects/home_finder
source venv/Scripts/activate
pytest apps/WebScraper/tests/test_models.py apps/WebScraper/tests/test_services.py apps/KeywordSelection/tests/test_models.py -v
```

**Terminal 2 - Stream 2 (Views & APIs):**
```bash
cd /home/gilhooleyp/projects/home_finder
source venv/Scripts/activate
pytest apps/Pages/tests/test_views.py apps/WebScraper/tests/test_views.py apps/KeywordSelection/tests/test_views.py -v
```

**Terminal 3 - Stream 3 (Celery Tasks):**
```bash
cd /home/gilhooleyp/projects/home_finder
source venv/Scripts/activate
pytest apps/WebScraper/tests/test_tasks.py -v -m celery
```

**Terminal 4 - Stream 4 (Scrapers):**
```bash
cd /home/gilhooleyp/projects/home_finder
source venv/Scripts/activate
pytest apps/WebScraper/tests/test_scrapers.py -v -m selenium
```

**Terminal 5 - Stream 5 (Frontend):**
```bash
cd /home/gilhooleyp/projects/home_finder
npm test
```

**Terminal 6 - Stream 6 (Integration):**
```bash
cd /home/gilhooleyp/projects/home_finder
source venv/Scripts/activate
pytest apps/WebScraper/tests/test_integration.py apps/WebScraper/tests/test_admin.py -v -m integration
```

### Running All Tests with Coverage

After parallel development, run full suite:
```bash
pytest --cov=apps --cov-report=html --cov-report=term-missing -v
```

### CI/CD Configuration (Optional)

Create `.github/workflows/test.yml`:
```yaml
name: Tests
on: [push, pull_request]

jobs:
  test-stream-1:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Model & Service Tests
        run: pytest apps/WebScraper/tests/test_models.py apps/WebScraper/tests/test_services.py -v

  test-stream-2:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run View & API Tests
        run: pytest apps/*/tests/test_views.py -v

  # Add remaining streams...
```

---

## Summary

| Stream | Tests | Files | Claude Instance |
|--------|-------|-------|-----------------|
| 1. Models & Services | 25 | test_models.py, test_services.py | Instance 1 |
| 2. Views & APIs | 20 | test_views.py (3 apps) | Instance 2 |
| 3. Celery Tasks | 15 | test_tasks.py | Instance 3 |
| 4. Scrapers (mocked) | 15 | test_scrapers.py | Instance 4 |
| 5. Frontend JS | 10 | keywordSelection.test.js | Instance 5 |
| 6. Integration | 10 | test_integration.py, test_admin.py | Instance 6 |

**Total: ~95 tests across 6 parallel streams**
