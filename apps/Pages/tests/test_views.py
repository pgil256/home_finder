import pytest

from home_finder import settings

pytestmark = pytest.mark.django_db


class TestPagesViews:
    def test_home_page_renders(self, client):
        """Test home page returns 200."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Pinellas Market Lens' in response.content

    def test_about_page_renders(self, client):
        """Test about page returns 200."""
        response = client.get('/about/')
        assert response.status_code == 200

    def test_help_page_renders(self, client):
        """Test help page returns 200."""
        response = client.get('/help')
        assert response.status_code == 200

    def test_home_uses_home_template(self, client):
        """Test home page opens on the product intro, not the analytics dashboard."""
        response = client.get('/')
        assert 'Pages/home.html' in [t.name for t in response.templates]
        assert b'Exact Market KPIs' not in response.content

    def test_about_uses_correct_template(self, client):
        """Test about page uses the correct template."""
        response = client.get('/about/')
        assert 'Pages/about.html' in [t.name for t in response.templates]

    def test_help_uses_correct_template(self, client):
        """Test help page uses the correct template."""
        response = client.get('/help')
        assert 'Pages/help.html' in [t.name for t in response.templates]


class TestHealthAndStatus:
    def test_health_check_returns_ok(self, client):
        """Test health endpoint returns 200 with status ok."""
        response = client.get('/health/')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
        assert 'database' in data['checks']
        assert 'cache' in data['checks']

    def test_api_status_returns_property_count(self, client):
        """Test status endpoint returns property count."""
        response = client.get('/api/status/')
        assert response.status_code == 200
        data = response.json()
        assert 'total_properties' in data
        assert 'last_updated' in data


class TestSettingsHelpers:
    def test_bool_config_falls_back_for_invalid_env_values(self, monkeypatch):
        """Deployment discovery should not crash on generic DEBUG collisions."""
        monkeypatch.setenv('DEBUG', 'production')
        assert settings._config_bool('DEBUG', default=False) is False

    def test_bool_config_still_accepts_explicit_truthy_values(self, monkeypatch):
        monkeypatch.setenv('SECURE_SSL_REDIRECT', 'off')
        assert settings._config_bool('SECURE_SSL_REDIRECT', default=True) is False

    def test_csv_config_drops_blank_values(self, monkeypatch):
        monkeypatch.setenv('ALLOWED_HOSTS', 'localhost, 127.0.0.1, , example.com')
        assert settings._config_csv('ALLOWED_HOSTS') == ['localhost', '127.0.0.1', 'example.com']

    def test_append_unique_keeps_first_value(self):
        values = ['localhost']
        settings._append_unique(values, '.vercel.app')
        settings._append_unique(values, '.vercel.app')
        assert values == ['localhost', '.vercel.app']
