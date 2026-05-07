from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import PropertyListing
from .services.filtering import (
    PINELLAS_CITIES, PROPERTY_TYPES,
    apply_filters, apply_sorting, paginate,
)
from .services.exports import generate_excel_response, generate_pdf_response

logger = logging.getLogger(__name__)

# Form fields whose names already match the dashboard's apply_filters params.
# property_type is handled separately because it's multi-value.
PASSTHROUGH_FIELDS = (
    'city', 'zip_code', 'min_price', 'max_price',
    'year_built', 'tax_status', 'min_sqft', 'max_sqft',
)
# beds/baths intentionally excluded — PCPAO doesn't expose this data.


def web_scraper_view(request):
    """Search form. POST translates form fields to dashboard query params and 302s.

    Searches are now DB queries against the bulk-imported PCPAO data, not live
    scrapes — fast, accurate, no rate limit, no loading state needed.
    """
    if request.method == 'POST':
        params: list[tuple[str, str]] = []
        for field in PASSTHROUGH_FIELDS:
            value = request.POST.get(field)
            if value:
                params.append((field, value))
        for property_type in request.POST.getlist('property_type'):
            if property_type:
                params.append(('property_type', property_type))

        url = reverse('dashboard')
        if params:
            url += '?' + urlencode(params)
        return redirect(url)

    return render(request, 'WebScraper/search.html', {
        'cities': sorted(PINELLAS_CITIES),
        'property_types': PROPERTY_TYPES,
    })


def property_dashboard(request):
    """Property dashboard with filtering, sorting, and pagination."""
    properties, selected_types = apply_filters(request)
    sort = request.GET.get('sort', '-market_value')
    properties = apply_sorting(properties, sort)
    total_count = properties.count()
    page_number = request.GET.get('page', 1)
    properties_page = paginate(properties, page_number)

    city = request.GET.get('city')
    search_criteria = {}
    if city:
        search_criteria['city'] = city
    if selected_types:
        search_criteria['property_types'] = selected_types

    return render(request, 'WebScraper/dashboard.html', {
        'properties': properties_page,
        'total_count': total_count,
        'cities': sorted(PINELLAS_CITIES),
        'property_types': PROPERTY_TYPES,
        'selected_property_types': selected_types,
        'search_criteria': search_criteria,
        'sort': sort,
    })


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
            market_value__gte=min_price, market_value__lte=max_price,
        )

    similar_properties = similar_properties[:4]

    return render(request, 'WebScraper/property-detail.html', {
        'property': property_obj,
        'similar_properties': similar_properties,
    })


def download_excel(request):
    """Generate and serve an Excel file of properties matching the dashboard filters."""
    return generate_excel_response(request)


def download_pdf(request):
    """Generate PDF report of properties matching the dashboard filters."""
    return generate_pdf_response(request)
