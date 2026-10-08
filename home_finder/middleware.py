"""Project-wide middleware."""

from __future__ import annotations

import logging

from django.db.utils import InterfaceError, OperationalError
from django.http import HttpRequest, HttpResponse
from django.utils.cache import has_vary_header

logger = logging.getLogger(__name__)

# How long to tell clients (and monitors) to wait before retrying.
RETRY_AFTER_SECONDS = 300

_MAINTENANCE_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Temporarily unavailable · Pinellas Market Lens</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 32rem; margin: 4rem auto; padding: 0 1.5rem; color: #1f2933;">
<h1>Temporarily unavailable</h1>
<p>The property database isn't reachable right now, so market data can't be loaded. This is usually brief — please try again in a few minutes.</p>
</body>
</html>"""


class DatabaseUnavailableMiddleware:
    """Turn database *connection* failures into 503s instead of opaque 500s.

    Connectivity problems — the host being unreachable, credentials rejected,
    connection limits, a provider suspending the instance for exceeding a quota
    — are not application bugs, and reporting them as 500 makes an outage look
    identical to a code defect. A 503 with Retry-After says "the app is fine,
    its dependency isn't", which is what both a browser and a monitor need.

    Deliberately narrow: only OperationalError and InterfaceError are treated
    this way. ProgrammingError, IntegrityError and DataError mean the code or
    schema is genuinely wrong and must keep surfacing as 500 so they get fixed.

    Note that ``process_exception`` only fires for exceptions raised inside the
    view. A query evaluated lazily during template rendering escapes this hook,
    which is a good reason for views to force evaluation before returning.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse | None:
        if not isinstance(exception, OperationalError | InterfaceError):
            return None

        logger.error(
            'Database unavailable while serving %s %s: %s',
            request.method,
            request.path,
            exception,
            exc_info=True,
        )

        response = HttpResponse(
            _MAINTENANCE_HTML,
            status=503,
            content_type='text/html; charset=utf-8',
        )
        response['Retry-After'] = str(RETRY_AFTER_SECONDS)
        return response


class PrivateWhenPersonalMiddleware:
    """Keep a response out of the CDN when it turned out to be for one visitor.

    Views opt in to CDN caching with ``cdn_cache``, but whether a response is
    really the same for everyone is only known after the session, CSRF and
    messages middleware have run: a flash message being shown, or a cookie
    being set, makes it personal. This sits first in MIDDLEWARE so it sees the
    finished response, and withdraws the public caching in those cases.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if 'public' not in response.get('Cache-Control', ''):
            return response
        if response.cookies or has_vary_header(response, 'Cookie'):
            response['Cache-Control'] = 'private, no-store'
        return response
