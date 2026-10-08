"""Side-by-side comparison of the homes a visitor has saved.

Saved homes live in the visitor's browser (localStorage), so the page gets
its parcel IDs from the query string. Nothing about the visitor is stored
here, and the link works for anyone it is sent to.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.analytics.models import PropertyListing, TaxDistrictMillage

from .risk_flags import RiskFlag, build_risk_flags, has_risk_data
from .tax_estimate import TaxOutlook, build_tax_outlook

# Enough for a shortlist, and the table still fits on a laptop screen.
COMPARE_LIMIT = 6

_MAX_PARCEL_ID_LENGTH = PropertyListing._meta.get_field('parcel_id').max_length


@dataclass(frozen=True)
class ComparedHome:
    listing: PropertyListing
    tax_outlook: TaxOutlook | None
    risk_flags: list[RiskFlag]
    has_risk_data: bool


@dataclass(frozen=True)
class Comparison:
    homes: list[ComparedHome]
    requested: int
    # Saved IDs the county no longer has (a retired or renumbered parcel).
    missing: int
    # IDs past COMPARE_LIMIT that were left out.
    left_out: int


def parse_compare_ids(raw: str | None) -> list[str]:
    """Parcel IDs from a comma-separated `ids` value, in order, without repeats."""
    ids: list[str] = []
    for part in (raw or '').split(','):
        parcel_id = part.strip()
        if parcel_id and len(parcel_id) <= _MAX_PARCEL_ID_LENGTH and parcel_id not in ids:
            ids.append(parcel_id)
    return ids


def build_comparison(raw_ids: str | None) -> Comparison:
    requested = parse_compare_ids(raw_ids)
    shown = requested[:COMPARE_LIMIT]

    listings = {listing.parcel_id: listing for listing in PropertyListing.objects.filter(parcel_id__in=shown)}
    districts = {listing.tax_district for listing in listings.values() if listing.tax_district}
    # Ordered oldest first, so the newest year is the one left in the dict.
    millage = {
        row.district_code: row
        for row in TaxDistrictMillage.objects.filter(district_code__in=districts).order_by('tax_year')
    }

    homes = [
        ComparedHome(
            listing=listing,
            tax_outlook=build_tax_outlook(listing, millage.get(listing.tax_district)),
            risk_flags=build_risk_flags(listing),
            has_risk_data=has_risk_data(listing),
        )
        for listing in (listings[parcel_id] for parcel_id in shown if parcel_id in listings)
    ]
    return Comparison(
        homes=homes,
        requested=len(requested),
        missing=len(shown) - len(homes),
        left_out=len(requested) - len(shown),
    )
