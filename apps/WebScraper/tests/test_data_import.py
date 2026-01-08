# apps/WebScraper/tests/test_data_import.py
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from decimal import Decimal
from django.test import TestCase
from apps.WebScraper.services.pcpao_importer import map_csv_row_to_property, download_pcpao_file, PCPAO_DATA_URL


class TestCSVFieldMapping:
    def test_map_csv_row_extracts_parcel_id(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': 'SMITH JOHN',
            'JV': '250000',
            'AV': '225000',
            'LIV_AREA': '1500',
            'YR_BLT': '1985',
            'BEDS': '3',
            'BATHS': '2',
            'DOR_UC': '0100',
            'LAND_SQFT': '7500',
        }
        result = map_csv_row_to_property(row)
        assert result['parcel_id'] == '14-31-15-00000-000-0001'

    def test_map_csv_row_extracts_address_fields(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': 'SMITH JOHN',
            'JV': '250000',
            'AV': '225000',
            'LIV_AREA': '1500',
            'YR_BLT': '1985',
            'BEDS': '3',
            'BATHS': '2',
            'DOR_UC': '0100',
            'LAND_SQFT': '7500',
        }
        result = map_csv_row_to_property(row)
        assert result['address'] == '123 MAIN ST'
        assert result['city'] == 'CLEARWATER'
        assert result['zip_code'] == '33755'

    def test_map_csv_row_extracts_valuation(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': 'SMITH JOHN',
            'JV': '250000',
            'AV': '225000',
            'LIV_AREA': '1500',
            'YR_BLT': '1985',
            'BEDS': '3',
            'BATHS': '2',
            'DOR_UC': '0100',
            'LAND_SQFT': '7500',
        }
        result = map_csv_row_to_property(row)
        assert result['market_value'] == Decimal('250000')
        assert result['assessed_value'] == Decimal('225000')

    def test_map_csv_row_handles_empty_values(self):
        row = {
            'PARCEL_ID': '14-31-15-00000-000-0001',
            'SITE_ADDR': '123 MAIN ST',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': '',
            'JV': '',
            'AV': '',
            'LIV_AREA': '',
            'YR_BLT': '',
            'BEDS': '',
            'BATHS': '',
            'DOR_UC': '0100',
            'LAND_SQFT': '',
        }
        result = map_csv_row_to_property(row)
        assert result['owner_name'] is None
        assert result['market_value'] is None
        assert result['building_sqft'] is None


class TestCSVDownload:
    def test_download_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_response = MagicMock()
            mock_response.iter_content = lambda chunk_size: [b'PARCEL_ID,SITE_ADDR\n', b'123,Main St\n']
            mock_response.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_response) as mock_get:
                mock_get.return_value.__enter__ = lambda s: mock_response
                mock_get.return_value.__exit__ = MagicMock(return_value=False)

                filepath = download_pcpao_file('RP_PROPERTY_INFO', tmpdir)

                assert os.path.exists(filepath)
                assert filepath.endswith('.csv')

    def test_download_uses_correct_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_response = MagicMock()
            mock_response.iter_content = lambda chunk_size: [b'data']
            mock_response.raise_for_status = MagicMock()

            with patch('requests.get', return_value=mock_response) as mock_get:
                mock_get.return_value.__enter__ = lambda s: mock_response
                mock_get.return_value.__exit__ = MagicMock(return_value=False)

                download_pcpao_file('RP_PROPERTY_INFO', tmpdir)

                call_url = mock_get.call_args[0][0]
                assert 'RP_PROPERTY_INFO' in call_url


class TestBulkUpsert(TestCase):
    def test_bulk_upsert_creates_new_records(self):
        from apps.WebScraper.models import PropertyListing
        from apps.WebScraper.services.pcpao_importer import bulk_upsert_properties

        properties = [
            {
                'parcel_id': '14-31-15-00000-000-0001',
                'address': '123 MAIN ST',
                'city': 'CLEARWATER',
                'zip_code': '33755',
                'property_type': '0100',
            },
            {
                'parcel_id': '14-31-15-00000-000-0002',
                'address': '456 OAK AVE',
                'city': 'ST PETERSBURG',
                'zip_code': '33701',
                'property_type': '0100',
            },
        ]

        stats = bulk_upsert_properties(properties)

        assert stats['created'] == 2
        assert stats['updated'] == 0
        assert PropertyListing.objects.count() == 2

    def test_bulk_upsert_updates_existing_records(self):
        from apps.WebScraper.models import PropertyListing
        from apps.WebScraper.services.pcpao_importer import bulk_upsert_properties

        PropertyListing.objects.create(
            parcel_id='14-31-15-00000-000-0001',
            address='OLD ADDRESS',
            city='CLEARWATER',
            zip_code='33755',
            property_type='0100',
        )

        properties = [
            {
                'parcel_id': '14-31-15-00000-000-0001',
                'address': 'NEW ADDRESS',
                'city': 'CLEARWATER',
                'zip_code': '33755',
                'property_type': '0100',
            },
        ]

        stats = bulk_upsert_properties(properties)

        assert stats['created'] == 0
        assert stats['updated'] == 1

        listing = PropertyListing.objects.get(parcel_id='14-31-15-00000-000-0001')
        assert listing.address == 'NEW ADDRESS'


class TestPropertyTypes:
    def test_single_family_code(self):
        from apps.WebScraper.services.property_types import dor_code_to_description
        assert dor_code_to_description('0100') == 'Single Family'

    def test_condo_code(self):
        from apps.WebScraper.services.property_types import dor_code_to_description
        assert dor_code_to_description('0400') == 'Condominium'

    def test_unknown_code(self):
        from apps.WebScraper.services.property_types import dor_code_to_description
        assert dor_code_to_description('9999') == 'Unknown (9999)'


class TestImportCommand(TestCase):
    def test_import_from_local_file(self):
        from django.core.management import call_command
        from apps.WebScraper.models import PropertyListing

        fixture_path = os.path.join(
            os.path.dirname(__file__),
            '../fixtures/sample_pcpao_data.csv'
        )

        call_command('import_pcpao_data', file=fixture_path, quiet=True)

        assert PropertyListing.objects.count() == 3

        clearwater = PropertyListing.objects.get(parcel_id='14-31-15-00000-000-0001')
        assert clearwater.city == 'CLEARWATER'
        assert clearwater.market_value == Decimal('250000')

    def test_import_with_limit(self):
        from django.core.management import call_command
        from apps.WebScraper.models import PropertyListing

        fixture_path = os.path.join(
            os.path.dirname(__file__),
            '../fixtures/sample_pcpao_data.csv'
        )

        call_command('import_pcpao_data', file=fixture_path, quiet=True, limit=2)

        assert PropertyListing.objects.count() == 2


class TestPropertySearch(TestCase):
    def setUp(self):
        from apps.WebScraper.models import PropertyListing

        PropertyListing.objects.create(
            parcel_id='14-31-15-00000-000-0001',
            address='123 MAIN ST',
            city='CLEARWATER',
            zip_code='33755',
            property_type='Single Family',
            market_value=Decimal('250000'),
        )
        PropertyListing.objects.create(
            parcel_id='14-31-15-00000-000-0002',
            address='456 OAK AVE',
            city='ST PETERSBURG',
            zip_code='33701',
            property_type='Single Family',
            market_value=Decimal('320000'),
        )

    def test_search_by_city(self):
        from apps.WebScraper.models import PropertyListing

        results = PropertyListing.objects.filter(city__icontains='clearwater')
        assert results.count() == 1
        assert results.first().address == '123 MAIN ST'

    def test_search_by_price_range(self):
        from apps.WebScraper.models import PropertyListing

        results = PropertyListing.objects.filter(
            market_value__gte=200000,
            market_value__lte=300000
        )
        assert results.count() == 1
