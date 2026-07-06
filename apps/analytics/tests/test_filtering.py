"""Isolated unit tests for the dashboard filter/sort logic."""

import pytest
from django.test import RequestFactory

from apps.analytics.models import PropertyListing
from apps.analytics.services.filtering import apply_filters, apply_sorting

pytestmark = pytest.mark.django_db

rf = RequestFactory()


def _prop(parcel_id, *, property_type='Single Family Home', market_value=250000, city='Clearwater', zip_code='33755'):
    return PropertyListing.objects.create(
        parcel_id=parcel_id,
        address=f'{parcel_id} Main St',
        city=city,
        zip_code=zip_code,
        property_type=property_type,
        market_value=market_value,
    )


def _filter(**params):
    return apply_filters(rf.get('/analytics/', params))


class TestResidentialDefault:
    def test_defaults_to_residential_and_excludes_commercial(self):
        _prop('res-1', property_type='Single Family Home')
        _prop('com-1', property_type='Office Building')

        qs, selected, defaulted = _filter()

        assert defaulted is True
        assert selected == []
        parcels = set(qs.values_list('parcel_id', flat=True))
        assert 'res-1' in parcels
        assert 'com-1' not in parcels

    def test_include_all_disables_residential_default(self):
        _prop('res-1', property_type='Single Family Home')
        _prop('com-1', property_type='Office Building')

        qs, selected, defaulted = _filter(include_all='1')

        assert defaulted is False
        assert {'res-1', 'com-1'} <= set(qs.values_list('parcel_id', flat=True))

    def test_explicit_property_type_is_not_defaulted(self):
        _prop('res-1', property_type='Single Family Home')
        _prop('condo-1', property_type='Condominium')

        qs, selected, defaulted = _filter(property_type='Condo')

        assert defaulted is False
        assert selected == ['Condo']
        assert set(qs.values_list('parcel_id', flat=True)) == {'condo-1'}


class TestNumericBounds:
    def test_price_bounds_filter_inclusively(self):
        _prop('p-low', market_value=100000)
        _prop('p-mid', market_value=300000)
        _prop('p-high', market_value=500000)

        qs, _, _ = _filter(include_all='1', min_price='200000', max_price='400000')

        assert set(qs.values_list('parcel_id', flat=True)) == {'p-mid'}

    def test_invalid_numeric_values_are_ignored_not_fatal(self):
        _prop('p-mid', market_value=300000)

        # Non-numeric filter values are logged and skipped, not raised.
        qs, _, _ = _filter(include_all='1', min_price='abc', max_sqft='not-a-number', min_lot_sqft='oops')

        assert set(qs.values_list('parcel_id', flat=True)) == {'p-mid'}


class TestScalarFilters:
    def test_city_is_case_insensitive_and_zip_is_exact(self):
        _prop('cw', city='Clearwater', zip_code='33755')
        _prop('sp', city='St. Petersburg', zip_code='33701')

        by_city, _, _ = _filter(include_all='1', city='clearwater')
        by_zip, _, _ = _filter(include_all='1', zip_code='33701')

        assert set(by_city.values_list('parcel_id', flat=True)) == {'cw'}
        assert set(by_zip.values_list('parcel_id', flat=True)) == {'sp'}


class TestApplySorting:
    def test_invalid_sort_falls_back_to_default_descending(self):
        _prop('a', market_value=100000)
        _prop('b', market_value=300000)

        ordered = apply_sorting(PropertyListing.objects.all(), 'bogus-field')

        # DEFAULT_SORT is -market_value → highest value first.
        assert list(ordered.values_list('parcel_id', flat=True)) == ['b', 'a']

    def test_ascending_sort_pushes_nulls_last(self):
        _prop('a', market_value=100000)
        _prop('b', market_value=300000)
        _prop('n', market_value=None)

        ordered = apply_sorting(PropertyListing.objects.all(), 'market_value')

        ids = list(ordered.values_list('parcel_id', flat=True))
        assert ids[:2] == ['a', 'b']
        assert ids[-1] == 'n'
