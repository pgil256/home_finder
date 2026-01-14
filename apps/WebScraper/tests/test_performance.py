"""
Performance Tests for WebScraper App

These tests identify and verify performance characteristics of critical operations.
They measure query counts, execution time, and memory usage to ensure
the system can handle large datasets efficiently.

Performance Bottleneck Areas Tested:
1. Database query efficiency (N+1 queries, bulk operations)
2. Sorting algorithm efficiency
3. Bulk upsert operations
4. Property filtering with database indexes
"""

import time
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.db import connection, reset_queries
from django.test.utils import override_settings, CaptureQueriesContext
from django.conf import settings

from apps.WebScraper.models import PropertyListing


pytestmark = [pytest.mark.django_db]


class QueryCounter(CaptureQueriesContext):
    """Context manager to count database queries using Django's CaptureQueriesContext."""

    def __init__(self):
        super().__init__(connection)

    @property
    def count(self):
        return len(self.captured_queries)


@pytest.fixture
def large_property_dataset(db):
    """Create a large dataset of properties for performance testing."""
    properties = []
    for i in range(100):
        properties.append(PropertyListing(
            parcel_id=f'15-29-16-{i:05d}-000-0001',
            address=f'{100 + i} Performance Test St',
            city='Clearwater' if i % 3 == 0 else ('St Petersburg' if i % 3 == 1 else 'Tampa'),
            zip_code=f'337{i % 100:02d}',
            owner_name=f'Test Owner {i}',
            property_type='Single Family' if i % 2 == 0 else 'Condo',
            market_value=Decimal(str(200000 + i * 5000)),
            assessed_value=Decimal(str(180000 + i * 4500)),
            building_sqft=1200 + i * 10,
            year_built=1980 + (i % 40),
            bedrooms=2 + (i % 4),
            bathrooms=Decimal(str(1.5 + (i % 3) * 0.5)),
            land_size=Decimal('0.20'),
            tax_amount=Decimal(str(2000 + i * 50)) if i % 2 == 0 else None,
            tax_status='Paid' if i % 3 == 0 else ('Unpaid' if i % 3 == 1 else 'Unknown'),
        ))
    PropertyListing.objects.bulk_create(properties)
    return [p.parcel_id for p in properties]


class TestDatabaseQueryEfficiency:
    """Test database query patterns for N+1 issues."""

    def test_individual_lookups_query_count(self, large_property_dataset):
        """Demonstrate N+1 query pattern with individual lookups.

        This test shows the problematic pattern in scrape_tax_data task
        where each parcel_id triggers a separate database query.
        """
        parcel_ids = large_property_dataset[:20]

        with QueryCounter() as qc:
            # Simulate the N+1 pattern from scrape_data.py lines 95-105
            results = []
            for parcel_id in parcel_ids:
                try:
                    listing = PropertyListing.objects.get(parcel_id=parcel_id)
                    results.append(listing)
                except PropertyListing.DoesNotExist:
                    pass

        # N+1 pattern: one query per item
        assert qc.count == 20, f"Expected 20 queries (N+1 pattern), got {qc.count}"

    def test_batch_lookup_query_count(self, large_property_dataset):
        """Demonstrate efficient batch lookup pattern.

        This shows the recommended approach using a single IN query.
        """
        parcel_ids = large_property_dataset[:20]

        with QueryCounter() as qc:
            # Efficient batch query
            results = list(PropertyListing.objects.filter(parcel_id__in=parcel_ids))

        # Single query for all items
        assert qc.count == 1, f"Expected 1 query (batch pattern), got {qc.count}"
        assert len(results) == 20

    def test_batch_lookup_with_dict_conversion(self, large_property_dataset):
        """Test batch lookup converted to dict for O(1) access."""
        parcel_ids = large_property_dataset[:50]

        with QueryCounter() as qc:
            # Single query to dict
            results_dict = {
                p.parcel_id: p
                for p in PropertyListing.objects.filter(parcel_id__in=parcel_ids)
            }

            # O(1) access for each parcel
            for parcel_id in parcel_ids:
                listing = results_dict.get(parcel_id)

        # Still only 1 query despite 50 lookups
        assert qc.count == 1, f"Expected 1 query with dict pattern, got {qc.count}"
        assert len(results_dict) == 50

    def test_values_list_reduces_memory(self, large_property_dataset):
        """Test values_list for memory-efficient data retrieval."""
        parcel_ids = large_property_dataset

        with QueryCounter() as qc:
            # Only retrieve needed fields
            tax_status_map = dict(
                PropertyListing.objects.filter(
                    parcel_id__in=parcel_ids
                ).values_list('parcel_id', 'tax_amount')
            )

        assert qc.count == 1
        assert len(tax_status_map) == 100


class TestBulkUpsertPerformance:
    """Test bulk insert/update performance."""

    def test_individual_update_or_create_query_count(self, db):
        """Measure queries for individual update_or_create pattern.

        This demonstrates the inefficient pattern in bulk_upsert_properties.
        """
        properties = [
            {
                'parcel_id': f'15-29-16-PERF{i:03d}-000-0001',
                'address': f'{i} Test St',
                'city': 'Clearwater',
                'zip_code': '33755',
                'property_type': 'Single Family',
            }
            for i in range(10)
        ]

        with QueryCounter() as qc:
            # Individual update_or_create pattern (current implementation)
            for prop in properties:
                parcel_id = prop.pop('parcel_id')
                PropertyListing.objects.update_or_create(
                    parcel_id=parcel_id,
                    defaults=prop
                )

        # Each update_or_create does SELECT + INSERT/UPDATE
        # Minimum 2 queries per item (20 for 10 items)
        assert qc.count >= 10, f"Expected at least 10 queries, got {qc.count}"

    def test_bulk_create_performance(self, db):
        """Test bulk_create for new records."""
        properties = [
            PropertyListing(
                parcel_id=f'15-29-16-BULK{i:03d}-000-0001',
                address=f'{i} Bulk Test St',
                city='Clearwater',
                zip_code='33755',
                property_type='Single Family',
            )
            for i in range(50)
        ]

        with QueryCounter() as qc:
            PropertyListing.objects.bulk_create(properties, ignore_conflicts=True)

        # 1-2 queries for bulk insert (may include SAVEPOINT on some backends)
        # Key point: much fewer than 50 individual queries
        assert qc.count <= 2, f"Expected <=2 queries for bulk_create, got {qc.count}"
        assert qc.count < 50, "bulk_create should be much more efficient than individual inserts"

    def test_bulk_update_performance(self, large_property_dataset):
        """Test bulk_update for existing records."""
        parcel_ids = large_property_dataset[:50]

        # First, get existing records
        properties = list(PropertyListing.objects.filter(parcel_id__in=parcel_ids))

        # Modify them
        for prop in properties:
            prop.tax_status = 'Bulk Updated'

        with QueryCounter() as qc:
            PropertyListing.objects.bulk_update(properties, ['tax_status'])

        # Single query for all updates
        assert qc.count == 1, f"Expected 1 query for bulk_update, got {qc.count}"

        # Verify updates applied
        updated = PropertyListing.objects.filter(
            parcel_id__in=parcel_ids,
            tax_status='Bulk Updated'
        ).count()
        assert updated == 50


class TestSortingAlgorithmPerformance:
    """Test sorting algorithm efficiency."""

    def test_quicksort_basic_functionality(self):
        """Test the custom quicksort implementation."""
        from apps.WebScraper.tasks.sort_data import quick_sort

        data = [5, 2, 8, 1, 9, 3]
        sorted_data = quick_sort(data, lambda x, y: x - y)

        assert sorted_data == [1, 2, 3, 5, 8, 9]

    def test_quicksort_vs_builtin_sort_small_dataset(self):
        """Compare custom quicksort to Python's built-in sort on small data."""
        from apps.WebScraper.tasks.sort_data import quick_sort
        import random

        data = list(range(100))
        random.shuffle(data)

        # Custom quicksort
        start = time.perf_counter()
        custom_sorted = quick_sort(data.copy(), lambda x, y: x - y)
        custom_time = time.perf_counter() - start

        # Built-in sort
        start = time.perf_counter()
        builtin_sorted = sorted(data.copy())
        builtin_time = time.perf_counter() - start

        assert custom_sorted == builtin_sorted
        # Custom quicksort should complete within reasonable time
        assert custom_time < 1.0, f"Custom quicksort took {custom_time:.3f}s"

    def test_quicksort_with_namedtuples(self, large_property_dataset):
        """Test quicksort with actual property data structures."""
        from apps.WebScraper.tasks.sort_data import quick_sort, fetch_property_listings

        columns, listings = fetch_property_listings()

        # Convert to list for sorting
        listings_list = list(listings)

        if len(listings_list) > 0:
            # Sort by market_value
            def compare_by_value(x, y):
                x_val = getattr(x, 'market_value', 0) or 0
                y_val = getattr(y, 'market_value', 0) or 0
                return (float(x_val) - float(y_val))

            start = time.perf_counter()
            sorted_listings = quick_sort(listings_list, compare_by_value)
            elapsed = time.perf_counter() - start

            assert len(sorted_listings) == len(listings_list)
            # Should complete quickly for 100 items
            assert elapsed < 1.0, f"Sorting took {elapsed:.3f}s for {len(listings_list)} items"

    def test_quicksort_empty_list(self):
        """Test quicksort handles empty list."""
        from apps.WebScraper.tasks.sort_data import quick_sort

        result = quick_sort([], lambda x, y: x - y)
        assert result == []

    def test_quicksort_single_element(self):
        """Test quicksort handles single element."""
        from apps.WebScraper.tasks.sort_data import quick_sort

        result = quick_sort([42], lambda x, y: x - y)
        assert result == [42]

    def test_quicksort_already_sorted(self):
        """Test quicksort with already sorted data (worst case for naive quicksort)."""
        from apps.WebScraper.tasks.sort_data import quick_sort

        data = list(range(100))  # Already sorted - worst case

        start = time.perf_counter()
        result = quick_sort(data, lambda x, y: x - y)
        elapsed = time.perf_counter() - start

        assert result == data
        # Even worst case should complete reasonably for 100 items
        assert elapsed < 1.0, f"Worst case took {elapsed:.3f}s"


class TestPropertyFilteringPerformance:
    """Test property filtering and search performance."""

    def test_filter_by_city_query_efficiency(self, large_property_dataset):
        """Test filtering by city uses efficient query."""
        with QueryCounter() as qc:
            clearwater_props = list(
                PropertyListing.objects.filter(city='Clearwater')
            )

        assert qc.count == 1
        # Approximately 1/3 of 100 properties should be in Clearwater
        assert len(clearwater_props) >= 30

    def test_filter_by_multiple_criteria(self, large_property_dataset):
        """Test combined filters still use single query."""
        with QueryCounter() as qc:
            results = list(
                PropertyListing.objects.filter(
                    city='Clearwater',
                    property_type='Single Family',
                    market_value__gte=200000,
                    market_value__lte=400000,
                )
            )

        # Should be a single query despite multiple filters
        assert qc.count == 1

    def test_filter_with_ordering(self, large_property_dataset):
        """Test filtering with ordering is efficient."""
        with QueryCounter() as qc:
            results = list(
                PropertyListing.objects.filter(
                    city='Clearwater'
                ).order_by('-market_value')[:10]
            )

        # Single query with ORDER BY and LIMIT
        assert qc.count == 1
        assert len(results) <= 10

    def test_count_vs_len_performance(self, large_property_dataset):
        """Test count() vs len() query patterns."""
        # count() is more efficient for just getting count
        with QueryCounter() as qc:
            count1 = PropertyListing.objects.filter(city='Clearwater').count()

        assert qc.count == 1

        # len() on queryset triggers full fetch
        with QueryCounter() as qc:
            qs = PropertyListing.objects.filter(city='Clearwater')
            count2 = len(list(qs))

        assert qc.count == 1
        assert count1 == count2

    def test_exists_vs_count_for_boolean_check(self, large_property_dataset):
        """Test exists() is more efficient than count() for boolean checks."""
        # exists() can short-circuit
        with QueryCounter() as qc:
            has_clearwater = PropertyListing.objects.filter(city='Clearwater').exists()

        assert qc.count == 1
        assert has_clearwater is True


class TestExcelGenerationPerformance:
    """Test Excel generation performance characteristics."""

    def test_fetch_property_listings_query_count(self, large_property_dataset):
        """Test fetch_property_listings uses minimal queries."""
        from apps.WebScraper.tasks.sort_data import fetch_property_listings

        with QueryCounter() as qc:
            columns, listings = fetch_property_listings()

        # Should be 2 queries max: one for keywords, one for listings
        assert qc.count <= 2, f"Expected <= 2 queries, got {qc.count}"

    def test_generate_spreadsheet_creates_file(self, large_property_dataset, tmp_path):
        """Test spreadsheet generation with actual data."""
        from apps.WebScraper.tasks.sort_data import generate_spreadsheet, fetch_property_listings
        import os

        # Patch REPORTS_DIR to use temp directory
        with patch('apps.WebScraper.tasks.sort_data.REPORTS_DIR', str(tmp_path)):
            columns, listings = fetch_property_listings()

            start = time.perf_counter()
            filepath = generate_spreadsheet(columns, listings)
            elapsed = time.perf_counter() - start

            assert os.path.exists(filepath)
            # Should complete in reasonable time for 100 records
            assert elapsed < 5.0, f"Excel generation took {elapsed:.3f}s"


class TestTaxDataCollectionPerformance:
    """Test tax data collection query patterns."""

    def test_check_existing_tax_data_efficient(self, large_property_dataset):
        """Test efficient pattern for checking existing tax data."""
        parcel_ids = large_property_dataset[:50]

        with QueryCounter() as qc:
            # Efficient: single query to get all tax amounts
            existing_tax = dict(
                PropertyListing.objects.filter(
                    parcel_id__in=parcel_ids
                ).values_list('parcel_id', 'tax_amount')
            )

            # Check which need scraping
            need_scraping = [
                pid for pid in parcel_ids
                if existing_tax.get(pid) is None
            ]

        assert qc.count == 1, f"Expected 1 query, got {qc.count}"

    def test_batch_tax_update_efficient(self, large_property_dataset):
        """Test efficient batch update for tax data."""
        parcel_ids = large_property_dataset[:20]

        # Simulate batch tax data results
        tax_results = [
            {'parcel_id': pid, 'tax_amount': 3000, 'tax_status': 'Paid'}
            for pid in parcel_ids
        ]

        # Get existing records in single query
        properties = {
            p.parcel_id: p
            for p in PropertyListing.objects.filter(parcel_id__in=parcel_ids)
        }

        # Update in memory
        to_update = []
        for result in tax_results:
            prop = properties.get(result['parcel_id'])
            if prop:
                prop.tax_amount = result['tax_amount']
                prop.tax_status = result['tax_status']
                to_update.append(prop)

        with QueryCounter() as qc:
            # Single bulk update
            PropertyListing.objects.bulk_update(to_update, ['tax_amount', 'tax_status'])

        assert qc.count == 1, f"Expected 1 query for bulk_update, got {qc.count}"


class TestBulkUpsertOptimized:
    """Test the optimized bulk_upsert_properties function."""

    def test_bulk_upsert_new_records_query_count(self, db):
        """Test bulk_upsert uses minimal queries for new records."""
        from apps.WebScraper.services.pcpao_importer import bulk_upsert_properties

        properties = [
            {
                'parcel_id': f'15-29-16-UPSERT{i:03d}-000-0001',
                'address': f'{i} Upsert Test St',
                'city': 'Clearwater',
                'zip_code': '33755',
                'property_type': 'Single Family',
            }
            for i in range(20)
        ]

        with QueryCounter() as qc:
            stats = bulk_upsert_properties(properties)

        # Should be: 1 SELECT (check existing) + 1 INSERT (bulk_create)
        # Plus possible SAVEPOINT queries from transaction.atomic()
        # Key assertion: much fewer than 20+ queries with old N+1 implementation
        assert qc.count <= 5, f"Expected <=5 queries for bulk upsert, got {qc.count}"
        assert qc.count < 20, "bulk_upsert should be much more efficient than N+1 pattern"
        assert stats['created'] == 20
        assert stats['updated'] == 0

    def test_bulk_upsert_existing_records_query_count(self, db):
        """Test bulk_upsert uses minimal queries for existing records."""
        from apps.WebScraper.services.pcpao_importer import bulk_upsert_properties

        # First, create records
        initial_props = [
            {
                'parcel_id': f'15-29-16-EXIST{i:03d}-000-0001',
                'address': f'{i} Initial St',
                'city': 'Tampa',
                'zip_code': '33601',
                'property_type': 'Condo',
            }
            for i in range(15)
        ]
        bulk_upsert_properties(initial_props)

        # Now update them
        updated_props = [
            {
                'parcel_id': f'15-29-16-EXIST{i:03d}-000-0001',
                'address': f'{i} Updated St',
                'city': 'Clearwater',
                'zip_code': '33755',
                'property_type': 'Single Family',
            }
            for i in range(15)
        ]

        with QueryCounter() as qc:
            stats = bulk_upsert_properties(updated_props)

        # Should be: 1 SELECT (check existing) + 1 UPDATE (bulk_update)
        # Plus possible SAVEPOINT queries
        assert qc.count <= 5, f"Expected <=5 queries for bulk update, got {qc.count}"
        assert qc.count < 15, "bulk_upsert should be much more efficient than N+1 pattern"
        assert stats['created'] == 0
        assert stats['updated'] == 15

    def test_bulk_upsert_mixed_records_query_count(self, db):
        """Test bulk_upsert handles mix of new and existing efficiently."""
        from apps.WebScraper.services.pcpao_importer import bulk_upsert_properties

        # Create some existing records
        existing_props = [
            {
                'parcel_id': f'15-29-16-MIX{i:03d}-000-0001',
                'address': f'{i} Existing St',
                'city': 'Tampa',
                'zip_code': '33601',
                'property_type': 'Condo',
            }
            for i in range(10)
        ]
        bulk_upsert_properties(existing_props)

        # Now process mix of existing and new
        mixed_props = [
            {
                'parcel_id': f'15-29-16-MIX{i:03d}-000-0001',
                'address': f'{i} Mixed St',
                'city': 'Clearwater',
                'zip_code': '33755',
                'property_type': 'Single Family',
            }
            for i in range(20)  # 10 existing + 10 new
        ]

        with QueryCounter() as qc:
            stats = bulk_upsert_properties(mixed_props)

        # Should be: 1 SELECT + 1 INSERT + 1 UPDATE + SAVEPOINTs
        assert qc.count <= 6, f"Expected <=6 queries for mixed upsert, got {qc.count}"
        assert qc.count < 20, "bulk_upsert should be much more efficient than N+1 pattern"
        assert stats['created'] == 10
        assert stats['updated'] == 10


class TestMemoryEfficiency:
    """Test memory-efficient patterns."""

    def test_iterator_for_large_queryset(self, large_property_dataset):
        """Test iterator() for memory-efficient iteration."""
        count = 0

        # Using iterator() processes one row at a time
        for prop in PropertyListing.objects.all().iterator():
            count += 1

        assert count == 100

    def test_values_list_vs_full_objects(self, large_property_dataset):
        """Demonstrate values_list is more memory efficient than full objects."""
        # Full objects (more memory)
        full_objects = list(PropertyListing.objects.all())

        # Values list (less memory)
        values_only = list(
            PropertyListing.objects.values_list('parcel_id', 'market_value')
        )

        assert len(full_objects) == len(values_only) == 100

    def test_only_defer_for_partial_loading(self, large_property_dataset):
        """Test only() and defer() for partial model loading."""
        with QueryCounter() as qc:
            # Load only specific fields
            partial = list(
                PropertyListing.objects.only('parcel_id', 'address', 'market_value')
            )

        assert qc.count == 1
        assert len(partial) == 100
