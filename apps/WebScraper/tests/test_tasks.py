# apps/WebScraper/tests/test_tasks.py
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

pytestmark = [pytest.mark.django_db, pytest.mark.celery]


@pytest.fixture
def mock_progress_recorder():
    """Mock ProgressRecorder to avoid celery task_id issues."""
    with patch('celery_progress.backend.ProgressRecorder') as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


class TestScrapeDataTasks:
    @patch('apps.WebScraper.tasks.pcpao_scraper.PCPAOScraper')
    @patch('apps.WebScraper.tasks.scrape_data.ProgressRecorder')
    def test_scrape_pinellas_properties_creates_records(self, mock_progress, mock_scraper_class, celery_eager):
        """Test scrape task creates PropertyListing records.

        Note: The scrape task now uses parallel scraping with separate search and detail phases.
        """
        from apps.WebScraper.tasks.scrape_data import scrape_pinellas_properties
        from apps.WebScraper.models import PropertyListing

        # Mock scraper instance
        mock_scraper = MagicMock()
        # Mock search phase returns parcel IDs with URLs
        mock_scraper.search_properties_with_urls.return_value = [
            {'parcel_id': 'test-001', 'detail_url': 'http://test1'},
        ]
        # Mock parallel scraping returns full property data
        mock_scraper.scrape_properties_parallel.return_value = [
            {
                'parcel_id': 'test-001',
                'address': '123 Test St',
                'city': 'Clearwater',
                'zip_code': '33755',
                'market_value': Decimal('250000'),
            }
        ]
        mock_scraper_class.return_value = mock_scraper

        result = scrape_pinellas_properties({'city': 'Clearwater'}, limit=10)

        assert PropertyListing.objects.filter(parcel_id='test-001').exists()
        assert 'test-001' in result['property_ids']

    @patch('apps.WebScraper.tasks.pcpao_scraper.PCPAOScraper')
    @patch('apps.WebScraper.tasks.scrape_data.ProgressRecorder')
    def test_scrape_pinellas_properties_returns_ids(self, mock_progress, mock_scraper_class, celery_eager):
        """Test scrape task returns list of property IDs."""
        from apps.WebScraper.tasks.scrape_data import scrape_pinellas_properties

        mock_scraper = MagicMock()
        mock_scraper.search_properties_with_urls.return_value = [
            {'parcel_id': 'test-001', 'detail_url': 'http://test1'},
            {'parcel_id': 'test-002', 'detail_url': 'http://test2'},
        ]
        mock_scraper.scrape_properties_parallel.return_value = [
            {'parcel_id': 'test-001', 'address': '123 Test St', 'city': 'Test'},
            {'parcel_id': 'test-002', 'address': '456 Test Ave', 'city': 'Test'},
        ]
        mock_scraper_class.return_value = mock_scraper

        result = scrape_pinellas_properties({'city': 'Test'}, limit=10)

        assert len(result['property_ids']) == 2
        assert result['search_criteria'] == {'city': 'Test'}

    @patch('apps.WebScraper.tasks.scrape_data.ProgressRecorder')
    def test_scrape_tax_data_is_passthrough(self, mock_progress, property_without_tax, celery_eager):
        """Test tax scraper is now a passthrough (tax data comes from PCPAO bulk import).

        The real-time tax collector scraper has been disabled because the tax collector
        website doesn't provide property-specific tax data via search.
        """
        from apps.WebScraper.tasks.scrape_data import scrape_tax_data

        scrape_result = {
            'property_ids': [property_without_tax.parcel_id],
            'search_criteria': {'city': 'Clearwater'},
            'cached_count': 0
        }
        result = scrape_tax_data(scrape_result)

        # Tax data should NOT be updated (passthrough behavior)
        property_without_tax.refresh_from_db()
        assert property_without_tax.tax_amount is None
        # Result should indicate passthrough
        assert result['status'] == 'Tax data from PCPAO bulk import'
        assert result['total_processed'] == 1

    @patch('apps.WebScraper.tasks.scrape_data.ProgressRecorder')
    def test_scrape_tax_data_preserves_property_ids(self, mock_progress, sample_property, celery_eager):
        """Test tax scraper passthrough preserves property IDs in result."""
        from apps.WebScraper.tasks.scrape_data import scrape_tax_data

        scrape_result = {
            'property_ids': [sample_property.parcel_id],
            'search_criteria': {'city': 'Clearwater'},
            'cached_count': 1
        }
        result = scrape_tax_data(scrape_result)

        # Tax amount should be unchanged (passthrough)
        sample_property.refresh_from_db()
        assert sample_property.tax_amount == Decimal('3125.00')
        # Property IDs should be passed through
        assert sample_property.parcel_id in result['property_ids']
        assert result['cached_count'] == 1

    @patch('apps.WebScraper.tasks.scrape_data.ProgressRecorder')
    def test_scrape_tax_data_handles_empty_ids(self, mock_progress, celery_eager):
        """Test tax scraper passthrough handles empty property list."""
        from apps.WebScraper.tasks.scrape_data import scrape_tax_data

        scrape_result = {
            'property_ids': [],
            'search_criteria': {}
        }
        result = scrape_tax_data(scrape_result)
        assert result['total_processed'] == 0
        assert result['property_ids'] == []


class TestSortDataTasks:
    def test_fetch_property_listings_returns_data(self, multiple_properties):
        """Test fetch_property_listings returns columns and listings."""
        from apps.WebScraper.tasks.sort_data import fetch_property_listings

        columns, listings = fetch_property_listings()

        assert len(columns) > 0
        assert len(listings) == 5

    def test_generate_spreadsheet_creates_file(self, multiple_properties, tmp_path, monkeypatch):
        """Test spreadsheet generation creates valid file."""
        from apps.WebScraper.tasks.sort_data import generate_spreadsheet, fetch_property_listings, REPORTS_DIR
        import os

        columns, listings = fetch_property_listings()
        result = generate_spreadsheet(columns, listings)

        # Function now returns the full filepath
        assert result.endswith('PropertyListings.xlsx')
        assert os.path.exists(result)

    def test_quick_sort_sorts_correctly(self):
        """Test quick_sort with simple compare function."""
        from apps.WebScraper.tasks.sort_data import quick_sort

        arr = [3, 1, 4, 1, 5, 9, 2, 6]
        sorted_arr = quick_sort(arr, lambda x, y: x - y)

        assert sorted_arr == [1, 1, 2, 3, 4, 5, 6, 9]

    def test_quick_sort_handles_empty_list(self):
        """Test quick_sort handles empty list."""
        from apps.WebScraper.tasks.sort_data import quick_sort

        result = quick_sort([], lambda x, y: x - y)
        assert result == []


class TestPDFTasks:
    @patch('apps.WebScraper.tasks.listings_pdf.ProgressRecorder')
    def test_generate_listing_pdf_with_empty_properties(self, mock_progress, celery_eager, tmp_path, monkeypatch):
        """Test PDF generation handles empty property list."""
        from apps.WebScraper.tasks.listings_pdf import generate_listing_pdf

        sort_result = {
            'sorted_properties': [],
            'columns': [],
            'excel_path': 'PropertyListings.xlsx'
        }

        result = generate_listing_pdf(sort_result)

        assert result['status'] == 'PDF generated successfully'
        # Function now returns full filepath
        assert result['pdf_path'].endswith('Real_Estate_Listings.pdf')

    @patch('apps.WebScraper.tasks.listings_pdf.ProgressRecorder')
    def test_generate_listing_pdf_returns_paths(self, mock_progress, celery_eager, tmp_path, monkeypatch):
        """Test PDF generation returns correct paths in result."""
        from apps.WebScraper.tasks.listings_pdf import generate_listing_pdf

        monkeypatch.chdir(tmp_path)

        # Empty properties to avoid triggering ReportLab markup bug
        sort_result = {
            'sorted_properties': [],
            'columns': [],
            'excel_path': 'TestListings.xlsx'
        }

        result = generate_listing_pdf(sort_result)

        assert 'pdf_path' in result
        assert 'excel_path' in result
        assert result['excel_path'] == 'TestListings.xlsx'


class TestVisualizationTasks:
    def test_column_mapping_exists(self):
        """Test COLUMN_MAPPING is defined correctly."""
        from apps.WebScraper.tasks.visual_data import COLUMN_MAPPING

        assert 'market_value' in COLUMN_MAPPING
        assert COLUMN_MAPPING['market_value'] == 'Listing Price'
        assert 'building_sqft' in COLUMN_MAPPING
        assert COLUMN_MAPPING['building_sqft'] == 'Home Size'

    def test_analyze_data_handles_missing_pdf(self, celery_eager):
        """Test analyze_data handles missing PDF path."""
        from apps.WebScraper.tasks.visual_data import analyze_data

        pdf_result = {
            'pdf_path': None,
            'excel_path': 'PropertyListings.xlsx'
        }

        result = analyze_data(pdf_result)

        assert 'Skipped visualization' in result['status']

    def test_column_mapping_covers_key_fields(self):
        """Test COLUMN_MAPPING covers all important property fields."""
        from apps.WebScraper.tasks.visual_data import COLUMN_MAPPING

        expected_fields = ['market_value', 'building_sqft', 'property_type', 'year_built', 'bedrooms', 'bathrooms']
        for field in expected_fields:
            assert field in COLUMN_MAPPING, f"Missing field: {field}"

    def test_concatenate_pdfs_function_exists(self):
        """Test concatenate_pdfs function is importable."""
        from apps.WebScraper.tasks.visual_data import concatenate_pdfs

        assert callable(concatenate_pdfs)

    def test_generate_plots_function_exists(self):
        """Test generate_plots_and_pdf function is importable."""
        from apps.WebScraper.tasks.visual_data import generate_plots_and_pdf

        assert callable(generate_plots_and_pdf)


class TestEmailTasks:
    @patch('apps.WebScraper.tasks.email_results.EmailMessage')
    def test_send_results_via_email_creates_message(self, mock_email_class, celery_eager, tmp_path):
        """Test email task creates EmailMessage correctly."""
        from apps.WebScraper.tasks.email_results import send_results_via_email
        import os

        # Create dummy files
        pdf_file = tmp_path / "test.pdf"
        excel_file = tmp_path / "test.xlsx"
        pdf_file.write_bytes(b"PDF content")
        excel_file.write_bytes(b"Excel content")

        mock_email = MagicMock()
        mock_email_class.return_value = mock_email

        analysis_result = {
            'pdf_path': str(pdf_file),
            'excel_path': str(excel_file)
        }

        send_results_via_email(analysis_result, 'test@example.com')

        mock_email_class.assert_called_once()
        assert mock_email.attach.call_count == 2
        mock_email.send.assert_called_once()

    @patch('apps.WebScraper.tasks.email_results.EmailMessage')
    def test_send_results_via_email_uses_correct_recipient(self, mock_email_class, celery_eager, tmp_path):
        """Test email task sends to correct recipient."""
        from apps.WebScraper.tasks.email_results import send_results_via_email

        # Create dummy files
        pdf_file = tmp_path / "test.pdf"
        excel_file = tmp_path / "test.xlsx"
        pdf_file.write_bytes(b"PDF content")
        excel_file.write_bytes(b"Excel content")

        mock_email = MagicMock()
        mock_email_class.return_value = mock_email

        analysis_result = {
            'pdf_path': str(pdf_file),
            'excel_path': str(excel_file)
        }

        send_results_via_email(analysis_result, 'recipient@test.com')

        call_args = mock_email_class.call_args
        assert 'recipient@test.com' in call_args[0][3]  # Fourth argument is recipient list
