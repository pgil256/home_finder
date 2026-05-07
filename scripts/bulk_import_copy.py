"""One-shot bulk import using PostgreSQL COPY.

Far faster than Django's bulk_create over a WAN (us-west Neon from FL is slow).
Use for the initial seed. The GH Actions monthly refresh in
.github/workflows/refresh-data.yml runs from us-east runners and can use
the regular `manage.py import_pcpao_data` path without WAN penalty.

Strategy:
  1. Download + extract PCPAO RP_PROPERTY_INFO.csv into memory
  2. Stream-parse, transform each row to match WebScraper_propertylisting columns
  3. COPY the transformed stream into a temp table
  4. INSERT ... SELECT ... ON CONFLICT (parcel_id) DO UPDATE — single transactional upsert

Usage:
  DATABASE_URL=postgresql://... python scripts/bulk_import_copy.py
  DATABASE_URL=... python scripts/bulk_import_copy.py --csv /path/to/RP_PROPERTY_INFO.csv
"""
import argparse
import csv
import io
import os
import sys
import time
import zipfile
from decimal import Decimal, InvalidOperation
from typing import Optional

import psycopg2
import requests

PCPAO_DOWNLOAD_URL = "https://www.pcpao.gov/dal/databasefile/downloadDatabaseFile"
TABLE = '"WebScraper_propertylisting"'
TEMP_TABLE = "_pcpao_import_staging"

CITY_FIXUPS = {
    "St Petersburg": "St. Petersburg",
    "St Pete Beach": "St. Pete Beach",
}

COPY_COLUMNS = (
    "parcel_id",
    "address",
    "city",
    "zip_code",
    "owner_name",
    "property_type",
    "market_value",
    "assessed_value",
    "building_sqft",
    "year_built",
    "land_size",
    "lot_sqft",
    "tax_amount",
    "tax_status",
)


def safe_decimal(v: str) -> Optional[Decimal]:
    if not v:
        return None
    s = v.strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def safe_int(v: str) -> Optional[int]:
    d = safe_decimal(v)
    return int(d) if d is not None else None


def normalize_city(v: str) -> Optional[str]:
    if not v:
        return None
    s = v.strip()
    if not s:
        return None
    titled = s.title().replace("'S", "'s")
    return CITY_FIXUPS.get(titled, titled)


def split_property_use(v: str) -> str:
    if not v:
        return "Unknown"
    parts = v.strip().split(None, 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1].strip() or "Unknown"
    return v.strip() or "Unknown"


def transform_row(row: dict) -> Optional[tuple]:
    parcel_id = (row.get("PARCEL_NUMBER") or "").strip()
    address = (row.get("SITE_ADDRESS") or "").strip()
    city = normalize_city(row.get("STR_CITY"))
    zip_code = (row.get("STR_ZIP") or "").strip()
    # zip_code is NOT NULL on the model — skip rows missing it (rare orphan parcels)
    if not (parcel_id and address and city and zip_code):
        return None

    acreage = safe_decimal(row.get("ACREAGE", ""))
    land_size = acreage
    lot_sqft = int(acreage * Decimal("43560")) if acreage is not None else None

    tax_amount = safe_decimal(row.get("TAX_AMOUNT_NO_EX", ""))
    tax_status = "From PCPAO" if tax_amount is not None else "Unknown"

    return (
        parcel_id,
        address,
        city,
        zip_code,
        (row.get("OWNER1") or "").strip() or None,
        split_property_use(row.get("PROPERTY_USE", "")),
        safe_decimal(row.get("CNTY_JST_VALUE", "")),
        safe_decimal(row.get("CNTY_ASD_VALUE", "")),
        safe_int(row.get("TOTAL_LIVING_SQFT", "")),
        safe_int(row.get("YEAR_BUILT", "")),
        land_size,
        lot_sqft,
        tax_amount,
        tax_status,
    )


def download_csv() -> bytes:
    print(f"Downloading from {PCPAO_DOWNLOAD_URL}...", flush=True)
    r = requests.post(
        PCPAO_DOWNLOAD_URL,
        data={"hdn_tbl_name": "RP_PROPERTY_INFO", "hdn_ftype": "csv"},
        timeout=600,
    )
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        return zf.read(name)


def csv_field(value) -> str:
    """Format one value for inclusion in a COPY CSV stream."""
    if value is None:
        return ""
    s = str(value)
    if any(c in s for c in (',', '"', '\n', '\r')):
        return '"' + s.replace('"', '""') + '"'
    return s


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="local CSV path (skip download)")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 1

    if args.csv:
        with open(args.csv, "rb") as f:
            csv_bytes = f.read()
    else:
        csv_bytes = download_csv()

    print(f"CSV size: {len(csv_bytes) / 1024 / 1024:.1f} MB", flush=True)

    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    started = time.time()
    buf = io.StringIO()
    valid = 0
    skipped = 0
    for row in reader:
        rec = transform_row(row)
        if rec is None:
            skipped += 1
            continue
        buf.write(",".join(csv_field(v) for v in rec) + "\n")
        valid += 1

    print(
        f"Parsed in {time.time() - started:.1f}s — valid: {valid:,} | skipped: {skipped:,}",
        flush=True,
    )

    buf.seek(0)
    started = time.time()

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            print("Creating staging table...", flush=True)
            cur.execute(
                f"CREATE TEMP TABLE {TEMP_TABLE} ("
                f"  parcel_id TEXT,"
                f"  address TEXT,"
                f"  city TEXT,"
                f"  zip_code TEXT,"
                f"  owner_name TEXT,"
                f"  property_type TEXT,"
                f"  market_value NUMERIC,"
                f"  assessed_value NUMERIC,"
                f"  building_sqft INTEGER,"
                f"  year_built INTEGER,"
                f"  land_size NUMERIC,"
                f"  lot_sqft INTEGER,"
                f"  tax_amount NUMERIC,"
                f"  tax_status TEXT"
                f")"
            )

            print("COPY into staging...", flush=True)
            cur.copy_expert(
                f"COPY {TEMP_TABLE} ({', '.join(COPY_COLUMNS)}) "
                f"FROM STDIN WITH (FORMAT csv, NULL '')",
                buf,
            )
            cur.execute(f"SELECT COUNT(*) FROM {TEMP_TABLE}")
            staging_count = cur.fetchone()[0]
            print(f"Staged {staging_count:,} rows in {time.time() - started:.1f}s", flush=True)

            print("Upserting into target table...", flush=True)
            upsert_started = time.time()
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    parcel_id, address, city, zip_code, owner_name,
                    property_type, market_value, assessed_value,
                    building_sqft, year_built, land_size, lot_sqft,
                    tax_amount, tax_status, delinquent, created_at, last_scraped
                )
                SELECT
                    parcel_id, address, city, zip_code, owner_name,
                    property_type, market_value, assessed_value,
                    building_sqft, year_built, land_size, lot_sqft,
                    tax_amount, tax_status, FALSE, NOW(), NOW()
                FROM {TEMP_TABLE}
                ON CONFLICT (parcel_id) DO UPDATE SET
                    address = EXCLUDED.address,
                    city = EXCLUDED.city,
                    zip_code = EXCLUDED.zip_code,
                    owner_name = EXCLUDED.owner_name,
                    property_type = EXCLUDED.property_type,
                    market_value = EXCLUDED.market_value,
                    assessed_value = EXCLUDED.assessed_value,
                    building_sqft = EXCLUDED.building_sqft,
                    year_built = EXCLUDED.year_built,
                    land_size = EXCLUDED.land_size,
                    lot_sqft = EXCLUDED.lot_sqft,
                    tax_amount = EXCLUDED.tax_amount,
                    tax_status = EXCLUDED.tax_status,
                    last_scraped = NOW()
                """
            )
            print(f"Upsert done in {time.time() - upsert_started:.1f}s", flush=True)

        conn.commit()
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
            print(f"Total rows in {TABLE}: {cur.fetchone()[0]:,}", flush=True)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
