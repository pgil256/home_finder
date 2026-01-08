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
