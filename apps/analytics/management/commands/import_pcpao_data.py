"""
Import PCPAO bulk data into the database.

Usage:
    python manage.py import_pcpao_data
    python manage.py import_pcpao_data --file /path/to/RP_PROPERTY_INFO.csv
    python manage.py import_pcpao_data --file RP_PROPERTY_INFO.csv --millage-file RP_MILLAGE_RATES.csv
    python manage.py import_pcpao_data --file RP_PROPERTY_INFO.csv --sales-file RP_SALES.csv
    python manage.py import_pcpao_data --file RP_PROPERTY_INFO.csv --permits-file RP_PERMITS.csv
    python manage.py import_pcpao_data --quiet
    python manage.py import_pcpao_data --vacuum-every 10
"""

import csv
import logging
import os
import tempfile

from django.core.cache import cache
from django.core.management.base import BaseCommand

from apps.analytics.services.pcpao_importer import (
    bulk_upsert_properties,
    csv_encoding,
    download_pcpao_file,
    import_millage_rates,
    map_csv_row_to_property,
    stored_millage,
    vacuum_property_listing_table,
)
from apps.analytics.services.permits_importer import PERMITS_TABLE, PermitYears, read_permit_years
from apps.analytics.services.sales_importer import SALES_TABLE, import_sales
from apps.analytics.services.street_names import rebuild_street_names
from apps.analytics.services.tax_estimate import Millage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import property data from PCPAO bulk CSV files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Path to local CSV file (skips download)',
        )
        parser.add_argument(
            '--millage-file',
            type=str,
            help=(
                'Path to a local RP_MILLAGE_RATES CSV for tax estimates. With --file and no '
                '--millage-file, the millage already in the database is used.'
            ),
        )
        parser.add_argument(
            '--sales-file',
            type=str,
            help=(
                'Path to a local RP_SALES CSV for sales history and comparable sales. With --file '
                'and no --sales-file, the sales already in the database are kept.'
            ),
        )
        parser.add_argument(
            '--permits-file',
            type=str,
            help=(
                'Path to a local RP_PERMITS CSV for roof and heating/air permit years. With --file '
                'and no --permits-file, the permit years already in the database are kept.'
            ),
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress progress output',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of records to import (for testing)',
        )
        parser.add_argument(
            '--vacuum-first',
            action='store_true',
            help='Reclaim reusable PostgreSQL row space before importing',
        )
        parser.add_argument(
            '--vacuum-every',
            type=int,
            metavar='N',
            help=(
                'Vacuum the property table after every N batches of 5000 rows, so a backfill '
                'that rewrites every row reuses dead-row space instead of growing the table'
            ),
        )

    def handle(self, *args, **options):
        quiet = options['quiet']
        limit = options.get('limit')
        vacuum_every = options.get('vacuum_every')

        if not quiet:
            self.stdout.write('Starting PCPAO data import...')

        if options['vacuum_first']:
            if not quiet:
                self.stdout.write('Reclaiming reusable property-table space...')
            vacuum_property_listing_table()

        # Get CSV file path
        if options['file']:
            csv_path = options['file']
            millage_path = options.get('millage_file')
            sales_path = options.get('sales_file')
            permits_path = options.get('permits_file')
            for path in (csv_path, millage_path, sales_path, permits_path):
                if path and not os.path.exists(path):
                    self.stderr.write(f'File not found: {path}')
                    return
            millage = import_millage_rates(millage_path) if millage_path else stored_millage()
            permits = read_permit_years(permits_path) if permits_path else None
            self._process_csv(csv_path, quiet, limit, vacuum_every, self._millage_or_none(millage, quiet), permits)
            self._rebuild_street_names(quiet)
            self._clear_cache()
            if sales_path:
                self._import_sales(sales_path, quiet)
        else:
            if not quiet:
                self.stdout.write(f'Downloading RP_MILLAGE_RATES.csv, {PERMITS_TABLE}.csv and RP_PROPERTY_INFO.csv...')
            with tempfile.TemporaryDirectory() as tmpdir:
                millage = import_millage_rates(download_pcpao_file('RP_MILLAGE_RATES', tmpdir))
                permits = self._download_permit_years(tmpdir, quiet)
                csv_path = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)
                self._process_csv(csv_path, quiet, limit, vacuum_every, self._millage_or_none(millage, quiet), permits)
                self._rebuild_street_names(quiet)
                self._clear_cache()
                # Last, so a problem with the sales file can't cost the property refresh.
                if not quiet:
                    self.stdout.write(f'Downloading {SALES_TABLE}.csv...')
                self._import_sales(download_pcpao_file(SALES_TABLE, tmpdir), quiet)

    def _clear_cache(self) -> None:
        # Cached market insights describe the old data. They live for a day
        # to save database egress, so drop them now rather than serve them.
        try:
            cache.clear()
        except Exception:
            logger.warning('Could not clear the cache after the import', exc_info=True)

    def _rebuild_street_names(self, quiet: bool) -> None:
        # Only the spelling suggestions depend on this, so a failure here
        # must not cost the property refresh.
        try:
            count = rebuild_street_names()
        except Exception:
            logger.exception('Could not rebuild street names; keeping the ones already loaded')
            return
        if not quiet:
            self.stdout.write(f'Rebuilt {count} street names.')

    def _import_sales(self, sales_path: str, quiet: bool) -> None:
        count = import_sales(sales_path)
        if not quiet:
            self.stdout.write(self.style.SUCCESS(f'Loaded {count} qualified sales.'))

    def _download_permit_years(self, tmpdir: str, quiet: bool) -> dict[str, PermitYears] | None:
        # Permit years ride along on the property rows, so the file has to be
        # read first. A problem with it must not cost the property refresh:
        # None keeps the years already stored.
        try:
            return read_permit_years(download_pcpao_file(PERMITS_TABLE, tmpdir))
        except Exception:
            logger.exception('Could not read %s; keeping the permit years already loaded', PERMITS_TABLE)
            if not quiet:
                self.stdout.write(self.style.WARNING(f'Could not read {PERMITS_TABLE}; keeping existing permit years.'))
            return None

    def _millage_or_none(self, millage: dict[str, Millage], quiet: bool) -> dict[str, Millage] | None:
        if millage:
            return millage
        if not quiet:
            self.stdout.write('No millage rates loaded; keeping existing tax estimates.')
        return None

    def _process_csv(
        self,
        csv_path: str,
        quiet: bool,
        limit: int = None,
        vacuum_every: int = None,
        millage: dict[str, Millage] | None = None,
        permits: dict[str, PermitYears] | None = None,
    ):
        """Process CSV file and import records."""
        properties = []
        count = 0
        skipped = 0
        batches = 0

        with open(csv_path, encoding=csv_encoding(csv_path)) as f:
            reader = csv.DictReader(f)
            for row in reader:
                prop = map_csv_row_to_property(row, millage, permits)
                # Need parcel_id plus required/search-critical address fields.
                # Vacant/orphan parcels with incomplete site data are skipped.
                if not (prop.get('parcel_id') and prop.get('address') and prop.get('city') and prop.get('zip_code')):
                    skipped += 1
                    continue

                properties.append(prop)
                count += 1

                if limit and count >= limit:
                    break

                # Process in batches of 5000
                if len(properties) >= 5000:
                    stats = bulk_upsert_properties(properties)
                    if not quiet:
                        self.stdout.write(
                            f'Processed {count} records '
                            f'(created: {stats["created"]}, updated: {stats["updated"]}, '
                            f'skipped so far: {skipped})'
                        )
                    properties = []
                    batches += 1
                    if vacuum_every and batches % vacuum_every == 0:
                        vacuum_property_listing_table()

        # Process remaining records
        if properties:
            stats = bulk_upsert_properties(properties)
            if not quiet:
                self.stdout.write(
                    f'Processed {count} records (created: {stats["created"]}, updated: {stats["updated"]})'
                )

        if not quiet:
            self.stdout.write(self.style.SUCCESS(f'Import complete. Total records: {count}'))
