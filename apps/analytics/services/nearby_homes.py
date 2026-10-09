"""Homes near a parcel that the county values about the same.

This is context for the county's number, not comparable sales (see comps.py
for those). The homes come from the parcel's county appraisal neighborhood,
the same kind of home, nearest in just value first. Where the neighborhood is
too small, the rest come from the same city.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F
from django.db.models.functions import Abs

from apps.analytics.models import PropertyListing

from .comps import comp_type_bucket, comp_type_q

NEARBY_LIMIT = 4
# A home from elsewhere in the city is only worth showing if its value is close.
CITY_VALUE_BAND = Decimal('0.2')

# Only what the cards show: crawlers walk parcel pages through these links,
# so every column read here is paid for in database egress.
CARD_FIELDS = ('parcel_id', 'address', 'market_value', 'building_sqft', 'year_built', 'image_url')


def nearby_homes(listing: PropertyListing, limit: int = NEARBY_LIMIT) -> list[PropertyListing]:
    """Up to `limit` homes valued closest to this one, its own neighborhood first."""
    value = listing.market_value
    if not value:
        return []

    homes = _in_neighborhood(listing, value, limit)
    if len(homes) < limit:
        chosen = [listing.parcel_id, *(home.parcel_id for home in homes)]
        homes += _in_city(listing, value, limit - len(homes), exclude=chosen)
    return homes


def _in_neighborhood(listing: PropertyListing, value: Decimal, limit: int) -> list[PropertyListing]:
    bucket = comp_type_bucket(listing.property_type)
    if not listing.neighborhood_code or bucket is None:
        return []
    # idx_neighborhood narrows this to one neighborhood, usually a subdivision
    # or a condo complex, and the database sorts that by distance in value.
    return list(
        PropertyListing.objects.filter(
            comp_type_q(bucket),
            neighborhood_code=listing.neighborhood_code,
            market_value__isnull=False,
        )
        .exclude(parcel_id=listing.parcel_id)
        .annotate(value_gap=Abs(F('market_value') - value))
        .order_by('value_gap', 'parcel_id')
        .only(*CARD_FIELDS)[:limit]
    )


def _in_city(listing: PropertyListing, value: Decimal, limit: int, exclude: list[str]) -> list[PropertyListing]:
    if not listing.city or not listing.property_type:
        return []
    same_kind = (
        PropertyListing.objects.filter(city=listing.city, property_type=listing.property_type)
        .exclude(parcel_id__in=exclude)
        .only(*CARD_FIELDS)
    )
    # A city can hold tens of thousands of homes of one type. Walking
    # idx_city_type_value outward from this home's value, once up and once
    # down, reads a handful of rows instead of sorting all of them.
    above = same_kind.filter(market_value__gte=value, market_value__lte=value * (1 + CITY_VALUE_BAND))
    below = same_kind.filter(market_value__lt=value, market_value__gte=value * (1 - CITY_VALUE_BAND))
    candidates = [
        *above.order_by('market_value', 'parcel_id')[:limit],
        *below.order_by('-market_value', 'parcel_id')[:limit],
    ]
    candidates.sort(key=lambda home: (abs(home.market_value - value), home.parcel_id))
    return candidates[:limit]
