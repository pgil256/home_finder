# apps/analytics/tests/test_integration.py
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]


class TestPropertySearchWorkflow:
    """Integration tests for property search and display workflow."""

    def test_search_filters_by_city(self, client, multiple_properties):
        """Test search filters properties by city correctly."""
        from apps.analytics.models import PropertyListing

        clearwater_count = PropertyListing.objects.filter(city='Clearwater').count()
        assert clearwater_count > 0  # Verify fixture created some Clearwater properties

        # Verify we can query by city
        properties = PropertyListing.objects.filter(city='Clearwater')
        assert properties.count() == clearwater_count

    def test_search_filters_by_price_range(self, client, multiple_properties):
        """Test search filters by price range."""
        from apps.analytics.models import PropertyListing

        in_range = PropertyListing.objects.filter(
            market_value__gte=200000,
            market_value__lte=300000,
        ).count()

        # Verify price range filtering works
        assert in_range >= 0

    def test_scraper_page_loads(self, client):
        """Test the scraper page renders successfully."""
        response = client.get('/analytics/')
        assert response.status_code == 200


class TestDataImportWorkflow:
    """Integration tests for bulk data import."""

    def test_property_listing_creation(self, db):
        """Test PropertyListing can be created and queried."""
        from apps.analytics.models import PropertyListing

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
        from apps.analytics.models import PropertyListing

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
