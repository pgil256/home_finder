"""
FEMA flood zones for parcels

Reads the flood hazard polygons for Pinellas County from FEMA's National Flood
Hazard Layer (NFHL, layer 28 "Flood Hazard Zones" of the public ArcGIS
service) and finds the one each parcel's county map point falls in. As
downloaded in October 2026 the county's map (DFIRM_ID 12103C) has 5,253
polygons, about 30 MB as GeoJSON:

  - FLD_ZONE: AE (969 polygons), VE (267), A (79), AO (6) and AH (6) are
    Special Flood Hazard Areas; X (3,922) is not; 4 are OPEN WATER.
  - ZONE_SUBTY: splits X into "0.2 PCT ANNUAL CHANCE FLOOD HAZARD" (2,256,
    the shaded X of a paper map, stored here as X500) and "AREA OF MINIMAL
    FLOOD HAZARD" (1,666).
  - STATIC_BFE: base flood elevation in feet, -9999 where the zone has none.

Matched against the county file the same month, all but one of 437,196
parcels with coordinates fell in a polygon: 59% in X, 9% in shaded X, 30% in
AE, 1.2% in A and 0.7% in VE, so just under a third are in a Special Flood
Hazard Area. The join took about three minutes.

The join needs shapely, which is installed only where the refresh runs
(requirements-data.txt), so it is imported inside the functions that use it.
Nothing here runs in a web request.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import NamedTuple

import requests

from apps.analytics.models import PropertyListing
from apps.analytics.services.pcpao_importer import vacuum_property_listing_table

logger = logging.getLogger(__name__)

NFHL_QUERY_URL = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query'
PINELLAS_DFIRM_ID = '12103C'
NFHL_FIELDS = 'FLD_ZONE,ZONE_SUBTY,STATIC_BFE'
# The service allows more, but a page of 500 is already about 3 MB.
PAGE_SIZE = 500
_ATTEMPTS = 3
_NO_VALUE = -9999

SHADED_X = 'X500'
MINIMAL_RISK = 'X'
# Special Flood Hazard Areas: a 1% chance of flooding in any year. A federally
# backed mortgage on a building in one requires flood insurance.
SFHA_ZONES = ('A', 'AE', 'AH', 'AO', 'A99', 'AR', 'V', 'VE')
COASTAL_ZONES = ('V', 'VE')
OUTSIDE_SFHA_ZONES = (MINIMAL_RISK, SHADED_X)

# Fewer polygons or matches than this means a broken download or a changed
# service, not a new map. Nothing is written.
MIN_POLYGONS = 1000
MIN_MATCHED_SHARE = 0.9


class FloodZone(NamedTuple):
    zone: str
    bfe: Decimal | None = None


def zone_from_attributes(attributes: dict) -> FloodZone | None:
    """The stored zone for one NFHL polygon's attributes, or None if it names no zone."""
    zone = (attributes.get('FLD_ZONE') or '').strip().upper()
    if not zone:
        return None
    if zone == MINIMAL_RISK and (attributes.get('ZONE_SUBTY') or '').strip().upper().startswith('0.2 PCT'):
        zone = SHADED_X
    bfe = attributes.get('STATIC_BFE')
    if bfe is None or bfe <= 0 or bfe == _NO_VALUE:
        return FloodZone(zone)
    return FloodZone(zone, Decimal(str(bfe)).quantize(Decimal('0.1')))


def _severity(flood_zone: FloodZone) -> int:
    """Where two polygons meet on a parcel's point, the riskier zone wins."""
    if flood_zone.zone in COASTAL_ZONES:
        return 3
    if flood_zone.zone in SFHA_ZONES:
        return 2
    return 1 if flood_zone.zone == SHADED_X else 0


def _fetch_page(offset: int) -> dict:
    params = {
        'where': f"DFIRM_ID='{PINELLAS_DFIRM_ID}'",
        'outFields': NFHL_FIELDS,
        'orderByFields': 'OBJECTID',
        'resultOffset': offset,
        'resultRecordCount': PAGE_SIZE,
        'outSR': 4326,
        'geometryPrecision': 6,
        'f': 'geojson',
    }
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            response = requests.get(NFHL_QUERY_URL, params=params, timeout=180)
            response.raise_for_status()
            page = response.json()
            # ArcGIS reports its own errors as a 200 with an "error" object.
            if 'features' not in page:
                raise ValueError(f'no features in the response: {str(page)[:200]}')
            return page
        except (requests.RequestException, ValueError) as error:
            if attempt == _ATTEMPTS:
                raise RuntimeError(f'Could not read flood zones from FEMA at offset {offset}: {error}') from error
            logger.warning('FEMA flood zone request failed at offset %d (%s); retrying', offset, error)
            time.sleep(10 * attempt)
    raise AssertionError('unreachable')


def download_flood_polygons(dest_path: str) -> int:
    """Save every Pinellas flood hazard polygon as one GeoJSON file; returns how many."""
    features: list[dict] = []
    while True:
        page = _fetch_page(len(features))
        features.extend(page['features'])
        if not page['features'] or not page.get('exceededTransferLimit'):
            break
    if len(features) < MIN_POLYGONS:
        raise RuntimeError(f'FEMA returned only {len(features)} flood zone polygons; expected over {MIN_POLYGONS}.')
    with open(dest_path, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f)
    logger.info('Downloaded %d flood zone polygons', len(features))
    return len(features)


class FloodZoneIndex:
    """Flood hazard polygons, searchable by point."""

    def __init__(self, features: list[dict]):
        from shapely import STRtree, make_valid
        from shapely.geometry import shape

        self.zones: list[FloodZone] = []
        geometries = []
        for feature in features:
            flood_zone = zone_from_attributes(feature.get('properties') or {})
            if flood_zone is None or not feature.get('geometry'):
                continue
            geometry = shape(feature['geometry'])
            geometries.append(geometry if geometry.is_valid else make_valid(geometry))
            self.zones.append(flood_zone)
        self._tree = STRtree(geometries)

    @classmethod
    def from_file(cls, geojson_path: str) -> FloodZoneIndex:
        with open(geojson_path, encoding='utf-8') as f:
            return cls(json.load(f)['features'])

    def __len__(self) -> int:
        return len(self.zones)

    def locate(self, coordinates: list[tuple[float, float]]) -> list[FloodZone | None]:
        """The zone containing each (longitude, latitude), or None where there is none."""
        import shapely

        found: list[FloodZone | None] = [None] * len(coordinates)
        if not coordinates or not self.zones:
            return found
        points = shapely.points(coordinates)
        point_indexes, polygon_indexes = self._tree.query(points, predicate='intersects')
        for point_index, polygon_index in zip(point_indexes.tolist(), polygon_indexes.tolist(), strict=True):
            candidate = self.zones[polygon_index]
            current = found[point_index]
            if current is None or _severity(candidate) > _severity(current):
                found[point_index] = candidate
        return found


def assign_flood_zones(
    index: FloodZoneIndex, batch_size: int = 5000, vacuum_every: int | None = None
) -> dict[str, int]:
    """Write `flood_zone` and `static_bfe` on every parcel whose zone changed.

    Rows that already hold the right zone are not touched: PostgreSQL keeps
    the old version of every updated row, and the first run updates most of
    the table, so `vacuum_every` (in batches) lets later batches reuse that
    space. Returns counts of parcels 'located', 'matched' and 'updated'.
    """
    if len(index) < MIN_POLYGONS:
        raise RuntimeError(f'Only {len(index)} flood zone polygons loaded; keeping the flood zones already stored.')

    rows = list(
        PropertyListing.objects.filter(latitude__isnull=False, longitude__isnull=False).values_list(
            'pk', 'longitude', 'latitude', 'flood_zone', 'static_bfe'
        )
    )
    found = index.locate([(float(longitude), float(latitude)) for _, longitude, latitude, _, _ in rows])
    matched = sum(1 for flood_zone in found if flood_zone is not None)
    if rows and matched < MIN_MATCHED_SHARE * len(rows):
        raise RuntimeError(
            f'Only {matched} of {len(rows)} parcels fall in a flood zone polygon; '
            'keeping the flood zones already stored.'
        )

    # A parcel outside every polygon loses a zone stored by an earlier run.
    changes: dict[FloodZone, list[int]] = defaultdict(list)
    for (pk, _, _, stored_zone, stored_bfe), flood_zone in zip(rows, found, strict=True):
        flood_zone = flood_zone or FloodZone(None)
        if (stored_zone, stored_bfe) != flood_zone:
            changes[flood_zone].append(pk)

    updated = 0
    batches = 0
    for flood_zone, pks in changes.items():
        for start in range(0, len(pks), batch_size):
            updated += PropertyListing.objects.filter(pk__in=pks[start : start + batch_size]).update(
                flood_zone=flood_zone.zone, static_bfe=flood_zone.bfe
            )
            batches += 1
            if vacuum_every and batches % vacuum_every == 0:
                vacuum_property_listing_table()

    logger.info('Flood zones: %d parcels located, %d matched, %d updated', len(rows), matched, updated)
    return {'located': len(rows), 'matched': matched, 'updated': updated}
