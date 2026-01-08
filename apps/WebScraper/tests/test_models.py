import pytest
from decimal import Decimal
from django.db import IntegrityError
from apps.WebScraper.models import PropertyListing

pytestmark = pytest.mark.django_db


class TestPropertyListingModel:
    def test_create_property_listing(self, sample_property):
        """Test that a PropertyListing can be created with valid data."""
        assert sample_property.pk is not None
        assert sample_property.parcel_id == '15-29-16-12345-000-0010'
        assert sample_property.city == 'Clearwater'

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
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal('100000'),
            building_sqft=0,
        )
        assert prop.price_per_sqft is None

    def test_price_per_sqft_with_null_sqft(self, db):
        """Test price_per_sqft returns None when sqft is null."""
        prop = PropertyListing.objects.create(
            parcel_id='test-null-sqft',
            address='Test',
            city='Test',
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal('100000'),
            building_sqft=None,
        )
        assert prop.price_per_sqft is None

    def test_price_per_sqft_with_null_market_value(self, db):
        """Test price_per_sqft returns None when market_value is null."""
        prop = PropertyListing.objects.create(
            parcel_id='test-null-value',
            address='Test',
            city='Test',
            zip_code='33755',
            property_type='Single Family',
            market_value=None,
            building_sqft=1500,
        )
        assert prop.price_per_sqft is None

    def test_parcel_id_unique_constraint(self, sample_property):
        """Test that duplicate parcel_id raises error."""
        with pytest.raises(IntegrityError):
            PropertyListing.objects.create(
                parcel_id=sample_property.parcel_id,
                address='Different',
                city='Different',
                zip_code='33701',
                property_type='Condo',
            )

    def test_str_representation(self, sample_property):
        """Test __str__ returns meaningful representation."""
        str_repr = str(sample_property)
        assert sample_property.parcel_id in str_repr or sample_property.address in str_repr

    def test_default_tax_status(self, db):
        """Test default tax_status is 'Unknown'."""
        prop = PropertyListing.objects.create(
            parcel_id='test-default-status',
            address='Test',
            city='Test',
            zip_code='33755',
            property_type='Single Family',
        )
        assert prop.tax_status == 'Unknown'

    def test_default_delinquent_is_false(self, db):
        """Test default delinquent flag is False."""
        prop = PropertyListing.objects.create(
            parcel_id='test-default-delinquent',
            address='Test',
            city='Test',
            zip_code='33755',
            property_type='Single Family',
        )
        assert prop.delinquent is False

    def test_timestamps_auto_set(self, db):
        """Test created_at and last_scraped are auto-set."""
        prop = PropertyListing.objects.create(
            parcel_id='test-timestamps',
            address='Test',
            city='Test',
            zip_code='33755',
            property_type='Single Family',
        )
        assert prop.created_at is not None
        assert prop.last_scraped is not None
