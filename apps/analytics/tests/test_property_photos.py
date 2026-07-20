from importlib import import_module

import pytest

from apps.analytics.models import PropertyListing
from apps.analytics.services.property_photos import sanitize_county_photo_url
from apps.analytics.tests.factories import PropertyListingFactory


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('https://www.pcpao.gov/property-photo/example.jpg', 'https://www.pcpao.gov/property-photo/example.jpg'),
        ('https://images.pcpao.gov/parcels/example.jpg', 'https://images.pcpao.gov/parcels/example.jpg'),
        ('https://pcpao.gov:443/photo.jpg', 'https://pcpao.gov:443/photo.jpg'),
        ('http://www.pcpao.gov/photo.jpg', None),
        ('https://maps.googleapis.com/maps/api/streetview?key=secret', None),
        ('https://pcpao.gov.example.com/photo.jpg', None),
        ('https://user@pcpao.gov/photo.jpg', None),
        ('javascript:alert(1)', None),
        ('', None),
        (None, None),
    ],
)
def test_sanitize_county_photo_url(value, expected):
    assert sanitize_county_photo_url(value) == expected


@pytest.mark.django_db
def test_cleanup_migration_keeps_only_county_photos():
    county_listing = PropertyListingFactory(image_url='https://www.pcpao.gov/property-photo/allowed.jpg')
    stale_listing = PropertyListingFactory(image_url='https://maps.googleapis.com/maps/api/streetview?key=stale')

    migration = import_module('apps.analytics.migrations.0006_keep_only_pcpao_photos')

    class CurrentApps:
        @staticmethod
        def get_model(app_label, model_name):
            assert (app_label, model_name) == ('WebScraper', 'PropertyListing')
            return PropertyListing

    migration.keep_only_pcpao_photos(CurrentApps(), schema_editor=None)

    county_listing.refresh_from_db()
    stale_listing.refresh_from_db()
    assert county_listing.image_url == 'https://www.pcpao.gov/property-photo/allowed.jpg'
    assert stale_listing.image_url is None
