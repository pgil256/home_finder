"""Unit tests for the server-side Street View helpers (the API key must stay
on the server; these functions build/fetch with it but never expose it)."""

import requests
from django.test import override_settings

from apps.analytics.services import street_view as sv


class _FakeResponse:
    def __init__(self, *, content=b'', json_data=None, content_type='image/jpeg'):
        self.content = content
        self._json = json_data or {}
        self.headers = {'Content-Type': content_type}

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class TestGetStreetViewUrl:
    @override_settings(GOOGLE_STREET_VIEW_API_KEY='')
    def test_returns_none_without_api_key(self):
        assert sv.get_street_view_url('123 Main St', 'Clearwater', '33755') is None

    @override_settings(GOOGLE_STREET_VIEW_API_KEY='test-key')
    def test_returns_none_without_address(self):
        assert sv.get_street_view_url('', 'Clearwater', '33755') is None

    @override_settings(GOOGLE_STREET_VIEW_API_KEY='test-key')
    def test_builds_url_with_key_when_imagery_exists(self, monkeypatch):
        monkeypatch.setattr(sv, '_has_street_view_imagery', lambda location, api_key: True)

        url = sv.get_street_view_url('123 Main St', 'Clearwater', '33755', '640x360')

        assert url.startswith('https://maps.googleapis.com/maps/api/streetview?')
        assert 'key=test-key' in url

    @override_settings(GOOGLE_STREET_VIEW_API_KEY='test-key')
    def test_returns_none_when_no_imagery(self, monkeypatch):
        monkeypatch.setattr(sv, '_has_street_view_imagery', lambda location, api_key: False)

        assert sv.get_street_view_url('123 Main St', 'Clearwater', '33755') is None


class TestFetchStreetViewImage:
    def test_returns_none_when_no_url(self, monkeypatch):
        monkeypatch.setattr(sv, 'get_street_view_url', lambda *a, **k: None)

        assert sv.fetch_street_view_image('123 Main St', 'Clearwater', '33755') is None

    def test_returns_image_bytes_and_content_type(self, monkeypatch):
        monkeypatch.setattr(sv, 'get_street_view_url', lambda *a, **k: 'https://maps.googleapis.com/x?key=k')
        monkeypatch.setattr(
            sv.requests, 'get', lambda *a, **k: _FakeResponse(content=b'\xff\xd8jpegbytes', content_type='image/jpeg')
        )

        result = sv.fetch_street_view_image('123 Main St', 'Clearwater', '33755', '640x360')

        assert result == (b'\xff\xd8jpegbytes', 'image/jpeg')

    def test_returns_none_on_request_failure(self, monkeypatch):
        monkeypatch.setattr(sv, 'get_street_view_url', lambda *a, **k: 'https://maps.googleapis.com/x?key=k')

        def _boom(*a, **k):
            raise requests.RequestException('timeout')

        monkeypatch.setattr(sv.requests, 'get', _boom)

        assert sv.fetch_street_view_image('123 Main St', 'Clearwater', '33755') is None
