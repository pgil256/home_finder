"""Unit tests for the cache-backed rate-limit helpers used by property_refresh
and the export downloads."""

from django.test import RequestFactory

from apps.analytics.services import task_management as tm

rf = RequestFactory()


class TestGetClientIp:
    def test_prefers_x_forwarded_for(self):
        request = rf.get('/', HTTP_X_FORWARDED_FOR='203.0.113.5, 10.0.0.1')
        assert tm.get_client_ip(request) == '203.0.113.5'

    def test_falls_back_to_remote_addr(self):
        request = rf.get('/', REMOTE_ADDR='127.0.0.1')
        assert tm.get_client_ip(request) == '127.0.0.1'


class TestCheckRateLimit:
    def test_first_call_is_allowed_and_starts_the_window(self, db):
        assert tm.check_rate_limit('1.2.3.4', bucket='test_bucket') is None

    def test_second_call_within_window_is_blocked_with_seconds_remaining(self, db):
        tm.check_rate_limit('1.2.3.4', bucket='test_bucket', window_seconds=60)

        wait = tm.check_rate_limit('1.2.3.4', bucket='test_bucket', window_seconds=60)

        assert wait is not None
        assert 0 < wait <= 60

    def test_buckets_are_independent(self, db):
        tm.check_rate_limit('1.2.3.4', bucket='bucket_a', window_seconds=60)

        assert tm.check_rate_limit('1.2.3.4', bucket='bucket_b', window_seconds=60) is None

    def test_different_ips_are_independent(self, db):
        tm.check_rate_limit('1.2.3.4', bucket='shared_bucket', window_seconds=60)

        assert tm.check_rate_limit('5.6.7.8', bucket='shared_bucket', window_seconds=60) is None

    def test_cache_failures_fail_open(self, db, monkeypatch):
        def _boom(*args, **kwargs):
            raise ConnectionError('cache unavailable')

        monkeypatch.setattr(tm.cache, 'get', _boom)
        monkeypatch.setattr(tm.cache, 'set', _boom)

        assert tm.check_rate_limit('1.2.3.4', bucket='test_bucket') is None
