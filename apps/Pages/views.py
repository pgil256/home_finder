from __future__ import annotations

import logging

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def home(request):
    return render(request, 'Pages/home.html')


def about(request):
    return render(request, 'Pages/about.html')


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

    # Redis/cache check
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
    from apps.WebScraper.models import PropertyListing

    total = PropertyListing.objects.count()
    latest = PropertyListing.objects.order_by('-last_scraped').values_list('last_scraped', flat=True).first()

    return JsonResponse({
        'total_properties': total,
        'last_updated': latest.isoformat() if latest else None,
    })


