"""
Store each parcel's FEMA flood zone and each ZIP code's flood-claim history.

Usage:
    python manage.py refresh_flood_data
    python manage.py refresh_flood_data --zones-file nfhl-pinellas.geojson
    python manage.py refresh_flood_data --skip-claims --vacuum-every 10

Needs shapely (requirements-data.txt) unless --skip-zones is given. With
--zones-file, FEMA's polygons are downloaded to that path only if it doesn't
exist yet, so a cached copy is reused.

The two halves are independent: if one fails, the other still runs, what is
already stored for the failed half is kept, and the command exits non-zero.
"""

import logging
import os
import tempfile

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from apps.analytics.services.flood_claims import download_claims, import_flood_claims
from apps.analytics.services.flood_zones import FloodZoneIndex, assign_flood_zones, download_flood_polygons

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fetch FEMA flood zones and flood-insurance claim history'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zones-file',
            type=str,
            help='Path to the flood zone GeoJSON; downloaded there if the file does not exist',
        )
        parser.add_argument('--skip-zones', action='store_true', help='Leave parcel flood zones as they are')
        parser.add_argument('--skip-claims', action='store_true', help='Leave ZIP claim history as it is')
        parser.add_argument(
            '--vacuum-every',
            type=int,
            metavar='N',
            help=(
                'Vacuum the property table after every N batches of 5000 updated rows, so the first '
                'run, which writes a zone on almost every row, reuses dead-row space'
            ),
        )

    def handle(self, *args, **options):
        failed = []
        if not options['skip_zones']:
            try:
                self._refresh_zones(options.get('zones_file'), options.get('vacuum_every'))
            except Exception:
                logger.exception('Could not refresh flood zones')
                failed.append('flood zones')
        if not options['skip_claims']:
            try:
                count = import_flood_claims(download_claims())
                self.stdout.write(f'Stored flood claim history for {count} ZIP codes.')
            except Exception:
                logger.exception('Could not refresh flood claim history')
                failed.append('flood claim history')

        # Cached market insights may be filtered on the old zones.
        try:
            cache.clear()
        except Exception:
            logger.warning('Could not clear the cache after the flood refresh', exc_info=True)

        if failed:
            raise CommandError(f'Could not refresh {" or ".join(failed)}; what was stored before is kept.')

    def _refresh_zones(self, zones_file: str | None, vacuum_every: int | None) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = zones_file or os.path.join(tmpdir, 'nfhl.geojson')
            if os.path.exists(path):
                self.stdout.write(f'Using flood zone polygons from {path}.')
            else:
                self.stdout.write('Downloading flood zone polygons from FEMA...')
                download_flood_polygons(path)
            index = FloodZoneIndex.from_file(path)
            stats = assign_flood_zones(index, vacuum_every=vacuum_every)
        self.stdout.write(
            f'Flood zones: {stats["matched"]} of {stats["located"]} parcels matched, {stats["updated"]} updated.'
        )
