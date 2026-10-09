import csv
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.analytics.models import PropertyListing, Sale
from apps.analytics.services.pcpao_importer import map_csv_row_to_property
from apps.analytics.services.permits_importer import PermitYears, read_permit_years

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures'
SAMPLE_PROPERTIES = FIXTURES / 'sample_pcpao_data.csv'
SAMPLE_PERMITS = FIXTURES / 'sample_permits.csv'

PARCEL = '15-29-16-00000-000-0001'
SAMPLE_PARCEL = '01-27-15-00864-002-0310'
TODAY = date(2026, 10, 8)

PERMIT_COLUMNS = [
    'STRAP',
    'PARCEL_NUMBER',
    'PERMIT_NUMBER',
    'PERMIT_TYPE',
    'PERMIT_DSCR',
    'AGENCY_ID',
    'AGENCY_NAME',
    'ISSUE_DT',
    'SIGN_OFF_DT',
    'EST_VAL',
    'PERMIT_YEAR',
]


def _permits_csv(tmp_path, *rows):
    """An RP_PERMITS file; each row overrides a 2019 roof permit on PARCEL."""
    defaults = {
        'PARCEL_NUMBER': PARCEL,
        'PERMIT_TYPE': '96',
        'PERMIT_DSCR': 'ROOF',
        'AGENCY_NAME': 'County',
        'ISSUE_DT': '2019-03-31 00:00:00',
        'EST_VAL': '12000',
        'PERMIT_YEAR': '2020',
    }
    path = tmp_path / 'RP_PERMITS.csv'
    with path.open('w', encoding='cp1252', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=PERMIT_COLUMNS, restval='', quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows({**defaults, **row} for row in rows)
    return str(path)


def _import_sample(**options):
    call_command('import_pcpao_data', file=str(SAMPLE_PROPERTIES), quiet=True, **options)


class TestReadPermitYears:
    def test_keeps_the_latest_year_of_each_kind(self, tmp_path):
        path = _permits_csv(
            tmp_path,
            {'ISSUE_DT': '2004-09-30 00:00:00'},
            {},
            {'ISSUE_DT': '2011-01-05 00:00:00'},
            {'PERMIT_DSCR': 'HEAT/AIR', 'ISSUE_DT': '2022-07-01 00:00:00'},
            {'PERMIT_DSCR': 'HEAT/AIR', 'ISSUE_DT': '2015-07-01 00:00:00'},
        )

        assert read_permit_years(path, TODAY) == {PARCEL: PermitYears(roof=2019, hvac=2022)}

    def test_other_kinds_of_permit_are_ignored(self, tmp_path):
        path = _permits_csv(
            tmp_path,
            {},
            {'PARCEL_NUMBER': 'pool', 'PERMIT_DSCR': 'POOL'},
            {'PARCEL_NUMBER': 'solar', 'PERMIT_DSCR': 'SOLAR PANELS'},
            {'PARCEL_NUMBER': 'air', 'PERMIT_DSCR': 'HEAT/AIR'},
        )

        assert read_permit_years(path, TODAY) == {PARCEL: PermitYears(roof=2019), 'air': PermitYears(hvac=2019)}

    def test_uses_the_issue_date_not_the_assessment_year(self, tmp_path):
        path = _permits_csv(tmp_path, {'ISSUE_DT': '2000-03-31 00:00:00', 'PERMIT_YEAR': '2001'})

        assert read_permit_years(path, TODAY)[PARCEL].roof == 2000

    @pytest.mark.parametrize('issued', ['1899-12-30 00:00:00', '2027-01-01 00:00:00', '', 'n/a'])
    def test_placeholder_and_impossible_dates_are_skipped(self, tmp_path, issued):
        path = _permits_csv(tmp_path, {'PARCEL_NUMBER': 'other'}, {'ISSUE_DT': issued})

        assert PARCEL not in read_permit_years(path, TODAY)

    def test_file_with_no_roof_permits_is_refused(self, tmp_path):
        with pytest.raises(RuntimeError, match='No roof permits'):
            read_permit_years(_permits_csv(tmp_path, {'PERMIT_DSCR': 'Roofing'}), TODAY)

    def test_renamed_column_is_refused(self, tmp_path):
        path = tmp_path / 'RP_PERMITS.csv'
        path.write_text('PARCEL_NUMBER,PERMIT_DESCRIPTION,ISSUE_DT\nx,ROOF,2019-03-31 00:00:00\n')

        with pytest.raises(KeyError):
            read_permit_years(str(path), TODAY)

    def test_sample_fixture(self):
        permits = read_permit_years(str(SAMPLE_PERMITS), TODAY)

        assert permits[SAMPLE_PARCEL] == PermitYears(roof=2019, hvac=None)


class TestMapping:
    ROW = {'PARCEL_NUMBER': PARCEL}

    def test_permit_years_are_set_from_the_lookup(self):
        result = map_csv_row_to_property(self.ROW, permits={PARCEL: PermitYears(roof=2019, hvac=2022)})

        assert (result['roof_permit_year'], result['hvac_permit_year']) == (2019, 2022)

    def test_parcel_missing_from_the_lookup_is_cleared(self):
        result = map_csv_row_to_property(self.ROW, permits={})

        assert (result['roof_permit_year'], result['hvac_permit_year']) == (None, None)

    def test_without_a_lookup_the_fields_are_left_alone(self):
        result = map_csv_row_to_property(self.ROW)

        assert 'roof_permit_year' not in result and 'hvac_permit_year' not in result


class TestImportCommand:
    def test_permits_file_sets_the_years_on_the_properties(self):
        _import_sample(permits_file=str(SAMPLE_PERMITS))

        assert PropertyListing.objects.get(parcel_id=SAMPLE_PARCEL).roof_permit_year == 2019

    def test_without_a_permits_file_existing_years_are_kept(self):
        _import_sample(permits_file=str(SAMPLE_PERMITS))

        _import_sample()

        assert PropertyListing.objects.get(parcel_id=SAMPLE_PARCEL).roof_permit_year == 2019

    def test_a_permit_that_leaves_the_file_is_cleared(self, tmp_path):
        _import_sample(permits_file=str(SAMPLE_PERMITS))

        _import_sample(permits_file=_permits_csv(tmp_path, {}))

        assert PropertyListing.objects.get(parcel_id=SAMPLE_PARCEL).roof_permit_year is None

    def test_failed_permits_download_keeps_the_years_and_the_refresh(self):
        _import_sample(permits_file=str(SAMPLE_PERMITS))
        files = {
            'RP_MILLAGE_RATES': str(FIXTURES / 'sample_millage_rates.csv'),
            'RP_PROPERTY_INFO': str(SAMPLE_PROPERTIES),
            'RP_SALES': str(FIXTURES / 'sample_sales.csv'),
        }

        def download(name, _dir):
            if name == 'RP_PERMITS':
                raise RuntimeError('PCPAO returned HTML')
            return files[name]

        with patch('apps.analytics.management.commands.import_pcpao_data.download_pcpao_file', side_effect=download):
            call_command('import_pcpao_data', quiet=True)

        assert PropertyListing.objects.get(parcel_id=SAMPLE_PARCEL).roof_permit_year == 2019
        assert Sale.objects.count() == 22


def test_parcel_page_shows_the_roof_permit(client):
    _import_sample(permits_file=str(SAMPLE_PERMITS))

    response = client.get(f'/analytics/property/{SAMPLE_PARCEL}/')

    assert response.status_code == 200
    assert 'Roof permit in 2019' in response.content.decode()
