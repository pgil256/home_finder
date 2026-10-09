import re

import pytest

from home_finder import settings

pytestmark = pytest.mark.django_db


class TestPagesViews:
    def test_home_page_renders(self, client):
        """Test home page returns 200."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Pinellas Market Lens' in response.content

    def test_home_page_leads_with_the_address_lookup(self, client):
        html = client.get('/').content.decode()

        assert 'What will this home really cost me' in html
        assert 'action="/lookup/"' in html
        assert 'name="q"' in html
        assert 'Not a listing search' not in html
        # The address box comes before the line about how the site is built.
        assert html.index('action="/lookup/"') < html.index('Built on 437,000 county records')

    def test_nav_puts_lookup_before_the_dashboard(self, client):
        html = client.get('/').content.decode()

        assert html.index('Look up a home') < html.index('Explore the market')

    def test_robots_keeps_crawlers_off_lookup_queries(self, client):
        assert b'Disallow: /lookup/?' in client.get('/robots.txt').content

    def test_home_page_is_for_buyers_and_points_to_how_it_is_built(self, client):
        html = client.get('/').content.decode()

        assert 'Built on 437,000 county records, refreshed monthly' in html
        assert 'Engineering proof at a glance' not in html
        assert 'pandas' not in html
        assert 'https://github.com/pgil256/home_finder' in html

    def test_about_page_carries_the_engineering_story(self, client):
        html = client.get('/about/').content.decode()

        assert 'Engineering proof at a glance' in html
        assert '437K+ parcels' in html
        assert 'pandas + numpy' in html

    def test_about_page_renders(self, client):
        """Test about page returns 200."""
        response = client.get('/about/')
        assert response.status_code == 200

    def test_help_page_renders(self, client):
        """Test help page returns 200."""
        response = client.get('/help')
        assert response.status_code == 200

    def test_help_page_is_the_first_time_buyer_guide(self, client):
        html = client.get('/help').content.decode()

        assert 'Buying your first home in Pinellas County' in html
        for section in ('steps', 'florida', 'assistance', 'glossary'):
            assert f'id="{section}"' in html
        assert 'https://www.floridahousing.org/' in html
        assert 'action="/lookup/"' in html
        assert 'From filters to' not in html

    def test_guide_describes_amendment_3_by_its_status(self, client, monkeypatch):
        from apps.Pages import views

        assert 'on the November 3, 2026 ballot' in client.get('/help').content.decode()

        monkeypatch.setattr(views, 'AMENDMENT_3_STATUS', 'passed')
        assert 'approved by voters' in client.get('/help').content.decode()

        monkeypatch.setattr(views, 'AMENDMENT_3_STATUS', 'failed')
        html = client.get('/help').content.decode()
        assert 'Amendment 3' not in html

    def test_parcel_page_glossary_links_have_a_definition(self):
        parcel_page = (settings.BASE_DIR / 'templates/analytics/property-detail.html').read_text()
        glossary = (settings.BASE_DIR / 'templates/Pages/partials/glossary.html').read_text()

        linked = set(re.findall(r"\{% url 'help' %\}#term-([a-z-]+)", parcel_page))
        defined = set(re.findall(r'id="term-([a-z-]+)"', glossary))

        assert len(linked) >= 10
        assert linked <= defined

    def test_home_page_links_to_the_guide(self, client):
        html = client.get('/').content.decode()

        assert 'href="/help"' in html
        assert "Read the buyer's guide" in html

    def test_nav_names_the_guide(self, client):
        assert "Buyer's guide" in client.get('/').content.decode()

    def test_home_uses_home_template(self, client):
        """Test home page opens on the product intro, not the analytics dashboard."""
        response = client.get('/')
        assert 'Pages/home.html' in [t.name for t in response.templates]
        assert b'The market at a glance' not in response.content

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

    def test_vercel_custom_hosts_include_canonical_and_alias(self):
        allowed_hosts = []
        trusted_origins = []

        settings._append_vercel_custom_hosts(allowed_hosts, trusted_origins)

        assert allowed_hosts == [
            'homefinder.patbuilds.dev',
            'pinellasmarketlens.patbuilds.dev',
        ]
        assert trusted_origins == [
            'https://homefinder.patbuilds.dev',
            'https://pinellasmarketlens.patbuilds.dev',
        ]
