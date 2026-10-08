"""Yearly lending constants and the default mortgage rate for the calculator.

The calculator itself runs in the browser (static/js/dev/affordability.js).
This module holds the numbers that change on a calendar, so a yearly update
is a one-line change here:

- FHFA and HUD publish the next year's loan limits in late November.
- FHA mortgage insurance premiums change by HUD Mortgagee Letter (the current
  schedule is ML 2023-05, effective March 20, 2023).

Pinellas is in the Tampa-St. Petersburg-Clearwater metro, which uses the
national conforming baseline and the FHA floor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import DatabaseError

logger = logging.getLogger(__name__)

# Freddie Mac's weekly 30-year fixed average (FRED series MORTGAGE30US). Used
# only until the weekly "Refresh mortgage rate" workflow has stored a row.
FALLBACK_MORTGAGE_RATE = Decimal('7.40')
FALLBACK_MORTGAGE_RATE_DATE = date(2026, 10, 8)

# One-unit limits for Pinellas County, keyed by the first year they apply to.
LOAN_LIMITS = {
    2026: {'conforming': 832_750, 'fha': 541_287},
}

# FHA mortgage insurance (ML 2023-05). Annual rates are percent of the base
# loan, as (highest loan-to-value percent, rate) bands; the split between the
# two tables is the base loan amount, which HUD fixed at $726,200.
FHA_UPFRONT_MIP_PCT = 1.75
FHA_MIN_DOWN_PCT = 3.5
FHA_ANNUAL_MIP = {
    'largeLoanOver': 726_200,
    # Terms longer than 15 years.
    'long': {'standard': [[95, 0.50], [100, 0.55]], 'large': [[95, 0.70], [100, 0.75]]},
    # Terms of 15 years or less.
    'short': {'standard': [[90, 0.15], [100, 0.40]], 'large': [[78, 0.15], [90, 0.40], [100, 0.65]]},
}

# The budget search has no parcel to price, so it assumes county-typical
# costs as a percent of price per year. Taxes are near the middle of Pinellas
# millage (about 16 to 22 mills) with no exemption taken off.
BUDGET_TAX_RATE_PCT = 1.8
# A placeholder: Florida premiums vary widely with roof age, construction and
# distance from the water, and flood cover is separate.
INSURANCE_RATE_PCT = 1.0


@dataclass(frozen=True)
class RateQuote:
    rate: Decimal
    as_of: date
    is_fallback: bool


def current_mortgage_rate() -> RateQuote:
    """The stored weekly rate, or the fallback if there isn't one.

    Deploys don't run migrations, so the table can be missing until the next
    scheduled job creates it. The parcel page must still render.
    """
    from apps.analytics.models import MortgageRate

    try:
        stored = MortgageRate.objects.first()
    except DatabaseError:
        logger.warning('Could not read the mortgage rate; using the fallback', exc_info=True)
        stored = None
    if stored is None:
        return RateQuote(FALLBACK_MORTGAGE_RATE, FALLBACK_MORTGAGE_RATE_DATE, is_fallback=True)
    return RateQuote(stored.rate, stored.as_of, is_fallback=False)


def loan_limits(today: date | None = None) -> tuple[int, dict[str, int]]:
    """The latest published limits that apply this year, as (year, limits)."""
    this_year = (today or date.today()).year
    years = [year for year in LOAN_LIMITS if year <= this_year]
    year = max(years) if years else min(LOAN_LIMITS)
    return year, LOAN_LIMITS[year]


def affordability_config(today: date | None = None) -> dict:
    """Everything the browser calculator needs that isn't about one parcel."""
    quote = current_mortgage_rate()
    limits_year, limits = loan_limits(today)
    return {
        'rate': float(quote.rate),
        'rateAsOf': f'{quote.as_of:%b} {quote.as_of.day}, {quote.as_of.year}',
        'insuranceRatePct': INSURANCE_RATE_PCT,
        'budgetTaxRatePct': BUDGET_TAX_RATE_PCT,
        'lending': {
            'limitsYear': limits_year,
            'conformingLimit': limits['conforming'],
            'fhaLimit': limits['fha'],
            'fhaUpfrontMipPct': FHA_UPFRONT_MIP_PCT,
            'fhaMinDownPct': FHA_MIN_DOWN_PCT,
            'fhaAnnualMip': FHA_ANNUAL_MIP,
        },
    }
