import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from apps.WebScraper.services.pcpao_importer import (
    map_csv_row_to_property,
    bulk_upsert_properties,
    safe_decimal,
    safe_int,
    FIELD_MAPPING,
)
from apps.WebScraper.services.property_types import dor_code_to_description, DOR_USE_CODES

pytestmark = pytest.mark.django_db


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
    def test_maps_basic_fields(self):
        """Test CSV row mapping to PropertyListing fields."""
        row = {
            'PARCEL_ID': '15-29-16-12345-000-0010',
            'SITE_ADDR': '123 Main St',
            'SITE_CITY': 'CLEARWATER',
            'SITE_ZIP': '33755',
            'OWN_NAME': 'John Doe',
            'JV': '245000',
            'AV': '220500',
            'LIV_AREA': '1450',
            'YR_BLT': '1987',
            'BEDS': '3',
            'BATHS': '2',
            'LAND_SQFT': '10890',
            'DOR_UC': '0100',
        }
        result = map_csv_row_to_property(row)

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['address'] == '123 Main St'
        assert result['city'] == 'CLEARWATER'
        assert result['market_value'] == Decimal('245000')
        assert result['building_sqft'] == 1450
        assert result['property_type'] == 'Single Family'

    def test_handles_missing_fields(self):
        """Test mapping handles missing optional fields."""
        row = {
            'PARCEL_ID': '15-29-16-12345-000-0010',
            'SITE_ADDR': '123 Main St',
        }
        result = map_csv_row_to_property(row)

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['market_value'] is None

    def test_handles_empty_numeric_values(self):
        """Test mapping handles empty strings for numeric fields."""
        row = {
            'PARCEL_ID': '15-29-16-12345-000-0010',
            'SITE_ADDR': '123 Main St',
            'JV': '',
            'LIV_AREA': '',
            'BEDS': '',
        }
        result = map_csv_row_to_property(row)

        assert result['parcel_id'] == '15-29-16-12345-000-0010'
        assert result['market_value'] is None
        assert result['building_sqft'] is None
        assert result['bedrooms'] is None

    def test_calculates_land_size_from_sqft(self):
        """Test land_size is calculated from lot_sqft."""
        row = {
            'PARCEL_ID': 'test-land',
            'LAND_SQFT': '43560',  # 1 acre
        }
        result = map_csv_row_to_property(row)

        assert result['lot_sqft'] == 43560
        assert result['land_size'] == Decimal('1')

    def test_land_size_none_when_no_sqft(self):
        """Test land_size is None when lot_sqft is missing."""
        row = {
            'PARCEL_ID': 'test-no-land',
        }
        result = map_csv_row_to_property(row)

        assert result['lot_sqft'] is None
        assert result['land_size'] is None

    def test_maps_tax_amount_from_pcpao(self):
        """Test CSV row mapping includes tax_amount from TAX_AMOUNT_NO_EX field."""
        row = {
            'PARCEL_ID': '15-29-16-12345-000-0010',
            'SITE_ADDR': '123 Main St',
            'TAX_AMOUNT_NO_EX': '4567.89',
        }
        result = map_csv_row_to_property(row)

        assert result['tax_amount'] == Decimal('4567.89')
        assert result['tax_status'] == 'From PCPAO'

    def test_tax_amount_none_when_missing(self):
        """Test tax_amount is None when TAX_AMOUNT_NO_EX is missing."""
        row = {
            'PARCEL_ID': 'test-no-tax',
            'SITE_ADDR': '456 Oak Ave',
        }
        result = map_csv_row_to_property(row)

        assert result['tax_amount'] is None
        assert 'tax_status' not in result or result.get('tax_status') != 'From PCPAO'


class TestBulkUpsertProperties:
    def test_creates_new_properties(self, db):
        """Test bulk upsert creates new properties."""
        from apps.WebScraper.models import PropertyListing

        properties_data = [
            {'parcel_id': 'new-001', 'address': 'Test 1', 'city': 'Test', 'zip_code': '33755', 'property_type': 'Single Family'},
            {'parcel_id': 'new-002', 'address': 'Test 2', 'city': 'Test', 'zip_code': '33755', 'property_type': 'Single Family'},
        ]

        result = bulk_upsert_properties(properties_data)

        assert result['created'] == 2
        assert result['updated'] == 0
        assert PropertyListing.objects.count() == 2

    def test_updates_existing_properties(self, sample_property):
        """Test bulk upsert updates existing properties."""
        from apps.WebScraper.models import PropertyListing

        properties_data = [{
            'parcel_id': sample_property.parcel_id,
            'address': 'Updated Address',
            'city': sample_property.city,
            'zip_code': sample_property.zip_code,
            'property_type': sample_property.property_type,
        }]

        result = bulk_upsert_properties(properties_data)

        assert result['created'] == 0
        assert result['updated'] == 1
        sample_property.refresh_from_db()
        assert sample_property.address == 'Updated Address'

    def test_skips_records_without_parcel_id(self, db):
        """Test bulk upsert skips records without parcel_id."""
        from apps.WebScraper.models import PropertyListing

        properties_data = [
            {'parcel_id': 'valid-001', 'address': 'Test 1', 'city': 'Test', 'zip_code': '33755', 'property_type': 'Single Family'},
            {'parcel_id': '', 'address': 'No ID', 'city': 'Test', 'zip_code': '33755', 'property_type': 'Single Family'},
            {'address': 'Missing ID', 'city': 'Test', 'zip_code': '33755', 'property_type': 'Single Family'},
        ]

        result = bulk_upsert_properties(properties_data)

        assert result['created'] == 1
        assert PropertyListing.objects.count() == 1


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
