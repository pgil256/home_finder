import pytest
from django.test import Client
from django.urls import reverse
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.django_db


class TestWebScraperViews:
    def test_scraper_page_get(self, client):
        """Test GET request to scraper page returns form."""
        response = client.get('/scraper/')
        assert response.status_code == 200

    def test_scraper_page_uses_correct_template(self, client):
        """Test scraper page uses the correct template."""
        response = client.get('/scraper/')
        assert 'WebScraper/web-scraper.html' in [t.name for t in response.templates]

    @patch('apps.WebScraper.views.start_processing_pipeline')
    def test_scraper_page_post_starts_task(self, mock_task, client):
        """Test POST starts Celery task."""
        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.apply_async.return_value = mock_result

        response = client.post('/scraper/', {
            'City': 'Clearwater',
            'Property Type': 'Single Family',
            'limit': '10',
        })

        # Should redirect to progress page
        assert response.status_code == 302
        assert 'progress/test-task-id' in response.url

    @patch('apps.WebScraper.views.start_processing_pipeline')
    def test_scraper_post_passes_search_criteria(self, mock_task, client):
        """Test POST passes correct search criteria to task."""
        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.apply_async.return_value = mock_result

        client.post('/scraper/', {
            'City': 'St Petersburg',
            'Location': '33701',
            'Property Type': 'Condo',
            'limit': '25',
        })

        # Verify task was called with search criteria
        mock_task.apply_async.assert_called_once()
        call_args = mock_task.apply_async.call_args
        search_criteria = call_args.kwargs['args'][0]
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

    @patch('apps.WebScraper.views.AsyncResult')
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

    @patch('apps.WebScraper.views.AsyncResult')
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

    @patch('apps.WebScraper.views.AsyncResult')
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

    @patch('apps.WebScraper.views.AsyncResult')
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
