import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestPagesViews:
    def test_home_page_renders(self, client):
        """Test home page returns 200 and uses correct template."""
        response = client.get('/')
        assert response.status_code == 200

    def test_about_page_renders(self, client):
        """Test about page returns 200."""
        response = client.get('/about/')
        assert response.status_code == 200

    def test_help_page_renders(self, client):
        """Test help page returns 200."""
        response = client.get('/help')
        assert response.status_code == 200

    def test_home_uses_correct_template(self, client):
        """Test home page uses the correct template."""
        response = client.get('/')
        assert 'Pages/home.html' in [t.name for t in response.templates]

    def test_about_uses_correct_template(self, client):
        """Test about page uses the correct template."""
        response = client.get('/about/')
        assert 'Pages/about.html' in [t.name for t in response.templates]

    def test_help_uses_correct_template(self, client):
        """Test help page uses the correct template."""
        response = client.get('/help')
        assert 'Pages/help.html' in [t.name for t in response.templates]
