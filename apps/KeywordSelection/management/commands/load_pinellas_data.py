from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Load initial Pinellas County keyword data'

    def handle(self, *args, **options):
        self.stdout.write('Loading Pinellas County keyword data...')

        try:
            call_command('loaddata', 'pinellas_county_data.json')
            self.stdout.write(self.style.SUCCESS('Successfully loaded Pinellas County data'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error loading data: {e}'))