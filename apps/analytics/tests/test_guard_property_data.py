from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db

IMPORTER = 'apps.analytics.management.commands.guard_property_data.call_command'


class TestGuardPropertyData:
    def test_does_nothing_when_data_is_present(self, sample_property):
        with patch(IMPORTER) as importer:
            call_command('guard_property_data')

        importer.assert_not_called()

    def test_rebuilds_then_fails_when_the_table_is_empty(self, db):
        """The rebuild must happen before the failure, or the site stays down."""
        with patch(IMPORTER) as importer, pytest.raises(CommandError, match='has been rebuilt'):
            call_command('guard_property_data')

        importer.assert_called_once_with('import_pcpao_data')
