from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.analytics.models import StreetName

pytestmark = pytest.mark.django_db

IMPORTER = 'apps.analytics.management.commands.guard_property_data.call_command'


class TestGuardPropertyData:
    def test_does_nothing_when_data_is_present(self, sample_property):
        StreetName.objects.create(name='MAIN ST', city='Clearwater', parcel_count=1)
        with patch(IMPORTER) as importer:
            call_command('guard_property_data')

        importer.assert_not_called()

    def test_fills_empty_street_names_without_failing(self, sample_property):
        """How the table gets its first rows after the migration that adds it."""
        call_command('guard_property_data')

        assert list(StreetName.objects.values_list('name', 'city', 'parcel_count')) == [('Main St', 'Clearwater', 1)]

    def test_rebuilds_then_fails_when_the_table_is_empty(self, db):
        """The rebuild must happen before the failure, or the site stays down."""
        with patch(IMPORTER) as importer, pytest.raises(CommandError, match='has been rebuilt'):
            call_command('guard_property_data')

        importer.assert_called_once_with('import_pcpao_data')
