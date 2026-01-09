# apps/WebScraper/tests/test_admin.py
import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from apps.WebScraper.admin import PropertyListingAdmin
from apps.WebScraper.models import PropertyListing

pytestmark = pytest.mark.django_db


class TestPropertyListingAdmin:
    @pytest.fixture
    def admin_user(self, db):
        return User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass',
        )

    @pytest.fixture
    def admin_client(self, client, admin_user):
        client.force_login(admin_user)
        return client

    def test_admin_changelist_loads(self, admin_client):
        """Test admin property list page loads."""
        response = admin_client.get('/admin/WebScraper/propertylisting/')
        assert response.status_code == 200

    def test_admin_search_by_parcel(self, admin_client, sample_property):
        """Test admin search functionality."""
        response = admin_client.get(
            '/admin/WebScraper/propertylisting/',
            {'q': sample_property.parcel_id},
        )
        assert response.status_code == 200
        assert sample_property.parcel_id.encode() in response.content

    def test_admin_search_by_address(self, admin_client, sample_property):
        """Test admin search by address."""
        response = admin_client.get(
            '/admin/WebScraper/propertylisting/',
            {'q': 'Main St'},
        )
        assert response.status_code == 200
        assert b'Main St' in response.content

    def test_admin_filter_by_city(self, admin_client, multiple_properties):
        """Test admin filter by city."""
        response = admin_client.get(
            '/admin/WebScraper/propertylisting/',
            {'city': 'Clearwater'},
        )
        assert response.status_code == 200

    def test_admin_filter_by_property_type(self, admin_client, multiple_properties):
        """Test admin filter by property type."""
        response = admin_client.get(
            '/admin/WebScraper/propertylisting/',
            {'property_type': 'Single Family'},
        )
        assert response.status_code == 200

    def test_admin_filter_by_tax_status(self, admin_client, sample_property):
        """Test admin filter by tax status."""
        response = admin_client.get(
            '/admin/WebScraper/propertylisting/',
            {'tax_status': 'Paid'},
        )
        assert response.status_code == 200

    def test_admin_add_page_loads(self, admin_client):
        """Test admin add property page loads."""
        response = admin_client.get('/admin/WebScraper/propertylisting/add/')
        assert response.status_code == 200

    def test_admin_change_page_loads(self, admin_client, sample_property):
        """Test admin change property page loads."""
        response = admin_client.get(
            f'/admin/WebScraper/propertylisting/{sample_property.pk}/change/'
        )
        assert response.status_code == 200

    def test_admin_displays_list_columns(self, admin_client, sample_property):
        """Test admin list displays expected columns."""
        response = admin_client.get('/admin/WebScraper/propertylisting/')

        # Check that key data is displayed
        content = response.content.decode()
        assert sample_property.parcel_id in content
        assert sample_property.address in content
        assert sample_property.city in content

    def test_admin_readonly_fields(self, admin_client, sample_property):
        """Test that readonly fields are displayed correctly."""
        response = admin_client.get(
            f'/admin/WebScraper/propertylisting/{sample_property.pk}/change/'
        )
        content = response.content.decode()

        # last_scraped and created_at should be readonly
        # They should appear in the form but not as editable inputs
        assert 'last_scraped' in content.lower() or 'Last scraped' in content
        assert 'created_at' in content.lower() or 'Created at' in content


class TestAdminSiteConfiguration:
    """Test admin site configuration."""

    @pytest.fixture
    def admin_user(self, db):
        return User.objects.create_superuser(
            username='admin2',
            email='admin2@test.com',
            password='adminpass2',
        )

    @pytest.fixture
    def admin_client(self, client, admin_user):
        client.force_login(admin_user)
        return client

    def test_admin_index_loads(self, admin_client):
        """Test admin index page loads."""
        response = admin_client.get('/admin/')
        assert response.status_code == 200

    def test_property_listing_registered(self, admin_client):
        """Test PropertyListing is registered in admin."""
        response = admin_client.get('/admin/')
        assert b'Property listings' in response.content or b'propertylisting' in response.content.lower()

    def test_admin_logout_works(self, admin_client):
        """Test admin logout functionality."""
        response = admin_client.post('/admin/logout/')
        # Should redirect after logout
        assert response.status_code in [200, 302]
