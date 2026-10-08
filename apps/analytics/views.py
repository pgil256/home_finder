from __future__ import annotations

import logging
import time
from collections.abc import Callable
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from home_finder.caching import cdn_cache

from .models import PropertyListing, TaxDistrictMillage
from .services.address_lookup import LOOKUP_LIMIT, lookup_parcels
from .services.compare import COMPARE_LIMIT, ComparedHome, build_comparison
from .services.exports import generate_excel_response, generate_pdf_response
from .services.filtering import (
    PINELLAS_CITIES,
    PROPERTY_TYPES,
    apply_filters,
    apply_sorting,
)
from .services.lending_config import affordability_config
from .services.market_insights import build_market_insights
from .services.risk_flags import (
    EVAC_FILTER_CHOICES,
    allowed_evac_zones,
    build_risk_flags,
    evac_filter_label,
    has_risk_data,
)
from .services.task_management import check_rate_limit, get_client_ip
from .services.tax_estimate import build_tax_outlook

# Per-parcel refresh rate limit: 60s between refreshes for the same parcel,
# regardless of who's asking. Prevents one user (or bot) from hammering
# PCPAO for any single property.
REFRESH_RATE_LIMIT_SECONDS = 60

# Export rate limit: exports are unauthenticated and build a workbook/PDF over
# up to 50k rows on every hit, so cap repeat downloads per IP per format.
EXPORT_RATE_LIMIT_SECONDS = 10

logger = logging.getLogger(__name__)

# Form fields whose names already match the dashboard's apply_filters params.
# property_type is handled separately because it's multi-value.
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
    'exclude_evac',
    'exclude_subsidence',
    'max_est_tax',
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


def _cache_busted(url: str, param: str) -> str:
    """Add a timestamp so a redirect lands on a page the CDN hasn't cached.

    A flash message only shows if Django renders the page, and the page after
    a refresh has to show the new values, not yesterday's cached copy.
    """
    separator = '&' if '?' in url else '?'
    return f'{url}{separator}{param}={int(time.time())}'


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
            _range_label('Tax before exemptions', get.get('min_tax_amount'), get.get('max_tax_amount'), '$'),
            'min_tax_amount',
            'max_tax_amount',
        )
    if allowed_evac_zones(get.get('exclude_evac', '')):
        add(evac_filter_label(get['exclude_evac']), 'exclude_evac')
    if get.get('exclude_subsidence') == '1':
        add('No subsidence on record', 'exclude_subsidence')
    if get.get('max_est_tax'):
        add(f'New-owner tax up to ${get["max_est_tax"]}', 'max_est_tax')
    return chips


def web_scraper_view(request):
    """Search form. POST translates form fields to dashboard query params and 302s.

    Searches are now DB queries against the bulk-imported PCPAO data, not live
    scrapes — fast, accurate, no rate limit, no loading state needed.
    """
    if request.method == 'POST':
        search_values = _search_values_from_querydict(request.POST)
        params = _search_params_from_values(search_values)

        url = reverse('insights')
        if params:
            url += '?' + urlencode(params)
        return redirect(url)

    # With no filters in the URL, the page's script restores the last search
    # from the browser's localStorage.
    search_values = _search_values_from_querydict(request.GET)
    return render(
        request,
        'analytics/search.html',
        {
            'cities': sorted(PINELLAS_CITIES),
            'property_types': PROPERTY_TYPES,
            'search_values': search_values,
            'evac_filter_choices': EVAC_FILTER_CHOICES,
            'affordability': affordability_config(),
        },
    )


@cdn_cache
def address_lookup(request):
    """Find a home by street address or parcel ID."""
    result = lookup_parcels(request.GET.get('q'))
    if result.parcel_id:
        return redirect('property-detail', parcel_id=result.parcel_id)
    return render(
        request,
        'analytics/lookup.html',
        {
            'query': result.query,
            'parcels': result.parcels,
            'truncated': result.truncated,
            'lookup_limit': LOOKUP_LIMIT,
        },
    )


def property_dashboard(request):
    """Legacy dashboard URL; redirect to the canonical market-insights route."""
    target = reverse('insights')
    query_string = request.META.get('QUERY_STRING')
    if query_string:
        target = f'{target}?{query_string}'
    return redirect(target)


@cdn_cache
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
            'search_querystring': urlencode(_search_params_from_values(filter_values)),
            'insights_url': reverse('insights'),
            'evac_filter_choices': EVAC_FILTER_CHOICES,
        },
    )


def _parcel_affordability(tax_outlook) -> dict | None:
    """Seed data for the monthly cost calculator, or None without a tax estimate."""
    if tax_outlook is None:
        return None
    config = affordability_config()
    config['parcel'] = {
        'price': float(tax_outlook.just_value),
        'taxHomestead': tax_outlook.homestead,
        'taxNoHomestead': tax_outlook.no_homestead,
        'millsTotal': float(tax_outlook.millage.total),
    }
    return config


@cdn_cache
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

    # Only what the cards show: crawlers walk parcel pages through these links,
    # so every column read here is paid for in database egress.
    similar_properties = similar_properties.only(
        'parcel_id', 'address', 'market_value', 'bedrooms', 'bathrooms', 'building_sqft', 'image_url'
    )[:4]

    district_millage = None
    if property_obj.tax_district:
        district_millage = (
            TaxDistrictMillage.objects.filter(district_code=property_obj.tax_district).order_by('-tax_year').first()
        )

    tax_outlook = build_tax_outlook(property_obj, district_millage)

    return render(
        request,
        'analytics/property-detail.html',
        {
            'property': property_obj,
            'similar_properties': similar_properties,
            'tax_outlook': tax_outlook,
            'affordability': _parcel_affordability(tax_outlook),
            'risk_flags': build_risk_flags(property_obj),
            'has_risk_data': has_risk_data(property_obj),
        },
    )


def _compare_affordability(homes: list[ComparedHome]) -> dict | None:
    """Seed data for the compare page's cost rows, or None if no home has a tax estimate.

    `homes` lines up with the table's columns; a home without an estimate is null.
    """
    if not any(home.tax_outlook for home in homes):
        return None
    config = affordability_config()
    config['homes'] = [
        {
            'price': float(home.tax_outlook.just_value),
            'taxHomestead': home.tax_outlook.homestead,
            'taxNoHomestead': home.tax_outlook.no_homestead,
        }
        if home.tax_outlook
        else None
        for home in homes
    ]
    return config


@cdn_cache
def compare_homes(request):
    """Saved homes side by side. The browser keeps the list and sends it as `?ids=`."""
    comparison = build_comparison(request.GET.get('ids'))
    return render(
        request,
        'analytics/compare.html',
        {
            'comparison': comparison,
            'homes': comparison.homes,
            'affordability': _compare_affordability(comparison.homes),
            'compare_limit': COMPARE_LIMIT,
        },
    )


@require_GET
@never_cache
def csrf_token(request):
    """Hand out a CSRF token on request.

    Cached pages can't carry one: rendering it sets a cookie, which would keep
    the page out of the CDN. Forms on those pages fetch it here when submitted.
    """
    return JsonResponse({'csrfToken': get_token(request)})


@require_POST
def property_refresh(request, parcel_id: str):
    """Re-scrape one parcel from PCPAO and update its row in Neon.

    The bulk import refreshes the whole dataset monthly via GitHub Actions,
    so this is for users who want fresh values on a specific listing
    between refreshes (e.g. after a sale).
    """
    from .tasks.scrape_data import ParcelNotFoundError, refresh_one_parcel

    detail_url = _cache_busted(reverse('property-detail', args=[parcel_id]), 'refreshed')
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
        return redirect(_cache_busted(reverse('insights'), 'rate_limited'))
    return generate(request)


def download_excel(request):
    """Generate and serve an Excel file of properties matching the dashboard filters."""
    return _rate_limited_export(
        request, bucket='export_excel', label='Excel workbook', generate=generate_excel_response
    )


def download_pdf(request):
    """Generate PDF report of properties matching the dashboard filters."""
    return _rate_limited_export(request, bucket='export_pdf', label='PDF brief', generate=generate_pdf_response)
