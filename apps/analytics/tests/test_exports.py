"""Direct tests for the Excel/PDF export builders and their error handling."""

from io import BytesIO

import openpyxl
import pytest
from django.test import RequestFactory

from apps.analytics.models import PropertyListing
from apps.analytics.services import exports
from apps.analytics.services.exports import generate_excel_response, generate_pdf_response

pytestmark = pytest.mark.django_db

rf = RequestFactory()


def _boom(*args, **kwargs):
    raise RuntimeError('kaboom')


@pytest.fixture
def some_parcels(db):
    for i in range(5):
        PropertyListing.objects.create(
            parcel_id=f'exp-{i:03d}',
            address=f'{i} Export Ave',
            city='Clearwater',
            zip_code='33755',
            property_type='Single Family Home',
            market_value=200000 + i * 50000,
            assessed_value=180000 + i * 40000,
            building_sqft=1200 + i * 100,
            year_built=1990 + i,
            tax_amount=2000 + i * 100,
        )


class TestExcelExport:
    def test_workbook_has_expected_sheets(self, some_parcels):
        response = generate_excel_response()

        assert response.status_code == 200
        assert 'spreadsheetml' in response['Content-Type']
        wb = openpyxl.load_workbook(BytesIO(response.content))
        assert wb.sheetnames == [
            'Overview',
            'City Segments',
            'Property Type Segments',
            'Outliers',
            'Sample Parcels',
            'Methodology',
        ]

    def test_generation_failure_returns_friendly_error(self, monkeypatch):
        monkeypatch.setattr(exports, 'build_market_insights', _boom)

        response = generate_excel_response()

        assert response.status_code == 500
        assert b"couldn't generate" in response.content


class TestPdfExport:
    def test_pdf_has_correct_content_type_and_nonempty_body(self, some_parcels):
        response = generate_pdf_response()

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert response.content[:5] == b'%PDF-'
        assert len(response.content) > 1000

    def test_generation_failure_returns_friendly_error(self, monkeypatch):
        monkeypatch.setattr(exports, 'build_market_insights', _boom)

        response = generate_pdf_response()

        assert response.status_code == 500
        assert b"couldn't generate" in response.content


@pytest.mark.parametrize('generate', [generate_excel_response, generate_pdf_response])
class TestExportFailureDoesNotRedirectIntoDashboard:
    """build_market_insights is shared with insights_dashboard, which has no
    try/except of its own — redirecting a failed export back to /insights/
    would just trigger the same crash there, unhandled. The error response
    must stand alone (no redirect) even when a real request is provided."""

    def test_with_a_real_request_the_response_is_a_standalone_error_not_a_redirect(self, monkeypatch, generate):
        monkeypatch.setattr(exports, 'build_market_insights', _boom)

        response = generate(rf.get('/analytics/download/excel/'))

        assert response.status_code == 500
        assert response.get('Location') is None
        assert b"couldn't generate" in response.content
