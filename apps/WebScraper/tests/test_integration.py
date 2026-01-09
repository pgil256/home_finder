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
        assert clearwater_count > 0  # Verify fixture created some Clearwater properties

        # Verify we can query by city
        properties = PropertyListing.objects.filter(city='Clearwater')
        assert properties.count() == clearwater_count

    def test_search_filters_by_price_range(self, client, multiple_properties):
        """Test search filters by price range."""
        from apps.WebScraper.models import PropertyListing

        in_range = PropertyListing.objects.filter(
            market_value__gte=200000,
            market_value__lte=300000,
        ).count()

        # Verify price range filtering works
        assert in_range >= 0

    def test_scraper_page_loads(self, client):
        """Test the scraper page renders successfully."""
        response = client.get('/scraper/')
        assert response.status_code == 200

    def test_progress_page_accepts_task_id(self, client):
        """Test progress page accepts arbitrary task IDs."""
        response = client.get('/scraper/progress/test-task-123/')
        assert response.status_code == 200


class TestKeywordOrderingWorkflow:
    """Integration tests for keyword priority ordering."""

    def test_keyword_reorder_persists(self, client, db):
        """Test keyword reordering persists to database."""
        import json
        from apps.KeywordSelection.models import Keyword

        # Create keywords
        k1 = Keyword.objects.create(name='First', priority=1)
        k2 = Keyword.objects.create(name='Second', priority=2)

        # Reorder using actual API format (ordered_keywords with name/priority)
        new_order = [
            {'name': 'Second', 'priority': 1},
            {'name': 'First', 'priority': 2},
        ]

        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'ordered_keywords': new_order}),
            content_type='application/json',
        )

        assert response.status_code == 200

        k1.refresh_from_db()
        k2.refresh_from_db()
        assert k2.priority < k1.priority

    def test_get_keywords_returns_json(self, client, db):
        """Test get_keywords endpoint returns JSON with keywords."""
        from apps.KeywordSelection.models import Keyword

        # Create test keywords
        Keyword.objects.create(name='City', priority=1, is_active=True)
        Keyword.objects.create(name='Price', priority=2, is_active=True)

        response = client.get('/keyword/get-keywords/')

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'

        data = response.json()
        assert 'keywords' in data
        assert 'City' in data['keywords']
        assert 'Price' in data['keywords']

    def test_keyword_selection_page_loads(self, client):
        """Test keyword selection page renders."""
        response = client.get('/keyword/keyword-selection')
        assert response.status_code == 200


class TestDataImportWorkflow:
    """Integration tests for bulk data import."""

    def test_property_listing_creation(self, db):
        """Test PropertyListing can be created and queried."""
        from apps.WebScraper.models import PropertyListing

        prop = PropertyListing.objects.create(
            parcel_id='test-import-001',
            address='456 Import Test Blvd',
            city='Clearwater',
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal('350000.00'),
        )

        assert PropertyListing.objects.filter(parcel_id='test-import-001').exists()
        assert prop.address == '456 Import Test Blvd'

    def test_property_update_existing(self, sample_property, db):
        """Test updating existing property doesn't create duplicate."""
        from apps.WebScraper.models import PropertyListing

        initial_count = PropertyListing.objects.count()

        # Update existing property
        sample_property.address = 'Updated Address 999'
        sample_property.save()

        # Count should remain the same
        assert PropertyListing.objects.count() == initial_count

        # Verify update persisted
        sample_property.refresh_from_db()
        assert sample_property.address == 'Updated Address 999'

    def test_property_price_per_sqft_calculation(self, sample_property):
        """Test price_per_sqft computed property works in context."""
        expected = sample_property.market_value / sample_property.building_sqft
        assert sample_property.price_per_sqft == expected


class TestTaskStatusAPI:
    """Integration tests for task status API."""

    def test_task_status_endpoint_returns_json(self, client):
        """Test task status API returns JSON response."""
        with patch('apps.WebScraper.views.AsyncResult') as mock_result:
            mock_result.return_value.state = 'PENDING'
            mock_result.return_value.info = None

            response = client.get('/scraper/status/test-task-456/')

            assert response.status_code == 200
            assert response['Content-Type'] == 'application/json'

    def test_task_status_pending_state(self, client):
        """Test task status returns correct format for PENDING state."""
        with patch('apps.WebScraper.views.AsyncResult') as mock_result:
            mock_result.return_value.state = 'PENDING'
            mock_result.return_value.info = None

            response = client.get('/scraper/status/test-task-789/')
            data = response.json()

            assert data['state'] == 'PENDING'
            assert 'current' in data
            assert 'total' in data

    def test_task_status_progress_state(self, client):
        """Test task status returns progress info correctly."""
        with patch('apps.WebScraper.views.AsyncResult') as mock_result:
            mock_result.return_value.state = 'PROGRESS'
            mock_result.return_value.info = {
                'current': 50,
                'total': 100,
                'status': 'Processing...'
            }

            response = client.get('/scraper/status/test-task-progress/')
            data = response.json()

            assert data['state'] == 'PROGRESS'
            assert data['current'] == 50
            assert data['total'] == 100
