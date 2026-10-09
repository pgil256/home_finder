"""
Rebuild the street-name table that typo-tolerant address lookup reads.

Usage:
    python manage.py rebuild_street_names

The monthly import runs this itself, and the daily database guard runs it
when the table is empty. On Postgres it is one statement inside the database
and reads no rows out of it. It prints the table's size so the scheduled
job's log shows what the feature costs in storage.
"""

from django.core.management.base import BaseCommand
from django.db import connection

from apps.analytics.models import StreetName
from apps.analytics.services.street_names import rebuild_street_names


class Command(BaseCommand):
    help = 'Rebuild the street names used to correct mistyped addresses'

    def handle(self, *args, **options):
        count = rebuild_street_names()
        self.stdout.write(self.style.SUCCESS(f'Street names rebuilt: {count} rows{self._size()}.'))

    def _size(self) -> str:
        if connection.vendor != 'postgresql':
            return ''
        # Quoted, because the table name has capitals in it.
        table = connection.ops.quote_name(StreetName._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_total_relation_size(%s), pg_indexes_size(%s)', [table, table])
            total, indexes = cursor.fetchone()
        return f', {total / 1024 / 1024:.2f} MB with indexes ({indexes / 1024 / 1024:.2f} MB of it indexes)'
