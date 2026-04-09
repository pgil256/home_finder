from __future__ import annotations

import logging
from typing import Optional

from django.core.paginator import Paginator, Page
from django.db.models import QuerySet

from ..models import PropertyListing

logger = logging.getLogger(__name__)

PINELLAS_CITIES = [
    'Clearwater', 'St. Petersburg', 'Largo', 'Pinellas Park', 'Dunedin',
    'Palm Harbor', 'Tarpon Springs', 'Seminole', 'Safety Harbor', 'Oldsmar',
    'Gulfport', 'St. Pete Beach', 'Treasure Island', 'Madeira Beach',
    'Indian Rocks Beach', 'Belleair', 'Kenneth City', 'South Pasadena',
    'Indian Shores', 'Redington Beach',
]

PROPERTY_TYPES = [
    'Single Family', 'Condo', 'Townhouse', 'Multi-Family',
    'Vacant Land', 'Mobile Home', 'Commercial',
]

VALID_SORT_FIELDS = [
    'market_value', '-market_value',
    'created_at', '-created_at',
    'building_sqft', '-building_sqft',
    'year_built', '-year_built',
]

DEFAULT_SORT = '-market_value'
PAGE_SIZE = 12


def apply_filters(request) -> tuple[QuerySet, list[str]]:
    """Apply all query filters from request params. Returns (queryset, selected_property_types)."""
    properties = PropertyListing.objects.all()

    city = request.GET.get('city')
    property_types_filter = request.GET.getlist('property_type')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    beds = request.GET.get('beds')
    baths = request.GET.get('baths')
    year_built = request.GET.get('year_built')
    tax_status = request.GET.get('tax_status')

    if city:
        properties = properties.filter(city__iexact=city)

    if property_types_filter:
        properties = properties.filter(property_type__in=property_types_filter)

    if min_price:
        try:
            properties = properties.filter(market_value__gte=float(min_price))
        except ValueError:
            logger.warning("Invalid min_price filter value: %r", min_price)

    if max_price:
        try:
            properties = properties.filter(market_value__lte=float(max_price))
        except ValueError:
            logger.warning("Invalid max_price filter value: %r", max_price)

    if beds and beds != '0':
        try:
            properties = properties.filter(bedrooms__gte=int(beds))
        except ValueError:
            logger.warning("Invalid beds filter value: %r", beds)

    if baths and baths != '0':
        try:
            properties = properties.filter(bathrooms__gte=float(baths))
        except ValueError:
            logger.warning("Invalid baths filter value: %r", baths)

    if year_built:
        try:
            properties = properties.filter(year_built__gte=int(year_built))
        except ValueError:
            logger.warning("Invalid year_built filter value: %r", year_built)

    if tax_status:
        properties = properties.filter(tax_status=tax_status)

    return properties, property_types_filter


def apply_sorting(properties: QuerySet, sort: Optional[str] = None) -> QuerySet:
    """Apply sorting to queryset. Falls back to default if invalid."""
    if sort in VALID_SORT_FIELDS:
        return properties.order_by(sort)
    return properties.order_by(DEFAULT_SORT)


def paginate(properties: QuerySet, page_number: int = 1) -> Page:
    """Paginate the queryset."""
    paginator = Paginator(properties, PAGE_SIZE)
    return paginator.get_page(page_number)
