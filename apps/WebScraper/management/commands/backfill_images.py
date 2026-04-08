"""Backfill missing property images using Google Street View API."""

import logging
import time

from django.core.management.base import BaseCommand
from apps.WebScraper.models import PropertyListing
from apps.WebScraper.services.street_view import get_street_view_url

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill missing property images using Google Street View API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Max properties to process (0 = all)',
        )
        parser.add_argument(
            '--delay', type=float, default=0.2,
            help='Delay between API calls in seconds (default: 0.2)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be updated without saving',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        delay = options['delay']
        dry_run = options['dry_run']

        properties = PropertyListing.objects.filter(
            image_url__isnull=True,
            address__isnull=False,
        ).exclude(address='')

        total = properties.count()
        if limit:
            properties = properties[:limit]
            count = min(limit, total)
        else:
            count = total

        self.stdout.write(f"Found {total} properties without images, processing {count}...")

        updated = 0
        skipped = 0

        for i, prop in enumerate(properties, 1):
            url = get_street_view_url(
                address=prop.address,
                city=prop.city,
                zip_code=prop.zip_code,
            )

            if url:
                if dry_run:
                    self.stdout.write(f"  [{i}/{count}] Would set image for {prop.parcel_id}: {prop.address}")
                else:
                    prop.image_url = url
                    prop.save(update_fields=['image_url'])
                updated += 1
            else:
                skipped += 1

            if i % 50 == 0:
                self.stdout.write(f"  Progress: {i}/{count} ({updated} found, {skipped} no imagery)")

            if delay and i < count:
                time.sleep(delay)

        action = "Would update" if dry_run else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"{action} {updated} properties with images ({skipped} had no Street View imagery)"
        ))
