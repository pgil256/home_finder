from __future__ import annotations

import logging
from typing import Optional

from django.core.paginator import Paginator, Page
from django.db.models import F, QuerySet

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

# Map each form-friendly property-type label to the substrings that should
# match in the PCPAO `property_type` column (which has values like
# 'Single Family Home', 'Duplex-Triplex-Fourplex', 'Manufactured Home (Co-Op
# or Share Owned)', etc.). The match is case-insensitive `icontains` OR.
PROPERTY_TYPE_KEYWORDS = {
    'Single Family': ['Single Family', 'Planned Unit Development'],
    'Condo': ['Condominium', 'Condo Conversion', 'Condo Common'],
    'Townhouse': ['Townhouse', 'Townhome'],
    'Multi-Family': [
        'Duplex-Triplex-Fourplex', 'Multi-Family',
        'Apartments (5-9 units)', 'Apartments (10-49 units)',
        'Apartments (50 or more', 'ALF',
    ],
    'Vacant Land': ['Vacant Residential', 'Acreage - Vacant'],
    'Mobile Home': ['Mobile Home', 'Manufactured Home'],
    'Commercial': [
        'Office', 'Store', 'Warehouse', 'Restaurant', 'Hotel', 'Motel',
        'Hospital', 'Auto', 'Medical', 'Vacant Commercial', 'Federal',
        'Municipal', 'Bank', 'Marina', 'School', 'Church', 'Industrial',
        'Drive-In', 'Service', 'Cafeteria', 'Shopping',
    ],
}

# Default property-type filter — used when the user hasn't picked any types.
# The home page is pitched at finding a place to live, so commercial,
# institutional, and miscellaneous parcels stay out of the default view.
RESIDENTIAL_DEFAULT_LABELS = (
    'Single Family', 'Condo', 'Townhouse',
    'Multi-Family', 'Mobile Home', 'Vacant Land',
)

VALID_SORT_FIELDS = [
    'market_value', '-market_value',
    'created_at', '-created_at',
    'building_sqft', '-building_sqft',
    'year_built', '-year_built',
]

DEFAULT_SORT = '-market_value'
PAGE_SIZE = 12


def apply_filters(request) -> tuple[QuerySet, list[str], bool]:
    """Apply all query filters from request params.

    Returns:
        (queryset, user_selected_property_types, defaulted_to_residential)
        - user_selected_property_types is *only* what the user explicitly
          chose (drives chip rendering and checkbox state).
        - defaulted_to_residential is True when no property_type filter was
          set and `?include_all=1` wasn't passed, so the queryset is
          silently constrained to residential types. Use this to render a
          banner offering to show all types.
    """
    properties = PropertyListing.objects.all()

    city = request.GET.get('city')
    zip_code = request.GET.get('zip_code')
    property_types_filter = request.GET.getlist('property_type')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    beds = request.GET.get('beds')
    baths = request.GET.get('baths')
    year_built = request.GET.get('year_built')
    tax_status = request.GET.get('tax_status')
    min_sqft = request.GET.get('min_sqft')
    max_sqft = request.GET.get('max_sqft')

    if city:
        properties = properties.filter(city__iexact=city)

    if zip_code:
        properties = properties.filter(zip_code=zip_code.strip())

    # Default to residential when no property_type is chosen, unless the
    # user opted into the unfiltered view via ?include_all=1. This keeps the
    # buyer-facing default (highest-value Single Family, Condo, etc.) instead
    # of surfacing $300M hospitals on page one.
    show_all_types = request.GET.get('include_all') == '1'
    effective_types = property_types_filter or (
        [] if show_all_types else list(RESIDENTIAL_DEFAULT_LABELS)
    )
    if effective_types:
        from django.db.models import Q
        type_q = Q()
        for label in effective_types:
            for keyword in PROPERTY_TYPE_KEYWORDS.get(label, [label]):
                type_q |= Q(property_type__icontains=keyword)
        properties = properties.filter(type_q)

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

    if min_sqft:
        try:
            properties = properties.filter(building_sqft__gte=int(min_sqft))
        except ValueError:
            logger.warning("Invalid min_sqft filter value: %r", min_sqft)

    if max_sqft:
        try:
            properties = properties.filter(building_sqft__lte=int(max_sqft))
        except ValueError:
            logger.warning("Invalid max_sqft filter value: %r", max_sqft)

    defaulted_to_residential = bool(
        not property_types_filter and not show_all_types
    )
    return properties, property_types_filter, defaulted_to_residential


def apply_sorting(properties: QuerySet, sort: Optional[str] = None) -> QuerySet:
    """Apply sorting to queryset. Falls back to default if invalid.

    Sorts NULLs last for any field — Postgres' default for DESC puts NULLs
    first, which surfaces 'Contact for Price' rows (condo common areas, etc.)
    above real listings on the first page. The dashboard is for browsing
    sellable properties, so push the no-data rows to the back.
    """
    field = sort if sort in VALID_SORT_FIELDS else DEFAULT_SORT
    descending = field.startswith('-')
    base = field.lstrip('-')
    expr = F(base).desc(nulls_last=True) if descending else F(base).asc(nulls_last=True)
    return properties.order_by(expr)


def paginate(properties: QuerySet, page_number: int = 1) -> Page:
    """Paginate the queryset."""
    paginator = Paginator(properties, PAGE_SIZE)
    return paginator.get_page(page_number)
