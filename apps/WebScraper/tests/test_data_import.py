# apps/WebScraper/tests/test_data_import.py
import pytest
from decimal import Decimal
from apps.WebScraper.services.pcpao_importer import map_csv_row_to_property


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
