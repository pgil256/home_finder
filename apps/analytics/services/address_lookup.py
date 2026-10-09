"""Find parcels from what a buyer types: a street address or a parcel ID.

PCPAO site addresses are stored upper-case with single spaces and no
punctuation except the unit marker ('701 MIRROR LAKE DR N # 307'). Queries are
normalised to that shape so the common case is a prefix match served by
idx_address_prefix. A substring scan of the whole table only runs when no
prefix matches and the query is long enough to be selective.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db.models import Q

from ..models import PropertyListing
from .filtering import PINELLAS_CITIES

LOOKUP_LIMIT = 25

SUGGEST_LIMIT = 8
# Shorter than this and the suggestions are a random handful of thousands of
# matches. It also bounds how many distinct responses the CDN has to hold.
SUGGEST_MIN_LENGTH = 3

# Below this length a substring scan matches too much of the county to be
# worth reading 437k rows for.
CONTAINS_MIN_LENGTH = 6

PARCEL_ID_PARTS = (2, 2, 2, 5, 3, 4)
PARCEL_ID_DIGITS = sum(PARCEL_ID_PARTS)

_PARCEL_CHARS_RE = re.compile(r'[\d\s-]+')
_NOT_ADDRESS_CHARS_RE = re.compile(r'[^A-Z0-9# ]+')
_UNIT_RE = re.compile(r'\s*(?:#|\b(?:APT|APARTMENT|UNIT|STE|SUITE)\b)\s*#?\s*([A-Z]?\d+[A-Z]?|[A-Z])$')
_UNIT_SEGMENT_RE = re.compile(r'^\s*(?:#|APT|APARTMENT|UNIT|STE|SUITE)\b', re.IGNORECASE)
_ZIP_RE = re.compile(r'\s+\d{5}(?:\s?\d{4})?$')
_STATE_RE = re.compile(r'\s+(?:FL|FLORIDA)$')

# What people type -> what the county stores. Applied only when the query as
# typed matches nothing, because some street names contain these words.
_ABBREVIATIONS = {
    'STREET': 'ST',
    'AVENUE': 'AVE',
    'BOULEVARD': 'BLVD',
    'DRIVE': 'DR',
    'ROAD': 'RD',
    'LANE': 'LN',
    'COURT': 'CT',
    'PLACE': 'PL',
    'CIRCLE': 'CIR',
    'TERRACE': 'TER',
    'PARKWAY': 'PKWY',
    'TRAIL': 'TRL',
    'POINT': 'PT',
    'HWY': 'HIGHWAY',
    'NORTH': 'N',
    'SOUTH': 'S',
    'EAST': 'E',
    'WEST': 'W',
    'NORTHEAST': 'NE',
    'NORTHWEST': 'NW',
    'SOUTHEAST': 'SE',
    'SOUTHWEST': 'SW',
}


def _plain(text: str) -> str:
    return ' '.join(_NOT_ADDRESS_CHARS_RE.sub(' ', text.upper()).split())


# Longest first, so 'ST PETE BEACH' is tried before a shorter name could match.
_CITY_SUFFIXES = sorted(
    {_plain(city) for city in PINELLAS_CITIES} | {'ST PETE', 'SAINT PETERSBURG'},
    key=len,
    reverse=True,
)
_CITY_BY_PLAIN_NAME = {_plain(city): city for city in PINELLAS_CITIES}


def normalize_address_query(raw: str | None) -> str:
    """Reduce a typed or pasted address to the county's street-address form.

    '1029 Charles St., Clearwater, FL 33755' -> '1029 CHARLES ST'
    '701 mirror lake dr n apt 307'           -> '701 MIRROR LAKE DR N # 307'
    """
    if not raw:
        return ''
    segments = [segment for segment in raw.split(',') if segment.strip()]
    if not segments:
        return ''
    # A pasted listing address carries city, state and ZIP after the first
    # comma; only a unit number there is part of the street address.
    street = segments[0]
    if len(segments) > 1 and _UNIT_SEGMENT_RE.match(segments[1]):
        street = f'{street} {segments[1]}'

    text = _plain(street)
    if len(segments) == 1:
        text = _strip_city_state_zip(text)
    return _UNIT_RE.sub(r' # \1', text).strip()


def _strip_city_state_zip(text: str) -> str:
    """Drop a trailing 'CLEARWATER FL 33755' typed without commas."""
    stripped = _STATE_RE.sub('', _ZIP_RE.sub('', text))
    for city in _CITY_SUFFIXES:
        if stripped.endswith(' ' + city):
            stripped = stripped[: -len(city) - 1]
            break
    # Only a house number and street with extras on the end gets trimmed; a
    # bare ZIP or city, or a street that happens to be named after one, stays.
    return stripped if len(stripped.split()) >= 2 and stripped[0].isdigit() else text


def _abbreviated(normalized: str) -> str:
    head, *rest = normalized.split(' ')
    return ' '.join([head, *(_ABBREVIATIONS.get(token, token) for token in rest)])


def address_candidates(raw: str | None) -> list[str]:
    """The normalised query, then the same query with county abbreviations."""
    normalized = normalize_address_query(raw)
    if not normalized:
        return []
    abbreviated = _abbreviated(normalized)
    return [normalized] if abbreviated == normalized else [normalized, abbreviated]


def parcel_id_from_query(raw: str | None) -> str | None:
    """Return a dashed parcel ID if the query is one, with or without dashes."""
    if not raw or not _PARCEL_CHARS_RE.fullmatch(raw.strip()):
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) != PARCEL_ID_DIGITS:
        return None
    parts = []
    start = 0
    for length in PARCEL_ID_PARTS:
        parts.append(digits[start : start + length])
        start += length
    return '-'.join(parts)


def address_q(raw: str | None) -> Q | None:
    """The cheapest filter that matches the query, or None if nothing can.

    Costs one indexed EXISTS per candidate. The substring scan is the last
    resort and is skipped for short queries.
    """
    candidates = address_candidates(raw)
    for candidate in candidates:
        prefix = Q(address__startswith=candidate)
        if PropertyListing.objects.filter(prefix).exists():
            return prefix

    contains = Q()
    for candidate in candidates:
        if len(candidate) >= CONTAINS_MIN_LENGTH:
            contains |= Q(address__icontains=candidate)
    return contains or None


def keyword_q(raw: str | None) -> Q | None:
    """Filter for the dashboard's free-text box: a ZIP, a city, or an address."""
    text = _plain(raw or '')
    if not text:
        return None
    if re.fullmatch(r'\d{5}', text):
        return Q(zip_code=text)
    city = _CITY_BY_PLAIN_NAME.get(text)
    if city:
        return Q(city__iexact=city)
    return address_q(raw)


@dataclass
class LookupResult:
    query: str = ''
    parcel_id: str | None = None  # set when the query was a parcel ID that exists
    parcels: list[PropertyListing] = field(default_factory=list)
    truncated: bool = False


RESULT_FIELDS = (
    'parcel_id',
    'address',
    'city',
    'zip_code',
    'property_type',
    'market_value',
    'est_tax_homestead',
    'est_tax_no_homestead',
)


def lookup_parcels(raw: str | None, limit: int = LOOKUP_LIMIT) -> LookupResult:
    result = LookupResult(query=(raw or '').strip())
    if not result.query:
        return result

    parcel_id = parcel_id_from_query(result.query)
    if parcel_id:
        if PropertyListing.objects.filter(parcel_id=parcel_id).exists():
            result.parcel_id = parcel_id
        return result

    match = address_q(result.query)
    if match is None:
        return result

    # No ORDER BY: sorting in the database would make it read every match
    # ("1700" alone is thousands of rows) before returning the first 25.
    rows = list(PropertyListing.objects.filter(match).only(*RESULT_FIELDS)[: limit + 1])
    result.truncated = len(rows) > limit
    result.parcels = sorted(rows[:limit], key=lambda parcel: (parcel.address or '', parcel.parcel_id))
    return result


SUGGEST_FIELDS = ('parcel_id', 'address', 'city', 'market_value')


def suggest_parcels(raw: str | None, limit: int = SUGGEST_LIMIT) -> list[dict]:
    """A few addresses that start with what has been typed so far.

    Prefix matches only, so every keystroke is one read of idx_address_prefix.
    The substring scan that lookup_parcels falls back to is left for the
    submitted form.
    """
    for candidate in address_candidates(raw):
        if len(candidate) < SUGGEST_MIN_LENGTH:
            continue
        # No ORDER BY, for the same reason as lookup_parcels.
        rows = list(PropertyListing.objects.filter(address__startswith=candidate).values(*SUGGEST_FIELDS)[:limit])
        if rows:
            return sorted(rows, key=lambda row: (row['address'] or '', row['parcel_id']))
    return []
