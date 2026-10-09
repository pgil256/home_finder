"""What a home last sold for, and what similar homes nearby sold for.

Everything here comes from the county's qualified sales (see
sales_importer.py). These are recorded prices, not an appraisal: the
comparable figure is a median price per square foot from a handful of nearby
sales, shown with how many sales it rests on and how far they spread.
"""

from __future__ import annotations

import calendar
import logging
import math
from dataclasses import dataclass
from datetime import date
from statistics import median

from django.db import DatabaseError
from django.db.models import Q

from apps.analytics.models import PropertyListing, Sale

from .filtering import PROPERTY_TYPE_KEYWORDS

logger = logging.getLogger(__name__)

COMP_WINDOW_MONTHS = 12
# A comparable home's living area is within this share of the subject's.
COMP_SQFT_TOLERANCE = 0.25
# Fewer sales than this and a median says more about one house than the market.
MIN_COMPS = 3
# From this many, the median is steady enough to lead with. Below it the page
# leads with the range the sales covered, and the median comes second.
CONFIDENT_COMPS = 5
COMPS_SHOWN = 5
FLIP_WINDOW_MONTHS = 24

# Checked in this order: a manufactured-home "land condo" is a mobile home,
# and a townhouse-style condo is a condo.
_COMP_TYPE_ORDER = ('Mobile Home', 'Condo', 'Townhouse', 'Multi-Family', 'Single Family')


@dataclass(frozen=True)
class RecordedSale:
    sale_date: date
    price: int


@dataclass(frozen=True)
class Comp:
    parcel_id: str
    address: str
    sale_date: date
    price: int
    building_sqft: int
    price_per_sqft: float


@dataclass(frozen=True)
class CompSummary:
    count: int
    median_per_sqft: float
    low_per_sqft: float
    high_per_sqft: float
    # Median price per square foot times this home's living area, to the nearest $1,000.
    indicated_value: int
    subject_sqft: int
    # The most recent few, newest first.
    shown: list[Comp]

    @property
    def confident(self) -> bool:
        return self.count >= CONFIDENT_COMPS


@dataclass(frozen=True)
class Flip:
    earlier: RecordedSale
    later: RecordedSale
    # 'within a month' or 'after 14 months'
    resold: str


@dataclass(frozen=True)
class SalesOutlook:
    # Newest first.
    history: list[RecordedSale]
    comps: CompSummary | None
    flip: Flip | None

    @property
    def last_sale(self) -> RecordedSale | None:
        return self.history[0] if self.history else None


def comp_type_bucket(property_type: str | None) -> str | None:
    """The kind of home to compare against, or None for parcels nobody lives in."""
    lowered = (property_type or '').lower()
    for label in _COMP_TYPE_ORDER:
        if any(keyword.lower() in lowered for keyword in PROPERTY_TYPE_KEYWORDS[label]):
            return label
    return None


def comp_type_q(bucket: str) -> Q:
    """The database filter for the rows comp_type_bucket() puts in `bucket`."""
    match = Q()
    for keyword in PROPERTY_TYPE_KEYWORDS[bucket]:
        match |= Q(property_type__icontains=keyword)
    for earlier in _COMP_TYPE_ORDER[: _COMP_TYPE_ORDER.index(bucket)]:
        for keyword in PROPERTY_TYPE_KEYWORDS[earlier]:
            match &= ~Q(property_type__icontains=keyword)
    return match


def build_sales_outlook(listing: PropertyListing, today: date | None = None) -> SalesOutlook | None:
    """Sales history and comparable sales for a parcel, or None if there are neither.

    Deploys don't run migrations, so the sales table can be missing until the
    next scheduled import creates it. The parcel page must still render.
    """
    today = today or date.today()
    try:
        history = [
            RecordedSale(sale.sale_date, sale.price)
            for sale in Sale.objects.filter(parcel_id=listing.parcel_id).order_by('-sale_date')
        ]
        comps = _comparable_sales(listing, today)
    except DatabaseError:
        logger.warning('Could not read sales for parcel %s', listing.parcel_id, exc_info=True)
        return None

    if not history and comps is None:
        return None
    return SalesOutlook(history=history, comps=comps, flip=_flip(history))


def _months_before(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _flip(history: list[RecordedSale]) -> Flip | None:
    """The two most recent sales, if the home was resold within two years."""
    if len(history) < 2:
        return None
    later, earlier = history[0], history[1]
    if earlier.sale_date < _months_before(later.sale_date, FLIP_WINDOW_MONTHS):
        return None
    months = (later.sale_date.year - earlier.sale_date.year) * 12 + later.sale_date.month - earlier.sale_date.month
    if later.sale_date.day < earlier.sale_date.day:
        months -= 1
    if months < 1:
        resold = 'within a month'
    else:
        resold = f'after {months} month{"" if months == 1 else "s"}'
    return Flip(earlier=earlier, later=later, resold=resold)


def _comparable_sales(listing: PropertyListing, today: date) -> CompSummary | None:
    bucket = comp_type_bucket(listing.property_type)
    sqft = listing.building_sqft
    if not listing.neighborhood_code or bucket is None or not sqft or sqft <= 0:
        return None

    # The county draws neighborhoods around homes it values together: usually
    # a subdivision or a condo complex, but a few run to thousands of parcels.
    # The subquery keeps those in the database, so only the homes that sold
    # come back.
    neighbors = (
        PropertyListing.objects.filter(
            neighborhood_code=listing.neighborhood_code,
            building_sqft__gte=math.ceil(sqft * (1 - COMP_SQFT_TOLERANCE)),
            building_sqft__lte=math.floor(sqft * (1 + COMP_SQFT_TOLERANCE)),
        )
        .exclude(parcel_id=listing.parcel_id)
        .values('parcel_id')
    )
    # Newest first, and one sale per home: a house that sold twice this year
    # counts once, at the price its current owner paid.
    latest_sales: dict[str, Sale] = {}
    recent_sales = Sale.objects.filter(
        parcel_id__in=neighbors, sale_date__gte=_months_before(today, COMP_WINDOW_MONTHS)
    ).order_by('-sale_date')
    for sale in recent_sales:
        latest_sales.setdefault(sale.parcel_id, sale)
    if len(latest_sales) < MIN_COMPS:
        return None

    sold_homes = {
        home.parcel_id: home
        for home in PropertyListing.objects.filter(parcel_id__in=list(latest_sales)).only(
            'parcel_id', 'address', 'property_type', 'building_sqft'
        )
        if comp_type_bucket(home.property_type) == bucket
    }
    comps = [
        Comp(
            parcel_id=parcel_id,
            address=sold_homes[parcel_id].address,
            sale_date=sale.sale_date,
            price=sale.price,
            building_sqft=sold_homes[parcel_id].building_sqft,
            price_per_sqft=sale.price / sold_homes[parcel_id].building_sqft,
        )
        for parcel_id, sale in latest_sales.items()
        if parcel_id in sold_homes
    ]
    if len(comps) < MIN_COMPS:
        return None

    per_sqft = [comp.price_per_sqft for comp in comps]
    median_per_sqft = median(per_sqft)
    return CompSummary(
        count=len(comps),
        median_per_sqft=median_per_sqft,
        low_per_sqft=min(per_sqft),
        high_per_sqft=max(per_sqft),
        indicated_value=int(round(median_per_sqft * sqft, -3)),
        subject_sqft=sqft,
        shown=comps[:COMPS_SHOWN],
    )
