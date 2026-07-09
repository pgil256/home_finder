from __future__ import annotations

import logging
import time
from collections.abc import Callable
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import PropertyListing
from .services.exports import generate_excel_response, generate_pdf_response
from .services.filtering import (
    PINELLAS_CITIES,
    PROPERTY_TYPES,
    apply_filters,
    apply_sorting,
)
from .services.market_insights import build_market_insights
from .services.street_view import fetch_street_view_image
from .services.task_management import check_rate_limit, get_client_ip

# Per-parcel refresh rate limit: 60s between refreshes for the same parcel,
# regardless of who's asking. Prevents one user (or bot) from hammering
# PCPAO for any single property.
REFRESH_RATE_LIMIT_SECONDS = 60

# Export rate limit: exports are unauthenticated and build a workbook/PDF over
# up to 50k rows on every hit, so cap repeat downloads per IP per format.
EXPORT_RATE_LIMIT_SECONDS = 10

# Street View images are proxied through the server so the Google API key never
# reaches the browser. Only known parcels and these fixed sizes are served, so
# it can't be used as an open image proxy. Fetched images are cached to avoid
# re-billing Google for repeat views; "no imagery" is cached briefly so dead
# parcels aren't re-checked on every page load.
STREET_VIEW_SIZES = frozenset({'1024x576', '640x360', '320x240'})
STREET_VIEW_DEFAULT_SIZE = '640x360'
STREET_VIEW_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days for a real image
STREET_VIEW_MISS_CACHE_TTL = 60 * 60 * 24  # 1 day for "no imagery"
STREET_VIEW_NO_IMAGE = 'NO_IMAGE'

logger = logging.getLogger(__name__)

# Form fields whose names already match the dashboard's apply_filters params.
# property_type is handled separately because it's multi-value.
SEARCH_SESSION_KEY = 'last_property_search'

SEARCH_FIELDS = (
    'q',
    'city',
    'zip_code',
    'min_price',
    'max_price',
    'year_built',
    'min_sqft',
    'max_sqft',
    'min_lot_sqft',
    'max_lot_sqft',
    'min_tax_amount',
    'max_tax_amount',
)
# beds/baths intentionally excluded — PCPAO doesn't expose this data.


def _empty_search_values() -> dict[str, str | list[str]]:
    values: dict[str, str | list[str]] = {field: '' for field in SEARCH_FIELDS}
    values['property_type'] = []
    return values


def _search_values_from_querydict(data: QueryDict) -> dict[str, str | list[str]]:
    values = _empty_search_values()
    for field in SEARCH_FIELDS:
        values[field] = data.get(field, '').strip()
    values['property_type'] = [property_type for property_type in data.getlist('property_type') if property_type]
    return values


def _search_params_from_values(values: dict[str, str | list[str]]) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    for field in SEARCH_FIELDS:
        value = values.get(field)
        if isinstance(value, str) and value:
            params.append((field, value))
    for property_type in values.get('property_type', []):
        if property_type:
            params.append(('property_type', property_type))
    return params


def _initial_search_values(request) -> dict[str, str | list[str]]:
    if any(field in request.GET for field in (*SEARCH_FIELDS, 'property_type')):
        values = _search_values_from_querydict(request.GET)
        request.session[SEARCH_SESSION_KEY] = values
        return values

    stored = request.session.get(SEARCH_SESSION_KEY, {})
    values = _empty_search_values()
    for field in SEARCH_FIELDS:
        stored_value = stored.get(field, '')
        values[field] = stored_value if isinstance(stored_value, str) else ''
    property_types = stored.get('property_type', [])
    values['property_type'] = property_types if isinstance(property_types, list) else []
    return values


def _search_url_from_values(values: dict[str, str | list[str]]) -> str:
    params = _search_params_from_values(values)
    url = reverse('scraper')
    if params:
        url += '?' + urlencode(params)
    return url


def _dashboard_querydict(request) -> QueryDict:
    """Return dashboard params that still map to buyer-facing filters.

    Old/shared links may arrive with removed fields like assessed value or
    tax status. Keep the visible dashboard links from carrying those dead
    params forward into exports, pagination, or active-filter chip URLs.
    """
    query = QueryDict(mutable=True)
    values = _search_values_from_querydict(request.GET)
    for key, value in _search_params_from_values(values):
        query.appendlist(key, value)
    sort = request.GET.get('sort', '').strip()
    if sort:
        query['sort'] = sort
    if request.GET.get('include_all') == '1':
        query['include_all'] = '1'
    return query


def _dashboard_query_without(request, *keys: str) -> str:
    query = _dashboard_querydict(request)
    for key in keys:
        query.pop(key, None)
    return query.urlencode()


def _range_label(prefix: str, low: str | None, high: str | None, unit: str = '') -> str:
    if low and high:
        return f'{prefix}: {unit}{low} - {unit}{high}'
    if low:
        return f'{prefix}: {unit}{low}+'
    return f'{prefix}: up to {unit}{high}'


def _active_filter_chips(request) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []

    def add(label: str, *remove_keys: str) -> None:
        chips.append(
            {
                'label': label,
                'querystring': _dashboard_query_without(request, *remove_keys),
            }
        )

    get = request.GET
    if get.get('q'):
        add(f'Keyword: {get["q"]}', 'q')
    if get.get('city'):
        add(get['city'], 'city')
    if get.get('zip_code'):
        add(f'ZIP {get["zip_code"]}', 'zip_code')
    property_types = get.getlist('property_type')
    if property_types:
        add(f'Type: {", ".join(property_types)}', 'property_type')
    if get.get('min_price') or get.get('max_price'):
        add(_range_label('Market value', get.get('min_price'), get.get('max_price'), '$'), 'min_price', 'max_price')
    if get.get('year_built'):
        add(f'Built after {get["year_built"]}', 'year_built')
    if get.get('min_sqft') or get.get('max_sqft'):
        add(_range_label('Building size', get.get('min_sqft'), get.get('max_sqft')), 'min_sqft', 'max_sqft')
    if get.get('min_lot_sqft') or get.get('max_lot_sqft'):
        add(_range_label('Lot size', get.get('min_lot_sqft'), get.get('max_lot_sqft')), 'min_lot_sqft', 'max_lot_sqft')
    if get.get('min_tax_amount') or get.get('max_tax_amount'):
        add(
            _range_label('Annual tax', get.get('min_tax_amount'), get.get('max_tax_amount'), '$'),
            'min_tax_amount',
            'max_tax_amount',
        )
    return chips


def web_scraper_view(request):
    """Search form. POST translates form fields to dashboard query params and 302s.

    Searches are now DB queries against the bulk-imported PCPAO data, not live
    scrapes — fast, accurate, no rate limit, no loading state needed.
    """
    if request.method == 'POST':
        search_values = _search_values_from_querydict(request.POST)
        request.session[SEARCH_SESSION_KEY] = search_values
        params = _search_params_from_values(search_values)

        url = reverse('insights')
        if params:
            url += '?' + urlencode(params)
        return redirect(url)

    search_values = _initial_search_values(request)
    return render(
        request,
        'analytics/search.html',
        {
            'cities': sorted(PINELLAS_CITIES),
            'property_types': PROPERTY_TYPES,
            'search_values': search_values,
        },
    )


def property_dashboard(request):
    """Legacy dashboard URL; redirect to the canonical market-insights route."""
    target = reverse('insights')
    query_string = request.META.get('QUERY_STRING')
    if query_string:
        target = f'{target}?{query_string}'
    return redirect(target)


def insights_dashboard(request):
    """Market insights dashboard with filters, KPIs, charts, and drilldowns."""
    properties, selected_types, defaulted_to_residential = apply_filters(request)
    sort = request.GET.get('sort', '-market_value')
    properties = apply_sorting(properties, sort)
    total_count = properties.count()

    city = request.GET.get('city')
    search_criteria = {}
    if city:
        search_criteria['city'] = city
    if selected_types:
        search_criteria['property_types'] = selected_types

    if request.GET:
        request.session[SEARCH_SESSION_KEY] = _search_values_from_querydict(request.GET)

    filter_values = _search_values_from_querydict(request.GET)
    dashboard_qs = _dashboard_querydict(request)

    # Build the "show all property types" URL = current filters + include_all=1
    show_all_qs = dashboard_qs.copy()
    show_all_qs['include_all'] = '1'
    insights = build_market_insights(request)

    return render(
        request,
        'analytics/market-insights.html',
        {
            'insights': insights,
            'charts': insights['charts'],
            'total_count': total_count,
            'cities': sorted(PINELLAS_CITIES),
            'property_types': PROPERTY_TYPES,
            'selected_property_types': selected_types,
            'search_criteria': search_criteria,
            'sort': sort,
            'defaulted_to_residential': defaulted_to_residential,
            'show_all_querystring': show_all_qs.urlencode(),
            'dashboard_querystring': dashboard_qs.urlencode(),
            'filter_values': filter_values,
            'active_filter_chips': _active_filter_chips(request),
            'modify_search_url': _search_url_from_values(filter_values),
            'insights_url': reverse('insights'),
        },
    )


def property_detail(request, parcel_id: str):
    """Single property detail view."""
    property_obj = get_object_or_404(PropertyListing, parcel_id=parcel_id)

    similar_properties = PropertyListing.objects.filter(
        city=property_obj.city,
        property_type=property_obj.property_type,
    ).exclude(parcel_id=parcel_id)

    if property_obj.market_value:
        min_price = float(property_obj.market_value) * 0.8
        max_price = float(property_obj.market_value) * 1.2
        similar_properties = similar_properties.filter(
            market_value__gte=min_price,
            market_value__lte=max_price,
        )

    similar_properties = similar_properties[:4]

    return render(
        request,
        'analytics/property-detail.html',
        {
            'property': property_obj,
            'similar_properties': similar_properties,
        },
    )


def _safe_cache_get(key: str):
    try:
        return cache.get(key)
    except Exception as e:
        logger.warning('Cache GET failed for %s: %s', key, e)
        return None


def _safe_cache_set(key: str, value, timeout: int) -> None:
    try:
        cache.set(key, value, timeout=timeout)
    except Exception as e:
        logger.warning('Cache SET failed for %s: %s', key, e)


def _street_view_response(content: bytes, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    # Let the browser and Vercel's edge cache hold it too, so repeat/CDN hits
    # never reach the origin (or Google) again.
    response['Cache-Control'] = f'public, max-age={STREET_VIEW_CACHE_TTL}'
    return response


def property_streetview(request, parcel_id: str):
    """Proxy a parcel's Street View image, keeping the Google API key server-side.

    Serves cached image bytes for a known parcel at an allowlisted size, or 404
    (so the template's onerror fallback shows the placeholder) when there's no
    imagery, no configured key, or the upstream fetch fails.
    """
    size = request.GET.get('size', STREET_VIEW_DEFAULT_SIZE)
    if size not in STREET_VIEW_SIZES:
        size = STREET_VIEW_DEFAULT_SIZE

    property_obj = get_object_or_404(PropertyListing, parcel_id=parcel_id)
    cache_key = f'street_view_img:{parcel_id}:{size}'

    cached = _safe_cache_get(cache_key)
    if cached == STREET_VIEW_NO_IMAGE:
        raise Http404('No Street View imagery for this parcel.')
    if isinstance(cached, dict):
        return _street_view_response(cached['content'], cached['content_type'])

    result = fetch_street_view_image(property_obj.address, property_obj.city, property_obj.zip_code, size)
    if result is None:
        _safe_cache_set(cache_key, STREET_VIEW_NO_IMAGE, STREET_VIEW_MISS_CACHE_TTL)
        raise Http404('No Street View imagery for this parcel.')

    content, content_type = result
    _safe_cache_set(cache_key, {'content': content, 'content_type': content_type}, STREET_VIEW_CACHE_TTL)
    return _street_view_response(content, content_type)


@require_POST
def property_refresh(request, parcel_id: str):
    """Re-scrape one parcel from PCPAO and update its row in Neon.

    The bulk import refreshes the whole dataset monthly via GitHub Actions,
    so this is for users who want fresh values on a specific listing
    between refreshes (e.g. after a sale).
    """
    from .tasks.scrape_data import ParcelNotFoundError, refresh_one_parcel

    detail_url = reverse('property-detail', args=[parcel_id])
    rate_key = f'parcel_refresh:{parcel_id}'

    # Rate-limit per parcel — 60 seconds between refresh attempts for the
    # same listing. Cache failures fail open (request allowed); the same
    # safe-cache pattern as task_management.py.
    try:
        last = cache.get(rate_key)
    except Exception as e:
        logger.warning('Cache GET failed during refresh: %s', e)
        last = None
    if last:
        wait = int(REFRESH_RATE_LIMIT_SECONDS - (time.time() - last))
        if wait > 0:
            messages.warning(
                request,
                f'This property was just refreshed. Try again in {wait} seconds.',
            )
            return redirect(detail_url)

    try:
        cache.set(rate_key, time.time(), timeout=REFRESH_RATE_LIMIT_SECONDS)
    except Exception as e:
        logger.warning('Cache SET failed during refresh: %s', e)

    try:
        refresh_one_parcel(parcel_id)
    except ParcelNotFoundError:
        messages.error(
            request,
            'Could not find this parcel on the Property Appraiser site. '
            'It may have been retired or the parcel ID changed.',
        )
    except Exception:
        logger.exception('Refresh failed for parcel %s', parcel_id)
        messages.error(
            request,
            'Something went wrong refreshing this property. Please try again in a minute.',
        )
    else:
        messages.success(request, 'Property data refreshed from the County Property Appraiser.')

    return redirect(detail_url)


def _rate_limited_export(
    request: HttpRequest, *, bucket: str, label: str, generate: Callable[[HttpRequest], HttpResponse]
) -> HttpResponse:
    client_ip = get_client_ip(request)
    wait = check_rate_limit(client_ip, bucket=bucket, window_seconds=EXPORT_RATE_LIMIT_SECONDS)
    if wait is not None:
        messages.warning(request, f'Please wait {wait} seconds before downloading another {label}.')
        return redirect(reverse('insights'))
    return generate(request)


def download_excel(request):
    """Generate and serve an Excel file of properties matching the dashboard filters."""
    return _rate_limited_export(request, bucket='export_excel', label='Excel workbook', generate=generate_excel_response)


def download_pdf(request):
    """Generate PDF report of properties matching the dashboard filters."""
    return _rate_limited_export(request, bucket='export_pdf', label='PDF brief', generate=generate_pdf_response)
