from __future__ import annotations

import logging

from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from home_finder.caching import cdn_cache

logger = logging.getLogger(__name__)


# Each filtered insights view and each export rebuilds the analysis from about
# 50,000 database rows, and the database has a monthly data-transfer quota.
# Crawlers get the default pages only.
ROBOTS_TXT = """User-agent: *
Disallow: /insights/?
Disallow: /lookup/?
Disallow: /analytics/compare/
Disallow: /analytics/download/
Disallow: /analytics/dashboard/
Disallow: /scraper/
Disallow: /admin/
"""


@cdn_cache
def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type='text/plain')


@cdn_cache
def home(request):
    return render(request, 'Pages/home.html')


@cdn_cache
def about(request):
    return render(request, 'Pages/about.html')


@cdn_cache
def help(request):
    return render(request, 'Pages/help.html')


def health_check(request):
    """Health check endpoint for monitoring and uptime checks."""
    status = {'status': 'ok', 'checks': {}}

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        status['checks']['database'] = 'ok'
    except Exception as exc:
        logger.error('Health check database failure: %s', exc)
        status['checks']['database'] = 'error'
        status['status'] = 'degraded'

    # Database-cache check
    try:
        from django.core.cache import cache

        cache.set('_health_check', '1', timeout=10)
        if cache.get('_health_check') == '1':
            status['checks']['cache'] = 'ok'
        else:
            status['checks']['cache'] = 'error'
            status['status'] = 'degraded'
    except Exception as exc:
        logger.error('Health check cache failure: %s', exc)
        status['checks']['cache'] = 'error'
        status['status'] = 'degraded'

    http_status = 200 if status['status'] == 'ok' else 503
    return JsonResponse(status, status=http_status)


def api_status(request):
    """Public status endpoint showing basic system stats."""
    from apps.analytics.models import PropertyListing

    total = PropertyListing.objects.count()
    latest = PropertyListing.objects.order_by('-last_scraped').values_list('last_scraped', flat=True).first()

    return JsonResponse(
        {
            'total_properties': total,
            'last_updated': latest.isoformat() if latest else None,
        }
    )
