"""
Import PCPAO bulk data into the database.

Usage:
    python manage.py import_pcpao_data
    python manage.py import_pcpao_data --file /path/to/RP_PROPERTY_INFO.csv
    python manage.py import_pcpao_data --quiet
"""

import codecs
import csv
import logging
import os
import tempfile

from django.core.management.base import BaseCommand

from apps.analytics.services.pcpao_importer import (
    bulk_upsert_properties,
    download_pcpao_file,
    map_csv_row_to_property,
    vacuum_property_listing_table,
)

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

    def handle(self, *args, **options):
        quiet = options['quiet']
        limit = options.get('limit')

        if not quiet:
            self.stdout.write('Starting PCPAO data import...')

        if options['vacuum_first']:
            if not quiet:
                self.stdout.write('Reclaiming reusable property-table space...')
            vacuum_property_listing_table()

        # Get CSV file path
        if options['file']:
            csv_path = options['file']
            if not os.path.exists(csv_path):
                self.stderr.write(f'File not found: {csv_path}')
                return
            self._process_csv(csv_path, quiet, limit)
        else:
            if not quiet:
                self.stdout.write('Downloading RP_PROPERTY_INFO.csv...')
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)
                self._process_csv(csv_path, quiet, limit)

    def _process_csv(self, csv_path: str, quiet: bool, limit: int = None):
        """Process CSV file and import records."""
        properties = []
        count = 0
        skipped = 0

        with open(csv_path, 'rb') as raw_file:
            has_utf8_bom = raw_file.read(len(codecs.BOM_UTF8)) == codecs.BOM_UTF8
        encoding = 'utf-8-sig' if has_utf8_bom else 'cp1252'

        with open(csv_path, encoding=encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                prop = map_csv_row_to_property(row)
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

        # Process remaining records
        if properties:
            stats = bulk_upsert_properties(properties)
            if not quiet:
                self.stdout.write(
                    f'Processed {count} records (created: {stats["created"]}, updated: {stats["updated"]})'
                )

        if not quiet:
            self.stdout.write(self.style.SUCCESS(f'Import complete. Total records: {count}'))
