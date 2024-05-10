from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Keyword
import json
import os

class Command(BaseCommand):
    help = 'Loads initial keyword data into the database'

    def handle(self, *args, **options):
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(os.path.dirname(current_script_dir))
        data_file_path = os.path.join(app_dir, 'data', 'initial_data.json')

        try:
            with open(data_file_path, 'r') as file:
                data = json.load(file)
                with transaction.atomic():
                    for item in data:
                        keyword, created = Keyword.objects.update_or_create(
                            name=item['name'],
                            defaults={
                                'data_type': item['data_type'],
                                'help_text': item['help_text'],
                                'extra_json': item['extra_json'] if 'extra_json' in item else {}
                            }
                        )
            self.stdout.write(self.style.SUCCESS('Successfully loaded initial data!'))
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f'File not found: {data_file_path}'))
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR('Invalid JSON format in data file.'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'An error occurred: {str(e)}'))
