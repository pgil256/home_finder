import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError

from apps.analytics.models import PropertyListing, ZipFloodHistory
from apps.analytics.services import flood_claims, flood_zones
from apps.analytics.services.flood_claims import import_flood_claims, summarize_claims, zip_flood_history
from apps.analytics.services.flood_zones import FloodZone, zone_from_attributes
from apps.analytics.tests.factories import PropertyListingFactory

pytestmark = pytest.mark.django_db

ZONES_GET = 'apps.analytics.services.flood_zones.requests.get'
CLAIMS_GET = 'apps.analytics.services.flood_claims.requests.get'


def _square(west, south, size=0.01, **attributes):
    """A GeoJSON feature the way the NFHL service returns one."""
    east, north = west + size, south + size
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    properties = {'FLD_ZONE': 'X', 'ZONE_SUBTY': 'AREA OF MINIMAL FLOOD HAZARD', 'STATIC_BFE': -9999, **attributes}
    return {'type': 'Feature', 'properties': properties, 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}


# Three squares side by side along latitude 27.90, and a VE square on top of the AE one.
FEATURES = [
    _square(-82.80, 27.90, FLD_ZONE='AE', ZONE_SUBTY='COASTAL FLOODPLAIN', STATIC_BFE=10),
    _square(-82.80, 27.90, size=0.005, FLD_ZONE='VE', ZONE_SUBTY='COASTAL FLOODPLAIN', STATIC_BFE=12.5),
    _square(-82.79, 27.90, ZONE_SUBTY='0.2 PCT ANNUAL CHANCE FLOOD HAZARD IN COASTAL ZONE'),
    _square(-82.78, 27.90),
]
IN_VE = (-82.798, 27.902)
IN_AE = (-82.792, 27.908)
IN_SHADED_X = (-82.785, 27.905)
IN_X = (-82.775, 27.905)
NOWHERE = (-82.50, 27.50)


def _json_response(payload):
    return Mock(status_code=200, json=Mock(return_value=payload), raise_for_status=Mock())


def _parcel(parcel_id, point, **fields):
    listing = PropertyListingFactory(parcel_id=parcel_id)
    longitude, latitude = point if point else (None, None)
    PropertyListing.objects.filter(pk=listing.pk).update(longitude=longitude, latitude=latitude, **fields)
    return listing


def _zone(parcel_id):
    return PropertyListing.objects.values_list('flood_zone', 'static_bfe').get(parcel_id=parcel_id)


class TestZoneFromAttributes:
    def test_special_flood_hazard_area_keeps_its_base_flood_elevation(self):
        assert zone_from_attributes({'FLD_ZONE': 'AE', 'STATIC_BFE': 10}) == FloodZone('AE', Decimal('10.0'))
        assert zone_from_attributes({'FLD_ZONE': 'VE', 'STATIC_BFE': 12.5}).bfe == Decimal('12.5')

    def test_placeholder_elevation_is_dropped(self):
        assert zone_from_attributes({'FLD_ZONE': 'A', 'STATIC_BFE': -9999}) == FloodZone('A', None)
        assert zone_from_attributes({'FLD_ZONE': 'A', 'STATIC_BFE': None}) == FloodZone('A', None)

    def test_shaded_x_is_told_apart_from_minimal_risk(self):
        shaded = {'FLD_ZONE': 'X', 'ZONE_SUBTY': '0.2 PCT ANNUAL CHANCE FLOOD HAZARD'}
        minimal = {'FLD_ZONE': 'X', 'ZONE_SUBTY': 'AREA OF MINIMAL FLOOD HAZARD'}

        assert zone_from_attributes(shaded).zone == 'X500'
        assert zone_from_attributes(minimal).zone == 'X'

    def test_polygon_without_a_zone_is_skipped(self):
        assert zone_from_attributes({'FLD_ZONE': None}) is None


class TestDownloadFloodPolygons:
    def test_pages_until_the_service_stops_reporting_more(self, tmp_path):
        pages = [
            {'features': FEATURES[:2], 'exceededTransferLimit': True},
            {'features': FEATURES[2:]},
        ]
        dest = tmp_path / 'nfhl.geojson'

        with (
            patch(ZONES_GET, side_effect=[_json_response(page) for page in pages]) as get,
            patch.object(flood_zones, 'MIN_POLYGONS', 4),
        ):
            count = flood_zones.download_flood_polygons(str(dest))

        assert count == 4
        assert [call.kwargs['params']['resultOffset'] for call in get.call_args_list] == [0, 2]
        assert get.call_args.kwargs['params']['where'] == "DFIRM_ID='12103C'"
        assert len(json.loads(dest.read_text())['features']) == 4

    def test_short_download_is_refused_and_writes_nothing(self, tmp_path):
        dest = tmp_path / 'nfhl.geojson'

        with patch(ZONES_GET, return_value=_json_response({'features': FEATURES})), pytest.raises(RuntimeError):
            flood_zones.download_flood_polygons(str(dest))

        assert not dest.exists()

    def test_retries_then_gives_up_on_an_arcgis_error_body(self, tmp_path):
        error = _json_response({'error': {'code': 500, 'message': 'Error performing query operation'}})

        with (
            patch(ZONES_GET, return_value=error) as get,
            patch('apps.analytics.services.flood_zones.time.sleep'),
            pytest.raises(RuntimeError, match='Could not read flood zones'),
        ):
            flood_zones.download_flood_polygons(str(tmp_path / 'nfhl.geojson'))

        assert get.call_count == 3


class TestAssignFloodZones:
    """The point-in-polygon join. Needs shapely, which only the data jobs install."""

    @pytest.fixture(autouse=True)
    def _small_map(self):
        pytest.importorskip('shapely')
        with patch.object(flood_zones, 'MIN_POLYGONS', 4), patch.object(flood_zones, 'MIN_MATCHED_SHARE', 0.5):
            yield

    def _assign(self, features=FEATURES, **options):
        return flood_zones.assign_flood_zones(flood_zones.FloodZoneIndex(features), **options)

    def test_database_connection_is_released_before_the_join(self):
        """The join idles the database for minutes, long enough for Neon to drop the connection."""
        _parcel('ae', IN_AE)
        order = []
        locate = flood_zones.FloodZoneIndex.locate

        def record_locate(index, points):
            order.append('join')
            return locate(index, points)

        with (
            patch.object(flood_zones, 'release_database_connection', side_effect=lambda: order.append('release')),
            patch.object(flood_zones.FloodZoneIndex, 'locate', autospec=True, side_effect=record_locate),
        ):
            stats = self._assign()

        assert order == ['release', 'join']
        assert stats['updated'] == 1

    def test_each_parcel_gets_the_zone_its_point_falls_in(self):
        _parcel('ae', IN_AE)
        _parcel('shaded', IN_SHADED_X)
        _parcel('minimal', IN_X)

        stats = self._assign()

        assert _zone('ae') == ('AE', Decimal('10.0'))
        assert _zone('shaded') == ('X500', None)
        assert _zone('minimal') == ('X', None)
        assert stats == {'located': 3, 'matched': 3, 'updated': 3}

    def test_riskier_zone_wins_where_polygons_overlap(self):
        _parcel('coast', IN_VE)

        self._assign()

        assert _zone('coast') == ('VE', Decimal('12.5'))

    def test_parcel_without_coordinates_is_left_alone(self):
        _parcel('no-point', None, flood_zone='AE')
        _parcel('minimal', IN_X)

        stats = self._assign()

        assert _zone('no-point') == ('AE', None)
        assert stats['located'] == 1

    def test_parcel_outside_every_polygon_loses_a_stale_zone(self):
        _parcel('moved', NOWHERE, flood_zone='AE', static_bfe=Decimal('9.0'))
        _parcel('ae', IN_AE)
        _parcel('minimal', IN_X)

        self._assign()

        assert _zone('moved') == (None, None)

    def test_second_run_updates_nothing(self):
        _parcel('ae', IN_AE)
        _parcel('minimal', IN_X)
        self._assign()

        assert self._assign()['updated'] == 0

    def test_map_that_misses_most_parcels_is_refused(self):
        _parcel('ae', IN_AE, flood_zone='AE')
        _parcel('far-1', NOWHERE, flood_zone='X')
        _parcel('far-2', NOWHERE, flood_zone='X')

        with pytest.raises(RuntimeError, match='Only 1 of 3 parcels'):
            self._assign()

        assert _zone('far-1') == ('X', None)

    def test_too_few_polygons_is_refused(self):
        _parcel('ae', IN_AE, flood_zone='AE')

        with pytest.raises(RuntimeError, match='Only 1 flood zone polygons'):
            self._assign(features=FEATURES[3:])

        assert _zone('ae') == ('AE', None)


def _claim(zip_code='33708', year=2024, building=40000, contents=0, icc=0):
    return {
        'reportedZipCode': zip_code,
        'yearOfLoss': year,
        'amountPaidOnBuildingClaim': building,
        'amountPaidOnContentsClaim': contents,
        'amountPaidOnIncreasedCostOfComplianceClaim': icc,
    }


class TestSummarizeClaims:
    def test_counts_recent_claims_and_takes_the_median_of_paid_ones(self):
        claims = [
            _claim(year=1985, building=10000),
            _claim(year=2019, building=None, contents=None, icc=None),  # closed without payment
            _claim(year=2020, building=30000, contents=5000),
            _claim(year=2024, building=90000, icc=10000),
        ]

        (row,) = summarize_claims(claims)

        assert (row.zip_code, row.claim_count, row.recent_claim_count) == ('33708', 4, 2)
        assert row.median_paid == 35000

    def test_zip_with_no_paid_claim_has_no_median(self):
        (row,) = summarize_claims([_claim(building=0)])

        assert row.median_paid is None

    def test_zip_plus_four_is_folded_in_and_junk_is_dropped(self):
        rows = summarize_claims([_claim('33706'), _claim('33706-3139'), _claim(''), _claim(None), _claim('PINEL')])

        assert [(row.zip_code, row.claim_count) for row in rows] == [('33706', 2)]


class TestImportFloodClaims:
    def test_replaces_what_was_stored(self):
        ZipFloodHistory.objects.create(zip_code='33701', claim_count=1, recent_claim_count=0, median_paid=None)

        with patch.object(flood_claims, 'MIN_CLAIMS', 2):
            assert import_flood_claims([_claim(), _claim(year=1999)]) == 1

        assert list(ZipFloodHistory.objects.values_list('zip_code', 'claim_count', 'recent_claim_count')) == [
            ('33708', 2, 1)
        ]

    def test_short_download_keeps_what_was_stored(self):
        ZipFloodHistory.objects.create(zip_code='33701', claim_count=1, recent_claim_count=0, median_paid=None)

        with pytest.raises(RuntimeError, match='Only 1 flood claims'):
            import_flood_claims([_claim()])

        assert ZipFloodHistory.objects.filter(zip_code='33701').exists()

    def test_download_pages_until_a_short_page(self):
        pages = [{'NfipClaims': [_claim(), _claim()]}, {'NfipClaims': [_claim()]}]

        with (
            patch(CLAIMS_GET, side_effect=[_json_response(page) for page in pages]) as get,
            patch.object(flood_claims, 'PAGE_SIZE', 2),
        ):
            claims = flood_claims.download_claims()

        assert len(claims) == 3
        assert [call.kwargs['params']['$skip'] for call in get.call_args_list] == [0, 2]
        assert get.call_args.kwargs['params']['$filter'] == "countyCode eq '12103'"


class TestZipFloodHistoryLookup:
    def test_finds_the_parcels_zip(self):
        ZipFloodHistory.objects.create(zip_code='33708', claim_count=7626, recent_claim_count=5000, median_paid=41000)

        assert zip_flood_history('33708').claim_count == 7626
        assert zip_flood_history('33999') is None
        assert zip_flood_history(None) is None

    def test_missing_table_is_not_fatal(self):
        with patch.object(ZipFloodHistory.objects, 'filter', side_effect=DatabaseError('no such table')):
            assert zip_flood_history('33708') is None


class TestRefreshFloodDataCommand:
    def test_claims_still_load_when_fema_flood_map_is_down(self):
        _parcel('ae', IN_AE, flood_zone='AE')

        with (
            patch(ZONES_GET, side_effect=requests.ConnectionError('reset')),
            patch('apps.analytics.services.flood_zones.time.sleep'),
            patch(CLAIMS_GET, return_value=_json_response({'NfipClaims': [_claim(), _claim()]})),
            patch.object(flood_claims, 'MIN_CLAIMS', 2),
            pytest.raises(CommandError, match='flood zones'),
        ):
            call_command('refresh_flood_data')

        assert _zone('ae') == ('AE', None)
        assert ZipFloodHistory.objects.get(zip_code='33708').claim_count == 2

    def test_cached_polygons_are_used_without_a_download(self, tmp_path):
        pytest.importorskip('shapely')
        _parcel('ae', IN_AE)
        zones_file = tmp_path / 'nfhl.geojson'
        zones_file.write_text(json.dumps({'type': 'FeatureCollection', 'features': FEATURES}))

        with patch(ZONES_GET) as get, patch.object(flood_zones, 'MIN_POLYGONS', 4):
            call_command('refresh_flood_data', zones_file=str(zones_file), skip_claims=True)

        get.assert_not_called()
        assert _zone('ae') == ('AE', Decimal('10.0'))


class TestReleaseDatabaseConnection:
    def test_closes_an_idle_connection_so_the_next_query_reconnects(self):
        with patch.object(flood_zones, 'connection', Mock(in_atomic_block=False)) as connection:
            flood_zones.release_database_connection()

        connection.close.assert_called_once_with()

    def test_leaves_a_connection_that_is_inside_a_transaction(self):
        with patch.object(flood_zones, 'connection', Mock(in_atomic_block=True)) as connection:
            flood_zones.release_database_connection()

        connection.close.assert_not_called()
