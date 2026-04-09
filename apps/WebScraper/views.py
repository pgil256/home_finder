from __future__ import annotations

import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET

from .models import PropertyListing
from .services.filtering import (
    PINELLAS_CITIES, PROPERTY_TYPES,
    apply_filters, apply_sorting, paginate,
)
from .services.task_management import (
    build_processing_pipeline, get_client_ip, check_rate_limit,
    get_task_status_response,
)
from .services.exports import generate_excel_response, generate_pdf_response

logger = logging.getLogger(__name__)


def web_scraper_view(request):
    """Main view for the property scraper interface."""
    if request.method == 'POST':
        client_ip = get_client_ip(request)
        wait = check_rate_limit(client_ip)
        if wait:
            logger.warning("Rate limited scrape request from %s", client_ip)
            return render(request, 'WebScraper/search.html', {
                'cities': sorted(PINELLAS_CITIES),
                'property_types': PROPERTY_TYPES,
                'error': f'Please wait {wait} seconds before submitting another search.',
            })

        property_types = request.POST.getlist('property_type')
        search_criteria = {
            'city': request.POST.get('city'),
            'zip_code': request.POST.get('zip_code'),
            'property_type': (
                property_types[0] if len(property_types) == 1
                else property_types if property_types else None
            ),
            'min_value': request.POST.get('min_value'),
            'max_value': request.POST.get('max_value'),
            'bedrooms_min': request.POST.get('bedrooms_min'),
            'bathrooms_min': request.POST.get('bathrooms_min'),
            'year_built_after': request.POST.get('year_built_after'),
            'tax_status': request.POST.get('tax_status'),
            'sqft_min': request.POST.get('sqft_min'),
            'sqft_max': request.POST.get('sqft_max'),
        }
        search_criteria = {k: v for k, v in search_criteria.items() if v}

        try:
            limit = int(request.POST.get('limit', 50))
        except ValueError:
            limit = 50
        user_email = request.POST.get('email', '')

        result = build_processing_pipeline(search_criteria, limit, user_email)
        return redirect('scraping-progress', task_id=result.id)

    return render(request, 'WebScraper/search.html', {
        'cities': sorted(PINELLAS_CITIES),
        'property_types': PROPERTY_TYPES,
    })


def scraping_progress(request, task_id: str):
    """View to track scraping progress."""
    return render(request, 'WebScraper/scraping-progress.html', {'task_id': task_id})


@require_GET
def get_task_status(request, task_id: str):
    """API endpoint to get task status with chain progress aggregation."""
    return get_task_status_response(task_id)


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
    """Generate and serve an Excel file of all properties."""
    return generate_excel_response()


def download_pdf(request):
    """Generate PDF report with property listings and market analysis charts."""
    return generate_pdf_response()
