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
