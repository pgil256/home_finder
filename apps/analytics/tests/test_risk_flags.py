from datetime import date
from types import SimpleNamespace

import pytest

from apps.analytics.services.risk_flags import (
    GOOD,
    HIGH,
    INFO,
    MEDIUM,
    allowed_evac_zones,
    build_risk_flags,
    evac_filter_label,
    has_risk_data,
)

TODAY = date(2026, 10, 6)


def _listing(**overrides):
    """A new single-family home with nothing on record."""
    fields = {
        'property_type': 'Single Family Home',
        'year_built': 2015,
        'evac_zone': None,
        'frontage': None,
        'waterfront': False,
        'seawall': False,
        'subsidence': False,
        'contamination': False,
        'historic_landmark': False,
    }
    return SimpleNamespace(**{**fields, **overrides})


def _flags(**overrides):
    return build_risk_flags(_listing(**overrides), today=TODAY)


def _titles(**overrides):
    return [flag.title for flag in _flags(**overrides)]


def test_clean_new_home_has_no_flags():
    assert _flags() == []


class TestEvacuationZone:
    @pytest.mark.parametrize(
        ('zone', 'level'),
        [('A', HIGH), ('B', MEDIUM), ('C', MEDIUM), ('D', INFO), ('E', INFO)],
    )
    def test_level_follows_how_early_the_zone_leaves(self, zone, level):
        (flag,) = _flags(evac_zone=zone)

        assert flag.title == f'Evacuation zone {zone}'
        assert flag.level == level

    def test_zone_a_points_to_flood_insurance_and_elevation_certificate(self):
        (flag,) = _flags(evac_zone='A')

        assert 'flood insurance quote' in flag.ask
        assert 'elevation certificate' in flag.ask

    def test_outside_every_zone_is_good_news_but_not_a_flood_all_clear(self):
        (flag,) = _flags(evac_zone='NONE')

        assert flag.level == GOOD
        assert 'not FEMA flood zones' in flag.ask

    def test_unknown_zone_says_nothing(self):
        assert _flags(evac_zone=None) == []


class TestWaterfront:
    def test_tidal_frontage_is_named(self):
        (flag,) = _flags(waterfront=True, frontage='Gulf')

        assert (flag.level, flag.title) == (MEDIUM, 'Waterfront: Gulf')
        assert 'elevation certificate' in flag.ask

    def test_elevation_certificate_advice_is_not_repeated_in_a_surge_zone(self):
        evac, waterfront = _flags(evac_zone='A', waterfront=True, frontage='Gulf')

        assert 'elevation certificate' in evac.ask
        assert 'elevation certificate' not in waterfront.ask

    def test_waterfront_without_a_frontage_type(self):
        assert _titles(waterfront=True, frontage=None) == ['Waterfront']

    def test_lake_or_pond_gets_the_milder_flag(self):
        (flag,) = _flags(waterfront=True, frontage='Pond')

        assert (flag.level, flag.title) == (INFO, 'Waterfront: Pond')

    def test_pond_frontage_alone_is_not_waterfront(self):
        """The county does not mark most pond-frontage lots as waterfront."""
        assert _flags(waterfront=False, frontage='Pond') == []

    def test_seawall_is_its_own_flag(self):
        assert _titles(waterfront=True, frontage='Canal/River', seawall=True) == ['Waterfront: Canal/River', 'Seawall']


class TestBuildingAge:
    def test_home_built_before_the_2002_code(self):
        (flag,) = _flags(year_built=1987)

        assert flag.level == INFO
        assert flag.title == 'Built in 1987, before the 2002 Florida Building Code'
        assert 'wind-mitigation' in flag.ask

    def test_home_built_in_2002_or_later_is_not_flagged(self):
        assert _flags(year_built=2002) == []

    def test_vacant_land_has_no_age_flags(self):
        assert _flags(year_built=None) == []

    def test_older_condo_gets_the_milestone_inspection_flag(self):
        flags = _flags(property_type='Condominium', year_built=1979)

        assert [flag.title for flag in flags] == [
            'Condo building about 47 years old',
            'Built in 1979, before the 2002 Florida Building Code',
        ]
        assert flags[0].level == MEDIUM
        assert 'milestone inspection report' in flags[0].ask

    def test_condo_under_25_years_is_not_flagged(self):
        assert _flags(property_type='Condominium', year_built=2008) == []

    def test_manufactured_home_land_condo_is_not_a_condo_building(self):
        titles = _titles(property_type='Manufactured Home (Land Condo, Individually Owned)', year_built=1980)

        assert 'Mobile or manufactured home' in titles
        assert not any(title.startswith('Condo building') for title in titles)


class TestRecordFlags:
    def test_subsidence_contamination_and_landmark(self):
        flags = _flags(subsidence=True, contamination=True, historic_landmark=True)

        assert [(flag.level, flag.title) for flag in flags] == [
            (HIGH, 'Subsidence on record'),
            (HIGH, 'Contamination on record'),
            (INFO, 'Local historic landmark'),
        ]

    def test_most_serious_flags_come_first(self):
        flags = _flags(evac_zone='NONE', year_built=1960, seawall=True, subsidence=True)

        assert [flag.level for flag in flags] == [HIGH, MEDIUM, INFO, GOOD]

    def test_every_flag_explains_itself(self):
        flags = _flags(
            property_type='Condominium',
            year_built=1970,
            evac_zone='A',
            frontage='Intracoastal',
            waterfront=True,
            seawall=True,
            subsidence=True,
            contamination=True,
            historic_landmark=True,
        )

        assert len(flags) == 8
        assert all(flag.title and flag.why and flag.ask for flag in flags)


class TestEvacFilter:
    def test_excluding_through_a_zone_keeps_the_later_ones(self):
        assert allowed_evac_zones('B') == ['C', 'D', 'E', 'NONE']
        assert allowed_evac_zones('a') == ['B', 'C', 'D', 'E', 'NONE']
        assert allowed_evac_zones('E') == ['NONE']

    @pytest.mark.parametrize('value', ['', 'Z', 'NONE', None])
    def test_anything_else_is_not_a_filter(self, value):
        assert allowed_evac_zones(value) is None

    def test_labels(self):
        assert evac_filter_label('A') == 'Outside evacuation zone A'
        assert evac_filter_label('C') == 'Outside evacuation zones A-C'
        assert evac_filter_label('E') == 'Not in an evacuation zone'


def test_has_risk_data_only_once_the_county_columns_are_imported():
    assert has_risk_data(_listing(subsidence=None, evac_zone=None)) is False
    assert has_risk_data(_listing(subsidence=False, evac_zone=None)) is True
    assert has_risk_data(_listing(subsidence=None, evac_zone='A')) is True
