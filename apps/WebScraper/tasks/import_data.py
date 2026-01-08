"""
Celery tasks for scheduled data imports.

Usage:
    # Run manually
    from apps.WebScraper.tasks.import_data import import_pcpao_data_task
    import_pcpao_data_task.delay()

    # Schedule in Celery Beat (celeryconfig.py):
    # CELERYBEAT_SCHEDULE = {
    #     'import-pcpao-daily': {
    #         'task': 'apps.WebScraper.tasks.import_data.import_pcpao_data_task',
    #         'schedule': crontab(hour=2, minute=0),
    #     },
    # }
"""
import tempfile
import logging
import csv
from celery import shared_task
from apps.WebScraper.services.pcpao_importer import (
    download_pcpao_file,
    map_csv_row_to_property,
    bulk_upsert_properties,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def import_pcpao_data_task(self):
    """
    Download and import PCPAO data.

    This task can be scheduled to run daily via Celery Beat.
    """
    logger.info('Starting scheduled PCPAO data import')

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)

        properties = []
        total_created = 0
        total_updated = 0
        count = 0

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                prop = map_csv_row_to_property(row)
                if prop.get('parcel_id'):
                    properties.append(prop)
                    count += 1

                    if len(properties) >= 5000:
                        stats = bulk_upsert_properties(properties)
                        total_created += stats['created']
                        total_updated += stats['updated']
                        properties = []

                        # Update task progress
                        self.update_state(
                            state='PROGRESS',
                            meta={'current': count, 'created': total_created, 'updated': total_updated}
                        )

        if properties:
            stats = bulk_upsert_properties(properties)
            total_created += stats['created']
            total_updated += stats['updated']

    logger.info(f'Import complete: {count} records ({total_created} created, {total_updated} updated)')

    return {
        'total': count,
        'created': total_created,
        'updated': total_updated,
    }
