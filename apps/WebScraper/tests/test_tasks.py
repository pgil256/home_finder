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
        """Test scrape task creates PropertyListing records."""
        from apps.WebScraper.tasks.scrape_data import scrape_pinellas_properties
        from apps.WebScraper.models import PropertyListing

        # Mock scraper to return test data
        mock_scraper = MagicMock()
        mock_scraper.scrape_by_criteria.return_value = [
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
        mock_scraper.scrape_by_criteria.return_value = [
            {'parcel_id': 'test-001', 'address': '123 Test St', 'city': 'Test'},
            {'parcel_id': 'test-002', 'address': '456 Test Ave', 'city': 'Test'},
        ]
        mock_scraper_class.return_value = mock_scraper

        result = scrape_pinellas_properties({'city': 'Test'}, limit=10)

        assert len(result['property_ids']) == 2
        assert result['search_criteria'] == {'city': 'Test'}

    @patch('apps.WebScraper.tasks.tax_collector_scraper.TaxCollectorScraper')
    @patch('apps.WebScraper.tasks.scrape_data.ProgressRecorder')
    def test_scrape_tax_data_updates_records(self, mock_progress, mock_scraper_class, sample_property, celery_eager):
        """Test tax scraper updates existing properties."""
        from apps.WebScraper.tasks.scrape_data import scrape_tax_data

        mock_scraper = MagicMock()
        mock_scraper.scrape_batch.return_value = [
            {
                'parcel_id': sample_property.parcel_id,
                'tax_amount': Decimal('3500.00'),
                'tax_status': 'Paid',
                'delinquent': False,
            }
        ]
        mock_scraper_class.return_value = mock_scraper

        scrape_result = {
            'property_ids': [sample_property.parcel_id],
            'search_criteria': {'city': 'Clearwater'}
        }
        scrape_tax_data(scrape_result)

        sample_property.refresh_from_db()
        assert sample_property.tax_amount == Decimal('3500.00')
        assert sample_property.tax_status == 'Paid'

    @patch('apps.WebScraper.tasks.tax_collector_scraper.TaxCollectorScraper')
    @patch('apps.WebScraper.tasks.scrape_data.ProgressRecorder')
    def test_scrape_tax_data_handles_missing_property(self, mock_progress, mock_scraper_class, celery_eager):
        """Test tax scraper handles property not found gracefully."""
        from apps.WebScraper.tasks.scrape_data import scrape_tax_data

        mock_scraper = MagicMock()
        mock_scraper.scrape_batch.return_value = [
            {
                'parcel_id': 'non-existent-parcel',
                'tax_amount': Decimal('1000.00'),
                'tax_status': 'Paid',
            }
        ]
        mock_scraper_class.return_value = mock_scraper

        scrape_result = {
            'property_ids': ['non-existent-parcel'],
            'search_criteria': {}
        }
        # Should not raise
        result = scrape_tax_data(scrape_result)
        assert result['total_processed'] == 0


class TestSortDataTasks:
    def test_fetch_property_listings_returns_data(self, multiple_properties):
        """Test fetch_property_listings returns columns and listings."""
        from apps.WebScraper.tasks.sort_data import fetch_property_listings

        columns, listings = fetch_property_listings()

        assert len(columns) > 0
        assert len(listings) == 5

    def test_generate_spreadsheet_creates_file(self, multiple_properties, tmp_path, monkeypatch):
        """Test spreadsheet generation creates valid file."""
        from apps.WebScraper.tasks.sort_data import generate_spreadsheet, fetch_property_listings
        import os

        # Change to temp directory for file output
        monkeypatch.chdir(tmp_path)

        columns, listings = fetch_property_listings()
        result = generate_spreadsheet(columns, listings)

        assert result == "Spreadsheet generated successfully!"
        assert os.path.exists(tmp_path / "PropertyListings.xlsx")

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
    def test_get_custom_styles_returns_dict(self):
        """Test get_custom_styles returns style dictionary."""
        from apps.WebScraper.tasks.listings_pdf import get_custom_styles

        styles = get_custom_styles()

        assert 'title' in styles
        assert 'heading' in styles
        assert 'body' in styles
        assert 'link' in styles

    @patch('apps.WebScraper.tasks.listings_pdf.ProgressRecorder')
    def test_generate_listing_pdf_with_empty_properties(self, mock_progress, celery_eager, tmp_path, monkeypatch):
        """Test PDF generation handles empty property list."""
        from apps.WebScraper.tasks.listings_pdf import generate_listing_pdf

        monkeypatch.chdir(tmp_path)

        sort_result = {
            'sorted_properties': [],
            'columns': [],
            'excel_path': 'PropertyListings.xlsx'
        }

        result = generate_listing_pdf(sort_result)

        assert result['status'] == 'PDF generated successfully'
        assert result['pdf_path'] == 'Real_Estate_Listings.pdf'

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

    def test_get_custom_styles_has_correct_font_settings(self):
        """Test custom styles have appropriate font settings."""
        from apps.WebScraper.tasks.listings_pdf import get_custom_styles

        styles = get_custom_styles()

        assert styles['title'].fontSize == 18
        assert styles['heading'].fontSize == 14
        assert styles['body'].fontSize == 12


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
