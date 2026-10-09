"""
Flood-insurance claim history by ZIP code

Reads National Flood Insurance Program claims for Pinellas County from
OpenFEMA's v3 NfipClaims dataset and keeps three numbers per ZIP code. As
downloaded in October 2026 there are 51,779 claims going back to 1978:

  - reportedZipCode: 5 digits on all but a handful of rows, which carry
    ZIP+4 or are blank. About 140 distinct values, a few from outside the
    county.
  - yearOfLoss: 29,873 claims are from 2020 or later, 26,366 of them from
    2024 (Hurricanes Helene and Milton).
  - amountPaidOn{Building,Contents,IncreasedCostOfCompliance}Claim: null or 0
    when nothing was paid. 42,476 claims were paid; the county-wide median
    was about $31,000.

FEMA publishes claims by ZIP code and census tract, never by address, so this
describes a neighborhood's history and not a home's.
"""

from __future__ import annotations

import logging
import statistics
import time
from collections import defaultdict

import requests
from django.db import DatabaseError, transaction

from apps.analytics.models import ZipFloodHistory

logger = logging.getLogger(__name__)

NFIP_CLAIMS_URL = 'https://www.fema.gov/api/open/v3/NfipClaims'
PINELLAS_COUNTY_FIPS = '12103'
CLAIM_RECORDS_START_YEAR = 1978
RECENT_SINCE_YEAR = 2020
PAGE_SIZE = 10000
_ATTEMPTS = 3
_PAID_FIELDS = (
    'amountPaidOnBuildingClaim',
    'amountPaidOnContentsClaim',
    'amountPaidOnIncreasedCostOfComplianceClaim',
)

# Fewer claims than this means a broken download, not a quiet decade.
MIN_CLAIMS = 10000


def _fetch_page(skip: int) -> list[dict]:
    params = {
        '$filter': f"countyCode eq '{PINELLAS_COUNTY_FIPS}'",
        '$select': ','.join(('reportedZipCode', 'yearOfLoss', *_PAID_FIELDS)),
        '$orderby': 'id',
        '$top': PAGE_SIZE,
        '$skip': skip,
    }
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            response = requests.get(NFIP_CLAIMS_URL, params=params, timeout=180)
            response.raise_for_status()
            return response.json()['NfipClaims']
        except (requests.RequestException, ValueError, KeyError) as error:
            if attempt == _ATTEMPTS:
                raise RuntimeError(f'Could not read flood claims from OpenFEMA at row {skip}: {error}') from error
            logger.warning('OpenFEMA request failed at row %d (%s); retrying', skip, error)
            time.sleep(10 * attempt)
    raise AssertionError('unreachable')


def download_claims() -> list[dict]:
    """Every NFIP claim for the county, with only the columns summarized here."""
    claims: list[dict] = []
    while True:
        page = _fetch_page(len(claims))
        claims.extend(page)
        if len(page) < PAGE_SIZE:
            return claims


def summarize_claims(claims: list[dict]) -> list[ZipFloodHistory]:
    """One unsaved ZipFloodHistory per ZIP code that has a claim."""
    counts: dict[str, int] = defaultdict(int)
    recent: dict[str, int] = defaultdict(int)
    paid: dict[str, list[float]] = defaultdict(list)
    for claim in claims:
        zip_code = (claim.get('reportedZipCode') or '').strip()[:5]  # some rows carry ZIP+4
        if len(zip_code) != 5 or not zip_code.isdigit():
            continue
        counts[zip_code] += 1
        if (claim.get('yearOfLoss') or 0) >= RECENT_SINCE_YEAR:
            recent[zip_code] += 1
        amount = sum(claim.get(field) or 0 for field in _PAID_FIELDS)
        if amount > 0:
            paid[zip_code].append(amount)

    return [
        ZipFloodHistory(
            zip_code=zip_code,
            claim_count=count,
            recent_claim_count=recent[zip_code],
            median_paid=round(statistics.median(paid[zip_code])) if paid[zip_code] else None,
        )
        for zip_code, count in sorted(counts.items())
    ]


def import_flood_claims(claims: list[dict]) -> int:
    """Replace the stored ZIP history with a summary of `claims`; returns the ZIP count."""
    if len(claims) < MIN_CLAIMS:
        raise RuntimeError(f'Only {len(claims)} flood claims read; keeping the claim history already stored.')
    rows = summarize_claims(claims)
    with transaction.atomic():
        ZipFloodHistory.objects.all().delete()
        ZipFloodHistory.objects.bulk_create(rows)
    logger.info('Stored flood claim history for %d ZIP codes', len(rows))
    return len(rows)


def zip_flood_history(zip_code: str | None) -> ZipFloodHistory | None:
    """Stored claim history for a parcel's ZIP code, if there is any.

    Deploys don't run migrations, so the table can be missing until the flood
    refresh creates it. The parcel page must still render.
    """
    if not zip_code:
        return None
    try:
        return ZipFloodHistory.objects.filter(zip_code=zip_code.strip()[:5]).first()
    except DatabaseError:
        logger.warning('Could not read flood claim history for ZIP %s', zip_code, exc_info=True)
        return None
