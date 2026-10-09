"""Street names, for finding the street a buyer meant when they mistyped it.

A trigram index on 437,000 addresses would cost tens of megabytes of a
512 MiB database. The county has only a few thousand distinct street names,
so those are kept in their own small table (StreetName) with a trigram index
on that. A query that matches no address is split into house number and
street, the nearest street names are looked up here, and the address search
runs again with each.

The table is rebuilt from the addresses already in the database, by the
monthly import and by the daily database guard when it is empty.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass

from django.db import DatabaseError, connection, transaction

from ..models import PropertyListing, StreetName

logger = logging.getLogger(__name__)

# pg_trgm similarity, 0 to 1. "GULF BVLD" against "GULF BLVD" scores 0.43.
SIMILARITY_THRESHOLD = 0.4
# The county's file has stray spellings of its own ("GULF BLV", on one parcel).
# Among names this close to the best score, the street with the most parcels
# is the one the buyer meant.
NEAR_TIE = 0.05
NEAREST_LIMIT = 3
MIN_STREET_LENGTH = 3

# '1700 GULF BLVD # 2' -> 'GULF BLVD'. The same two patterns are used in SQL
# by _rebuild_in_postgres, so keep them to syntax both engines read alike.
_UNIT_PATTERN = r'\s+#.*$'
_HOUSE_NUMBER_PATTERN = r'^[0-9]+[A-Z]?\s+'
_UNIT_RE = re.compile(_UNIT_PATTERN)
_HOUSE_NUMBER_RE = re.compile(_HOUSE_NUMBER_PATTERN)


@dataclass(frozen=True)
class NearbyStreet:
    name: str
    city: str
    similarity: float


def split_address(normalized: str) -> tuple[str, str]:
    """Split a county-form address into (house number, street), dropping the unit.

    '1700 GULF BLVD # 2' -> ('1700', 'GULF BLVD')
    'MIRROR LAKE DR N'   -> ('', 'MIRROR LAKE DR N')
    """
    without_unit = _UNIT_RE.sub('', normalized)
    match = _HOUSE_NUMBER_RE.match(without_unit)
    if not match:
        return '', without_unit.strip()
    return match.group().strip(), without_unit[match.end() :].strip()


def street_of(address: str | None) -> str:
    return split_address(address or '')[1]


def trigrams(text: str) -> set[str]:
    """The trigram set pg_trgm builds: each word lower-cased and padded with two
    leading blanks and one trailing blank."""
    found = set()
    for word in re.findall(r'[a-z0-9]+', text.lower()):
        padded = f'  {word} '
        found.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return found


def trigram_similarity(a: str, b: str) -> float:
    """pg_trgm's similarity(): shared trigrams over all distinct trigrams."""
    first, second = trigrams(a), trigrams(b)
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def nearest_streets(street: str, limit: int = NEAREST_LIMIT) -> list[NearbyStreet]:
    """Street names closest in spelling to `street`, best first, one entry per name.

    Returns nothing rather than raising when the table isn't there yet: deploys
    don't run migrations, and a missing spelling suggestion must not break the
    lookup page.
    """
    if len(street) < MIN_STREET_LENGTH:
        return []
    try:
        if connection.vendor == 'postgresql':
            rows = _nearest_in_postgres(street, limit)
        else:
            rows = _nearest_in_python(street)
    except DatabaseError:
        logger.warning('Could not read street names for %r', street, exc_info=True)
        return []

    # The same street name in two cities is one spelling to try. Rows arrive
    # biggest city first within a name, so that is the city it is shown with.
    nearest: dict[str, NearbyStreet] = {}
    parcels: dict[str, int] = {}
    for name, city, similarity, parcel_count in rows:
        nearest.setdefault(name, NearbyStreet(name=name, city=city, similarity=similarity))
        parcels[name] = parcels.get(name, 0) + parcel_count
    if not nearest:
        return []

    best = max(street.similarity for street in nearest.values())

    def rank(street: NearbyStreet):
        if street.similarity >= best - NEAR_TIE:
            return (0, -parcels[street.name], -street.similarity, street.name)
        return (1, -street.similarity, -parcels[street.name], street.name)

    return sorted(nearest.values(), key=rank)[:limit]


def _nearest_in_postgres(street: str, limit: int) -> list[tuple[str, str, float, int]]:
    table = connection.ops.quote_name(StreetName._meta.db_table)
    with connection.cursor() as cursor:
        # `%%` is pg_trgm's "similar enough" operator (0.3 by default), which
        # is what lets the trigram index narrow the rows; the stricter
        # threshold is applied to what it returns.
        cursor.execute(
            f'SELECT name, city, similarity(name, %s) AS score, parcel_count FROM {table} '
            'WHERE name %% %s AND similarity(name, %s) >= %s '
            'ORDER BY score DESC, parcel_count DESC, name, city LIMIT %s',
            [street, street, street, SIMILARITY_THRESHOLD, limit * 4],
        )
        return cursor.fetchall()


def _nearest_in_python(street: str) -> list[tuple[str, str, float, int]]:
    """The same ranking without pg_trgm, for SQLite in development and tests."""
    scored = [
        (trigram_similarity(name, street), parcel_count, name, city)
        for name, city, parcel_count in StreetName.objects.values_list('name', 'city', 'parcel_count')
    ]
    scored = [row for row in scored if row[0] >= SIMILARITY_THRESHOLD]
    scored.sort(key=lambda row: (-row[0], -row[1], row[2], row[3]))
    return [(name, city, similarity, parcel_count) for similarity, parcel_count, name, city in scored]


def rebuild_street_names() -> int:
    """Replace the street-name table with what the addresses say now. Returns the row count."""
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            _rebuild_in_postgres()
        else:
            StreetName.objects.all().delete()
            _rebuild_in_python()
    return StreetName.objects.count()


def _rebuild_in_postgres() -> None:
    """Inside the database, so no address leaves it.

    TRUNCATE and REINDEX rather than DELETE and plain inserts: deleted rows and
    a trigram index filled row by row both leave the table several times the
    size it needs to be, and this database has a storage cap.
    """
    street_names = connection.ops.quote_name(StreetName._meta.db_table)
    listings = connection.ops.quote_name(PropertyListing._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f'TRUNCATE {street_names}')
        cursor.execute(
            f'INSERT INTO {street_names} (name, city, parcel_count) '
            'SELECT street, city, COUNT(*) FROM ('
            '  SELECT btrim(regexp_replace(regexp_replace(address, %s, %s), %s, %s)) AS street, city'
            f'  FROM {listings} WHERE address IS NOT NULL AND city IS NOT NULL'
            ') AS streets WHERE length(street) >= %s GROUP BY street, city',
            [_UNIT_PATTERN, '', _HOUSE_NUMBER_PATTERN, '', MIN_STREET_LENGTH],
        )
        cursor.execute(f'REINDEX TABLE {street_names}')


def _rebuild_in_python() -> None:
    counts: Counter[tuple[str, str]] = Counter()
    addresses = PropertyListing.objects.filter(address__isnull=False, city__isnull=False)
    for address, city in addresses.values_list('address', 'city').iterator():
        street = street_of(address)
        if len(street) >= MIN_STREET_LENGTH:
            counts[(street, city)] += 1
    StreetName.objects.bulk_create(
        [StreetName(name=name, city=city, parcel_count=count) for (name, city), count in counts.items()],
        batch_size=1000,
    )
