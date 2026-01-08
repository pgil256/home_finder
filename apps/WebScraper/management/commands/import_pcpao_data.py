"""
Import PCPAO bulk data into the database.

Usage:
    python manage.py import_pcpao_data
    python manage.py import_pcpao_data --file /path/to/RP_PROPERTY_INFO.csv
    python manage.py import_pcpao_data --quiet
"""
import os
import csv
import tempfile
import logging
from django.core.management.base import BaseCommand
from apps.WebScraper.services.pcpao_importer import (
    download_pcpao_file,
    map_csv_row_to_property,
    bulk_upsert_properties,
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

    def handle(self, *args, **options):
        quiet = options['quiet']
        limit = options.get('limit')

        if not quiet:
            self.stdout.write('Starting PCPAO data import...')

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

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                prop = map_csv_row_to_property(row)
                if prop.get('parcel_id'):
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
                                f'(created: {stats["created"]}, updated: {stats["updated"]})'
                            )
                        properties = []

        # Process remaining records
        if properties:
            stats = bulk_upsert_properties(properties)
            if not quiet:
                self.stdout.write(
                    f'Processed {count} records '
                    f'(created: {stats["created"]}, updated: {stats["updated"]})'
                )

        if not quiet:
            self.stdout.write(self.style.SUCCESS(f'Import complete. Total records: {count}'))
