"""
Rebuild the property data if the table is empty.

On 2026-10-02 every table in the production database disappeared with no
operation logged by the host and no job of ours running. The site returned
errors until a refresh was run by hand. This command is the daily check for
that: it costs one small query when the data is there.

Usage:
    python manage.py migrate --noinput && python manage.py guard_property_data

Run migrate first so the tables exist. Exits non-zero after a rebuild, so
the scheduled job fails and someone looks into what emptied the database.

It also fills the street-name table when that alone is empty, which is how
the table gets its first rows after the migration that creates it. That is
routine, cheap, and does not fail the job.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import PropertyListing, StreetName


class Command(BaseCommand):
    help = 'Re-import the county data if the property table is empty'

    def handle(self, *args, **options):
        if PropertyListing.objects.exists():
            self.stdout.write('Property data is present.')
            # The import fills this, but a migration that adds the table
            # shouldn't have to wait a month (or cost a full import) for it.
            if not StreetName.objects.exists():
                call_command('rebuild_street_names')
            return

        self.stderr.write('The property table is empty; rebuilding from PCPAO.')
        call_command('import_pcpao_data')
        raise CommandError('The property table was empty and has been rebuilt. Find out what emptied it.')
