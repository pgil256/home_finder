"""
PCPAO permits reader

Reads RP_PERMITS, the county's file of building permits. As downloaded in
October 2026 it has about 1.67 million rows from every permitting agency in
the county, going back to 1997. Each row is one permit on one parcel:

  - PERMIT_DSCR: the county's own category. 'ROOF' (429,000 rows) and
    'HEAT/AIR' (287,000) are the two read here; the other 59 are ignored.
  - ISSUE_DT: when the permit was issued. About 660 rows carry a placeholder
    year (1899 or earlier).
  - PERMIT_YEAR: the assessment year, not the issue year, and 0 on 65,000
    rows. Not used.

Nothing is stored per permit. The import keeps one year per parcel for each
category, on PropertyListing. A roof permit can be a repair as well as a
replacement: since 2015 about 7% were valued under $3,000.
"""

import csv
import logging
from datetime import date
from typing import NamedTuple

from apps.analytics.services.pcpao_importer import csv_encoding, safe_int

logger = logging.getLogger(__name__)

PERMITS_TABLE = 'RP_PERMITS'
# The county's permit records start here; a home with no roof permit may
# still have had a new roof before this.
PERMIT_RECORDS_START_YEAR = 1997

ROOF = 'ROOF'
HEAT_AIR = 'HEAT/AIR'


class PermitYears(NamedTuple):
    roof: int | None = None
    hvac: int | None = None


def read_permit_years(csv_path: str, today: date | None = None) -> dict[str, PermitYears]:
    """Year of the latest roof and heating/air permit for each parcel that has either."""
    this_year = (today or date.today()).year
    roof: dict[str, int] = {}
    hvac: dict[str, int] = {}
    with open(csv_path, encoding=csv_encoding(csv_path), newline='') as f:
        for row in csv.DictReader(f):
            latest = roof if row['PERMIT_DSCR'] == ROOF else hvac if row['PERMIT_DSCR'] == HEAT_AIR else None
            if latest is None:
                continue
            parcel_id = row['PARCEL_NUMBER'].strip()
            year = safe_int(row['ISSUE_DT'][:4])  # '2019-03-31 00:00:00'
            if not parcel_id or year is None or not PERMIT_RECORDS_START_YEAR <= year <= this_year:
                continue
            if year > latest.get(parcel_id, 0):
                latest[parcel_id] = year

    if not roof:
        # A renamed column raises KeyError above; this catches a file whose
        # categories changed, before it can clear every stored year.
        raise RuntimeError(f'No roof permits found in {csv_path}; keeping the permit years already loaded.')

    logger.info('Read permit years for %d parcels', len(roof.keys() | hvac.keys()))
    return {parcel_id: PermitYears(roof.get(parcel_id), hvac.get(parcel_id)) for parcel_id in roof.keys() | hvac.keys()}
