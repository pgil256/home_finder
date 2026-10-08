"""
PCPAO sales importer

Loads RP_SALES, the county's file of recorded sales. As downloaded in October
2026 it has about 161,000 rows going back to January 2021. Each row is one
deed for one parcel:

  - QUALIFIED_FLG: 'Q' (arm's-length), 'U' (unqualified: family transfers,
    foreclosures, $100 quitclaims) or 'M' (multi-parcel)
  - VACANT_IMPROVED: 'I' if the parcel had a building when it sold, else 'V'
  - MULTI_SALES_YN: 'Y' when PRICE covers more than one parcel
  - SALE_ID: counts up with each sale of the parcel

Only qualified, single-parcel sales of improved parcels are kept, because
those are the prices a buyer can compare against. Buyer and seller names
(GRANTEE, GRANTOR) are never stored.
"""

import csv
import logging
from datetime import date

from django.db import connection, transaction

from apps.analytics.models import Sale
from apps.analytics.services.pcpao_importer import csv_encoding, safe_int

logger = logging.getLogger(__name__)

SALES_TABLE = 'RP_SALES'


def read_qualified_sales(csv_path: str) -> list[Sale]:
    """Qualified single-parcel sales of improved parcels, one per parcel per day.

    About 270 parcels have two qualified deeds on the same day (a relocation
    company buying and reselling, for example). The later deed is the price
    the current owner paid, so the highest SALE_ID wins.
    """
    latest: dict[tuple[str, date], tuple[int, int]] = {}
    with open(csv_path, encoding=csv_encoding(csv_path), newline='') as f:
        for row in csv.DictReader(f):
            if row['QUALIFIED_FLG'] != 'Q' or row['VACANT_IMPROVED'] != 'I' or row['MULTI_SALES_YN'] == 'Y':
                continue
            parcel_id = row['PARCEL_NUMBER'].strip()
            price = safe_int(row['PRICE'])
            try:
                sale_date = date.fromisoformat(row['SALE_DATE'][:10])  # '2021-07-02 00:00:00'
            except ValueError:
                continue
            if not parcel_id or not price or price <= 0:
                continue
            sale_id = safe_int(row['SALE_ID']) or 0
            key = (parcel_id, sale_date)
            if key not in latest or sale_id > latest[key][0]:
                latest[key] = (sale_id, price)

    return [
        Sale(parcel_id=parcel_id, sale_date=sale_date, price=price)
        for (parcel_id, sale_date), (_, price) in latest.items()
    ]


def import_sales(csv_path: str, batch_size: int = 5000) -> int:
    """Replace the Sale table with an RP_SALES file. Returns the rows loaded."""
    sales = read_qualified_sales(csv_path)
    if not sales:
        # A renamed column raises KeyError above; this catches a file whose
        # flag values changed, before it can empty the table.
        raise RuntimeError(f'No qualified sales found in {csv_path}; keeping the sales already loaded.')

    # One transaction, so a parcel page never sees a half-loaded table. On
    # PostgreSQL the TRUNCATE holds readers off until the insert commits.
    with transaction.atomic():
        _empty_sale_table()
        Sale.objects.bulk_create(sales, batch_size=batch_size)
    logger.info('Loaded %d qualified sales', len(sales))
    return len(sales)


def _empty_sale_table() -> None:
    """TRUNCATE leaves no dead rows behind, unlike DELETE, on a size-limited database."""
    if connection.vendor != 'postgresql':
        Sale.objects.all().delete()
        return
    table_name = connection.ops.quote_name(Sale._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f'TRUNCATE TABLE {table_name} RESTART IDENTITY')
