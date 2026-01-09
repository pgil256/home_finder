import pytest
import json
from django.test import Client
from apps.KeywordSelection.models import Keyword

pytestmark = pytest.mark.django_db


class TestKeywordSelectionViews:
    @pytest.fixture
    def keywords(self, db):
        """Create test keywords."""
        return [
            Keyword.objects.create(name='City', priority=1, is_active=True, data_type='select'),
            Keyword.objects.create(name='Price', priority=2, is_active=True, data_type='range'),
            Keyword.objects.create(name='Bedrooms', priority=3, is_active=True, data_type='number'),
        ]

    def test_keyword_selection_page_renders(self, client, keywords):
        """Test keyword selection page returns 200."""
        response = client.get('/keyword/keyword-selection')
        assert response.status_code == 200

    def test_keyword_selection_uses_correct_template(self, client, keywords):
        """Test keyword selection page uses correct template."""
        response = client.get('/keyword/keyword-selection')
        assert 'KeywordSelection/keyword-selection.html' in [t.name for t in response.templates]

    def test_get_keywords_api(self, client, keywords):
        """Test get_keywords API returns all keywords."""
        response = client.get('/keyword/get-keywords/')
        assert response.status_code == 200

        data = response.json()
        assert 'keywords' in data
        assert len(data['keywords']) == 3

    def test_get_keywords_returns_json(self, client, keywords):
        """Test get_keywords returns proper JSON format."""
        response = client.get('/keyword/get-keywords/')
        assert response['Content-Type'] == 'application/json'

        data = response.json()
        # Check structure - should be a list of keyword names
        assert isinstance(data['keywords'], list)
        assert 'City' in data['keywords']

    def test_submit_keyword_order_updates_priorities(self, client, keywords):
        """Test submit_keyword_order updates keyword priorities."""
        new_order = [
            {'name': 'Bedrooms', 'priority': 1},
            {'name': 'City', 'priority': 2},
            {'name': 'Price', 'priority': 3},
        ]

        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'ordered_keywords': new_order}),
            content_type='application/json',
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify priorities updated
        keywords[2].refresh_from_db()  # Bedrooms
        keywords[0].refresh_from_db()  # City
        assert keywords[2].priority == 1  # Bedrooms should now be priority 1
        assert keywords[0].priority == 2  # City should now be priority 2

    def test_submit_keyword_order_returns_redirect_url(self, client, keywords):
        """Test submit_keyword_order returns redirect URL."""
        new_order = [{'name': 'City', 'priority': 1}]

        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'ordered_keywords': new_order}),
            content_type='application/json',
        )

        data = response.json()
        assert 'redirect_url' in data
        assert data['redirect_url'] == '/scraper/'

    def test_submit_keyword_order_validates_input_json_error(self, client):
        """Test submit_keyword_order rejects invalid JSON."""
        response = client.post(
            '/keyword/submit-keyword-order/',
            data='not valid json',
            content_type='application/json',
        )

        assert response.status_code == 400

    def test_submit_keyword_order_validates_input_format(self, client, keywords):
        """Test submit_keyword_order rejects invalid format."""
        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'ordered_keywords': 'not a list'}),
            content_type='application/json',
        )

        assert response.status_code == 400

    def test_submit_keyword_order_rejects_get_request(self, client):
        """Test submit_keyword_order rejects GET requests."""
        response = client.get('/keyword/submit-keyword-order/')

        assert response.status_code == 405

    def test_submit_keyword_order_creates_new_keyword(self, client, db):
        """Test submit_keyword_order can create new keywords."""
        new_order = [
            {'name': 'NewKeyword', 'priority': 1},
        ]

        response = client.post(
            '/keyword/submit-keyword-order/',
            data=json.dumps({'ordered_keywords': new_order}),
            content_type='application/json',
        )

        assert response.status_code == 200
        assert Keyword.objects.filter(name='NewKeyword').exists()
        new_keyword = Keyword.objects.get(name='NewKeyword')
        assert new_keyword.priority == 1
