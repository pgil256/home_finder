import io
import zipfile
from decimal import Decimal
from unittest.mock import patch

import pytest
import responses
from django.core.management import call_command

from apps.analytics.models import PropertyListing
from apps.analytics.services.pcpao_importer import (
    PCPAO_DATABASE_FILES_PAGE,
    PCPAO_DOWNLOAD_URL,
    bulk_upsert_properties,
    download_pcpao_file,
    map_csv_row_to_property,
    safe_decimal,
    safe_int,
    vacuum_property_listing_table,
)
from apps.analytics.services.property_types import DOR_USE_CODES, dor_code_to_description

pytestmark = pytest.mark.django_db


def _pcpao_zip_bytes() -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as zip_file:
        zip_file.writestr('RP_PROPERTY_INFO.csv', 'PARCEL_NUMBER,SITE_ADDRESS\nexample,1 TEST ST\n')
    return archive.getvalue()


class TestDownloadPcpaoFile:
    @responses.activate
    def test_uses_browser_headers_and_extracts_csv(self, tmp_path):
        responses.add(
            responses.POST,
            PCPAO_DOWNLOAD_URL,
            body=_pcpao_zip_bytes(),
            status=200,
            content_type='application/zip',
        )

        csv_path = download_pcpao_file('RP_PROPERTY_INFO', str(tmp_path))

        assert (tmp_path / 'RP_PROPERTY_INFO.csv').read_text(encoding='utf-8').startswith('PARCEL_NUMBER')
        assert csv_path == str(tmp_path / 'RP_PROPERTY_INFO.csv')
        request = responses.calls[0].request
        assert request.headers['User-Agent'].startswith('Mozilla/5.0')
        assert request.headers['Referer'] == PCPAO_DATABASE_FILES_PAGE
        assert request.headers['Origin'] == 'https://www.pcpao.gov'

    @responses.activate
    def test_primes_session_and_retries_once_after_forbidden(self, tmp_path):
        responses.add(responses.POST, PCPAO_DOWNLOAD_URL, status=403)
        responses.add(responses.GET, PCPAO_DATABASE_FILES_PAGE, status=200)
        responses.add(
            responses.POST,
            PCPAO_DOWNLOAD_URL,
            body=_pcpao_zip_bytes(),
            status=200,
            content_type='application/zip',
        )

        csv_path = download_pcpao_file('RP_PROPERTY_INFO', str(tmp_path))

        assert csv_path == str(tmp_path / 'RP_PROPERTY_INFO.csv')
        assert [call.request.method for call in responses.calls] == ['POST', 'GET', 'POST']


class TestSafeDecimal:
    def test_converts_valid_number(self):
        """Test converting valid number string."""
        assert safe_decimal('100.50') == Decimal('100.50')

    def test_handles_commas(self):
        """Test handling numbers with commas."""
        assert safe_decimal('1,234,567.89') == Decimal('1234567.89')

    def test_returns_none_for_empty_string(self):
        """Test returns None for empty string."""
        assert safe_decimal('') is None

    def test_returns_none_for_whitespace(self):
        """Test returns None for whitespace only."""
        assert safe_decimal('   ') is None

    def test_returns_none_for_invalid_value(self):
        """Test returns None for non-numeric string."""
        assert safe_decimal('not a number') is None


class TestSafeInt:
    def test_converts_valid_integer(self):
        """Test converting valid integer string."""
        assert safe_int('42') == 42

    def test_converts_float_string_to_int(self):
        """Test converting float string to int."""
        assert safe_int('42.7') == 42

    def test_handles_commas(self):
        """Test handling numbers with commas."""
        assert safe_int('1,234') == 1234

    def test_returns_none_for_empty_string(self):
        """Test returns None for empty string."""
        assert safe_int('') is None

    def test_returns_none_for_invalid_value(self):
        """Test returns None for non-numeric string."""
        assert safe_int('invalid') is None


class TestMapCsvRowToProperty:
    """Column names match the current PCPAO RP_PROPERTY_INFO schema
    (PARCEL_NUMBER, SITE_ADDRESS, STR_CITY, STR_ZIP, OWNER1,
    CNTY_JST_VALUE, CNTY_ASD_VALUE, TOTAL_LIVING_SQFT, YEAR_BUILT,
    PROPERTY_USE = '<code> <description>', ACREAGE, TAX_AMOUNT_NO_EX).
    """

    def test_maps_basic_fields(self):
        row = {
            'PARCEL_NUMBER': '15-29-16-12345-000-0010',
            'SITE_ADDRESS': '123 MAIN ST',
            'STR_CITY': 'CLEARWATER',
            'STR_ZIP': '33755',
            'OWNER1': 'DOE, JOHN',
            'CNTY_JST_VALUE': '245000',
            'CNTY_ASD_VALUE': '220500',
            'TOTAL_LIVING_SQFT': '1450',
            'YEAR_BUILT': '1987',
            'ACREAGE': '0.25',
            'PROPERTY_USE': '0110 Single Family Home',
        }
        result = map_csv_row_to_property(row)

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['address'] == '123 MAIN ST'
        assert result['city'] == 'Clearwater'  # normalized from uppercase
        assert result['zip_code'] == '33755'
        assert result['owner_name'] == 'DOE, JOHN'
        assert result['market_value'] == Decimal('245000')
        assert result['assessed_value'] == Decimal('220500')
        assert result['building_sqft'] == 1450
        assert result['year_built'] == 1987
        assert result['property_type'] == 'Single Family Home'

    def test_normalizes_st_petersburg(self):
        """PCPAO ships 'ST PETERSBURG'; canonical form for the form dropdown
        is 'St. Petersburg'."""
        row = {
            'PARCEL_NUMBER': '01-30-14-00000-000-0001',
            'SITE_ADDRESS': '500 4TH ST N',
            'STR_CITY': 'ST PETERSBURG',
        }
        assert map_csv_row_to_property(row)['city'] == 'St. Petersburg'

    def test_handles_missing_fields(self):
        row = {
            'PARCEL_NUMBER': '15-29-16-12345-000-0010',
            'SITE_ADDRESS': '123 MAIN ST',
        }
        result = map_csv_row_to_property(row)

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['market_value'] is None
        assert result['city'] is None
        assert result['property_type'] == 'Unknown'

    def test_handles_empty_numeric_values(self):
        row = {
            'PARCEL_NUMBER': '15-29-16-12345-000-0010',
            'SITE_ADDRESS': '123 MAIN ST',
            'CNTY_JST_VALUE': '',
            'TOTAL_LIVING_SQFT': '',
            'ACREAGE': '',
        }
        result = map_csv_row_to_property(row)

        assert result['market_value'] is None
        assert result['building_sqft'] is None
        assert result['land_size'] is None
        assert result['lot_sqft'] is None

    def test_acreage_converts_to_lot_sqft(self):
        """1 acre = 43,560 sqft."""
        row = {
            'PARCEL_NUMBER': 'test-land',
            'ACREAGE': '1.0',
        }
        result = map_csv_row_to_property(row)

        assert result['lot_sqft'] == 43560
        assert result['land_size'] == Decimal('1.0')

    def test_property_use_strips_dor_code(self):
        """PROPERTY_USE in the new schema is '<4-digit-code> <description>';
        we keep only the description."""
        row = {
            'PARCEL_NUMBER': 'test-condo',
            'PROPERTY_USE': '0430 Condominium',
        }
        assert map_csv_row_to_property(row)['property_type'] == 'Condominium'

    def test_maps_tax_amount_from_pcpao(self):
        row = {
            'PARCEL_NUMBER': '15-29-16-12345-000-0010',
            'SITE_ADDRESS': '123 MAIN ST',
            'TAX_AMOUNT_NO_EX': '4567.89',
        }
        result = map_csv_row_to_property(row)

        assert result['tax_amount'] == Decimal('4567.89')
        assert result['tax_status'] == 'From PCPAO'

    def test_tax_amount_none_when_missing(self):
        row = {
            'PARCEL_NUMBER': 'test-no-tax',
            'SITE_ADDRESS': '456 OAK AVE',
        }
        result = map_csv_row_to_property(row)

        assert result['tax_amount'] is None
        assert 'tax_status' not in result or result.get('tax_status') != 'From PCPAO'


class TestBulkUpsertProperties:
    def test_creates_new_properties(self, db):
        """Test bulk upsert creates new properties."""
        from apps.analytics.models import PropertyListing

        properties_data = [
            {
                'parcel_id': 'new-001',
                'address': 'Test 1',
                'city': 'Test',
                'zip_code': '33755',
                'property_type': 'Single Family',
            },
            {
                'parcel_id': 'new-002',
                'address': 'Test 2',
                'city': 'Test',
                'zip_code': '33755',
                'property_type': 'Single Family',
            },
        ]

        result = bulk_upsert_properties(properties_data)

        assert result['created'] == 2
        assert result['updated'] == 0
        assert PropertyListing.objects.count() == 2

    def test_updates_existing_properties(self, sample_property):
        """Test bulk upsert updates existing properties."""

        properties_data = [
            {
                'parcel_id': sample_property.parcel_id,
                'address': 'Updated Address',
                'city': sample_property.city,
                'zip_code': sample_property.zip_code,
                'property_type': sample_property.property_type,
            }
        ]

        result = bulk_upsert_properties(properties_data)

        assert result['created'] == 0
        assert result['updated'] == 1
        sample_property.refresh_from_db()
        assert sample_property.address == 'Updated Address'

    def test_does_not_rewrite_unchanged_properties(self, sample_property):
        """Unchanged county rows do not create PostgreSQL table bloat."""
        properties_data = [
            {
                'parcel_id': sample_property.parcel_id,
                'address': sample_property.address,
                'city': sample_property.city,
                'zip_code': sample_property.zip_code,
                'property_type': sample_property.property_type,
            }
        ]

        with patch.object(PropertyListing.objects, 'bulk_update') as bulk_update:
            result = bulk_upsert_properties(properties_data)

        assert result == {'created': 0, 'updated': 0}
        bulk_update.assert_not_called()

    def test_skips_records_without_parcel_id(self, db):
        """Test bulk upsert skips records without parcel_id."""
        from apps.analytics.models import PropertyListing

        properties_data = [
            {
                'parcel_id': 'valid-001',
                'address': 'Test 1',
                'city': 'Test',
                'zip_code': '33755',
                'property_type': 'Single Family',
            },
            {
                'parcel_id': '',
                'address': 'No ID',
                'city': 'Test',
                'zip_code': '33755',
                'property_type': 'Single Family',
            },
            {'address': 'Missing ID', 'city': 'Test', 'zip_code': '33755', 'property_type': 'Single Family'},
        ]

        result = bulk_upsert_properties(properties_data)

        assert result['created'] == 1
        assert PropertyListing.objects.count() == 1


class TestVacuumPropertyListingTable:
    @patch('apps.analytics.services.pcpao_importer.connection')
    def test_disables_parallel_index_cleanup(self, connection):
        connection.vendor = 'postgresql'
        connection.ops.quote_name.return_value = '"property_table"'
        cursor = connection.cursor.return_value.__enter__.return_value

        assert vacuum_property_listing_table() is True

        cursor.execute.assert_called_once_with('VACUUM (ANALYZE, PARALLEL 0) "property_table"')


class TestImportPcpaoDataCommand:
    def test_skips_rows_missing_zip_code(self, tmp_path, db):
        csv_path = tmp_path / 'RP_PROPERTY_INFO.csv'
        csv_path.write_text(
            '\n'.join(
                [
                    'PARCEL_NUMBER,SITE_ADDRESS,STR_CITY,STR_ZIP,PROPERTY_USE',
                    'missing-zip,1 AUDIT ST,CLEARWATER,,0110 Single Family Home',
                    'valid-zip,2 AUDIT ST,CLEARWATER,33755,0110 Single Family Home',
                ]
            ),
            encoding='utf-8',
        )

        call_command('import_pcpao_data', file=str(csv_path), quiet=True)

        assert not PropertyListing.objects.filter(parcel_id='missing-zip').exists()
        assert PropertyListing.objects.filter(parcel_id='valid-zip').exists()

    def test_vacuum_first_is_safe_outside_postgresql(self, tmp_path, db):
        csv_path = tmp_path / 'RP_PROPERTY_INFO.csv'
        csv_path.write_text(
            '\n'.join(
                [
                    'PARCEL_NUMBER,SITE_ADDRESS,STR_CITY,STR_ZIP,PROPERTY_USE',
                    'vacuum-test,1 CLEAN ST,CLEARWATER,33755,0110 Single Family Home',
                ]
            ),
            encoding='utf-8',
        )

        call_command('import_pcpao_data', file=str(csv_path), quiet=True, vacuum_first=True)

        assert PropertyListing.objects.filter(parcel_id='vacuum-test').exists()

    def test_reads_pcpao_windows_1252_characters(self, tmp_path, db):
        csv_path = tmp_path / 'RP_PROPERTY_INFO.csv'
        csv_path.write_bytes(
            (
                'PARCEL_NUMBER,SITE_ADDRESS,STR_CITY,STR_ZIP,OWNER1,PROPERTY_USE\n'
                'encoded-owner,1 CLEAN ST,CLEARWATER,33755,JOSÉ,0110 Single Family Home\n'
            ).encode('cp1252')
        )

        call_command('import_pcpao_data', file=str(csv_path), quiet=True)

        imported = PropertyListing.objects.get(parcel_id='encoded-owner')
        assert imported.owner_name == 'JOSÉ'


class TestPropertyTypeConversion:
    def test_dor_code_single_family(self):
        """Test DOR code conversion for single family."""
        result = dor_code_to_description('0100')
        assert result == 'Single Family'

    def test_dor_code_condo(self):
        """Test DOR code conversion for condominium."""
        result = dor_code_to_description('0400')
        assert result == 'Condominium'

    def test_dor_code_vacant_residential(self):
        """Test DOR code conversion for vacant residential."""
        result = dor_code_to_description('0000')
        assert result == 'Vacant Residential'

    def test_dor_code_unknown(self):
        """Test DOR code conversion for unknown code."""
        result = dor_code_to_description('9999')
        assert result == 'Unknown (9999)'

    def test_dor_code_empty_string(self):
        """Test DOR code conversion for empty string."""
        result = dor_code_to_description('')
        assert 'Unknown' in result

    def test_dor_code_strips_whitespace(self):
        """Test DOR code strips whitespace."""
        result = dor_code_to_description('  0100  ')
        assert result == 'Single Family'

    def test_all_codes_have_descriptions(self):
        """Test all defined codes return meaningful descriptions."""
        for code, description in DOR_USE_CODES.items():
            result = dor_code_to_description(code)
            assert result == description
            assert 'Unknown' not in result
