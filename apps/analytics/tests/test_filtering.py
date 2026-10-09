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


class TestRiskAndTaxFilters:
    def _parcels(self):
        specs = [
            (
                'zone-a',
                {'evac_zone': 'A', 'subsidence': False, 'est_tax_homestead': 9000, 'est_tax_no_homestead': 10000},
            ),
            ('zone-c', {'evac_zone': 'C', 'subsidence': True, 'est_tax_homestead': 4000, 'est_tax_no_homestead': 5000}),
            (
                'no-zone',
                {'evac_zone': 'NONE', 'subsidence': False, 'est_tax_homestead': 3000, 'est_tax_no_homestead': 3600},
            ),
            (
                'unknown',
                {'evac_zone': None, 'subsidence': None, 'est_tax_homestead': None, 'est_tax_no_homestead': None},
            ),
            # A lot nobody can homestead: only the no-homestead estimate exists.
            ('lot', {'evac_zone': 'D', 'subsidence': False, 'est_tax_homestead': None, 'est_tax_no_homestead': 2500}),
        ]
        for parcel_id, fields in specs:
            PropertyListing.objects.filter(pk=_prop(parcel_id).pk).update(**fields)

    def _ids(self, **params):
        qs, _, _ = _filter(**params)
        return set(qs.values_list('parcel_id', flat=True))

    def test_exclude_evac_drops_zones_through_the_chosen_one(self):
        self._parcels()

        assert self._ids(exclude_evac='A') == {'zone-c', 'no-zone', 'lot'}
        assert self._ids(exclude_evac='C') == {'no-zone', 'lot'}
        assert self._ids(exclude_evac='E') == {'no-zone'}

    def test_unknown_zone_is_not_treated_as_safe(self):
        self._parcels()

        assert 'unknown' not in self._ids(exclude_evac='A')

    def test_outside_sfha_keeps_only_parcels_known_to_be_in_zone_x(self):
        self._parcels()
        for parcel_id, zone in (('zone-a', 'AE'), ('zone-c', 'VE'), ('no-zone', 'X'), ('lot', 'X500')):
            PropertyListing.objects.filter(parcel_id=parcel_id).update(flood_zone=zone)

        assert self._ids(outside_sfha='1') == {'no-zone', 'lot'}
        assert len(self._ids(outside_sfha='yes')) == 5

    def test_exclude_subsidence_keeps_unknowns_and_clean_parcels(self):
        self._parcels()

        assert self._ids(exclude_subsidence='1') == {'zone-a', 'no-zone', 'unknown', 'lot'}

    def test_max_est_tax_uses_the_homestead_estimate_when_there_is_one(self):
        self._parcels()

        # zone-c would pay 4,000 with homestead; its 5,000 no-homestead figure doesn't matter.
        assert self._ids(max_est_tax='4500') == {'zone-c', 'no-zone', 'lot'}
        assert self._ids(max_est_tax='2800') == {'lot'}

    def test_invalid_values_are_ignored_not_fatal(self):
        self._parcels()

        assert len(self._ids(exclude_evac='Z', max_est_tax='cheap', exclude_subsidence='yes')) == 5
