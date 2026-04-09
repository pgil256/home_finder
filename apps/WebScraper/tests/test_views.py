import pytest
from decimal import Decimal
from django.core.cache import cache as django_cache
from django.test import Client
from django.urls import reverse
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Django cache before each test to avoid rate limit interference."""
    django_cache.clear()
    yield
    django_cache.clear()


class TestWebScraperViews:
    def test_scraper_page_get(self, client):
        """Test GET request to scraper page returns form."""
        response = client.get('/scraper/')
        assert response.status_code == 200

    def test_scraper_page_uses_correct_template(self, client):
        """Test scraper page uses the correct template."""
        response = client.get('/scraper/')
        assert 'WebScraper/search.html' in [t.name for t in response.templates]

    @patch('apps.WebScraper.views.build_processing_pipeline')
    def test_scraper_page_post_starts_task(self, mock_task, client):
        """Test POST starts Celery task pipeline."""
        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.return_value = mock_result

        response = client.post('/scraper/', {
            'city': 'Clearwater',
            'property_type': 'Single Family',
            'limit': '10',
        })

        # Should redirect to progress page
        assert response.status_code == 302
        assert 'progress/test-task-id' in response.url

    @patch('apps.WebScraper.views.build_processing_pipeline')
    def test_scraper_post_passes_search_criteria(self, mock_task, client):
        """Test POST passes correct search criteria to task."""
        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.return_value = mock_result

        client.post('/scraper/', {
            'city': 'St Petersburg',
            'zip_code': '33701',
            'property_type': 'Condo',
            'limit': '25',
        })

        # Verify build_processing_pipeline was called
        mock_task.assert_called_once()
        call_args = mock_task.call_args
        search_criteria = call_args[0][0]  # First positional argument
        assert search_criteria['city'] == 'St Petersburg'
        assert search_criteria['zip_code'] == '33701'
        assert search_criteria['property_type'] == 'Condo'

    def test_progress_page_renders(self, client):
        """Test progress page renders with task_id."""
        response = client.get('/scraper/progress/test-task-123/')
        assert response.status_code == 200

    def test_progress_page_contains_task_id(self, client):
        """Test progress page has task_id in context."""
        response = client.get('/scraper/progress/test-task-123/')
        assert response.context['task_id'] == 'test-task-123'

    @patch('apps.WebScraper.services.task_management.AsyncResult')
    def test_task_status_api_pending(self, mock_async_result, client):
        """Test task status API returns JSON for pending task."""
        mock_result = MagicMock()
        mock_result.state = 'PENDING'
        mock_async_result.return_value = mock_result

        response = client.get('/scraper/status/test-task-123/')

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'
        data = response.json()
        assert data['state'] == 'PENDING'
        assert data['current'] == 0

    @patch('apps.WebScraper.services.task_management.AsyncResult')
    def test_task_status_api_progress(self, mock_async_result, client):
        """Test task status API returns progress info."""
        mock_result = MagicMock()
        mock_result.state = 'PROGRESS'
        mock_result.info = {'current': 50, 'total': 100, 'status': 'Processing...'}
        mock_async_result.return_value = mock_result

        response = client.get('/scraper/status/test-task-123/')

        data = response.json()
        assert data['state'] == 'PROGRESS'
        assert data['current'] == 50
        assert data['total'] == 100

    @patch('apps.WebScraper.services.task_management.AsyncResult')
    def test_task_status_api_success(self, mock_async_result, client):
        """Test task status API returns result on success."""
        mock_result = MagicMock()
        mock_result.state = 'SUCCESS'
        mock_result.info = {'current': 100, 'total': 100, 'status': 'Complete'}
        mock_result.result = {'properties_found': 10}
        mock_async_result.return_value = mock_result

        response = client.get('/scraper/status/test-task-123/')

        data = response.json()
        assert data['state'] == 'SUCCESS'
        assert data['result'] == {'properties_found': 10}

    @patch('apps.WebScraper.services.task_management.AsyncResult')
    def test_task_status_api_failure(self, mock_async_result, client):
        """Test task status API returns error on failure."""
        mock_result = MagicMock()
        mock_result.state = 'FAILURE'
        mock_result.info = Exception('Test error')
        mock_async_result.return_value = mock_result

        response = client.get('/scraper/status/test-task-123/')

        data = response.json()
        assert data['state'] == 'FAILURE'
        assert 'Test error' in data['status']


class TestExportGuestAccess:
    """Export endpoints are accessible to all users (guest-friendly)."""

    def test_download_excel_works_for_guests(self, client, db):
        response = client.get('/scraper/download/excel/')
        assert response.status_code == 200
        assert 'spreadsheetml' in response['Content-Type']

    def test_download_pdf_works_for_guests(self, client, sample_property):
        response = client.get('/scraper/download/pdf/')
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'


class TestRateLimiting:
    """Scraping submissions are rate limited."""

    @patch('apps.WebScraper.views.build_processing_pipeline')
    def test_rapid_submissions_are_rate_limited(self, mock_task, client):
        from django.core.cache import cache as _cache

        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.return_value = mock_result

        # First submission should succeed
        response = client.post('/scraper/', {'city': 'Clearwater', 'limit': '10'})
        assert response.status_code == 302

        # Verify the rate limit key was set
        assert _cache.get('scrape_rate:127.0.0.1') is not None

        # Second immediate submission should be rate limited (re-renders form)
        response = client.post('/scraper/', {'city': 'Clearwater', 'limit': '10'})
        assert response.status_code == 200  # renders form instead of redirecting
        assert 'error' in response.context
        assert 'Please wait' in response.context['error']


class TestDashboardFilterValidation:
    """Invalid filter values are handled gracefully."""

    def test_invalid_min_price_ignored(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {'min_price': 'not-a-number'})
        assert response.status_code == 200

    def test_invalid_max_price_ignored(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {'max_price': 'abc'})
        assert response.status_code == 200

    def test_invalid_beds_ignored(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {'beds': 'xyz'})
        assert response.status_code == 200

    def test_valid_filters_apply(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {
            'city': 'Clearwater',
            'min_price': '100000',
            'max_price': '500000',
        })
        assert response.status_code == 200
        assert response.context['total_count'] == 1

    def test_filter_excludes_non_matching(self, client, sample_property):
        response = client.get('/scraper/dashboard/', {
            'min_price': '999999',
        })
        assert response.status_code == 200
        assert response.context['total_count'] == 0


class TestTaskStatusEndpoint:
    """Task status endpoint only accepts GET."""

    def test_post_not_allowed(self, client):
        response = client.post('/scraper/status/test-task-123/')
        assert response.status_code == 405
