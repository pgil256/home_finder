# apps/WebScraper/tests/test_data_import.py
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from decimal import Decimal
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
