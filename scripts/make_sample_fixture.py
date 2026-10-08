"""Regenerate the sample PCPAO fixtures from real county downloads.

Picks a small, deterministic sample of RP_PROPERTY_INFO rows that covers the
cases the app cares about (every evacuation zone, waterfront and seawall,
subsidence, contamination, historic landmarks, capped homesteads, older
condos, duplexes, commercial, and one row the importer skips), then blanks
owner, mailing, and deed columns so no personal data lands in the repo.

With an RP_SALES file as a third argument, it also writes every sale of the
sampled parcels, with buyer and seller names and deed references blanked.
With an RP_PERMITS file as a fourth, it writes every permit of the sampled
parcels; that file names no people.

Usage:
    python scripts/make_sample_fixture.py RP_PROPERTY_INFO.csv RP_MILLAGE_RATES.csv [RP_SALES.csv [RP_PERMITS.csv]]

The inputs come from https://www.pcpao.gov/tools-data/data-downloads/raw-database-files
"""

import csv
import random
import sys
from collections.abc import Callable
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent.parent / 'apps' / 'analytics' / 'fixtures'
PROPERTY_OUT = FIXTURE_DIR / 'sample_pcpao_data.csv'
MILLAGE_OUT = FIXTURE_DIR / 'sample_millage_rates.csv'
SALES_OUT = FIXTURE_DIR / 'sample_sales.csv'
PERMITS_OUT = FIXTURE_DIR / 'sample_permits.csv'
SEED = 20260929

REDACTED_COLUMNS = {
    'OWNER2',
    'MAILING_ADDRESS_1',
    'MAILING_ADDRESS_2',
    'MAILING_ADDRESS_3',
    'MAILING_ADDRESS_4',
    'MAILING_CITY',
    'MAILING_STATE',
    'MAILING_ZIP',
    'LEGAL',
    'OR_BOOK_PAGE',
}
REDACTED_SALES_COLUMNS = {'BOOK_PAGE', 'GRANTEE', 'GRANTOR'}


def _num(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _has_site(r: dict[str, str]) -> bool:
    return bool(r['SITE_ADDRESS'].strip() and r['STR_CITY'].strip() and r['STR_ZIP'].strip())


def _home(r: dict[str, str]) -> bool:
    return _has_site(r) and r['PARCEL_TYPE'] in ('Residential', 'Condo') and _num(r['CNTY_JST_VALUE']) > 50_000


# (bucket name, how many rows, predicate). A row lands in the first bucket it matches.
BUCKETS: list[tuple[str, int, Callable[[dict[str, str]], bool]]] = [
    ('skipped: no site address', 1, lambda r: not r['SITE_ADDRESS'].strip()),
    ('subsidence', 2, lambda r: _home(r) and r['SUBSIDENCE_YN'] == 'Y'),
    ('contamination', 1, lambda r: _has_site(r) and r['CONTAMINATION_YN'] == 'Y'),
    ('historic landmark', 2, lambda r: _home(r) and r['DLHL_YN'] == 'Y'),
    ('gulf waterfront + seawall', 2, lambda r: _home(r) and r['FRONTAGE'] == 'Gulf' and r['SEAWALL'] == 'Yes'),
    ('canal waterfront + seawall', 2, lambda r: _home(r) and r['FRONTAGE'] == 'Canal/River' and r['SEAWALL'] == 'Yes'),
    (
        'big save-our-homes gap',
        4,
        lambda r: (
            _home(r) and r['HX_CAP'] == 'Yes' and _num(r['CNTY_JST_VALUE']) > 2 * max(_num(r['CNTY_ASD_VALUE']), 1)
        ),
    ),
    (
        'homestead, just value 50k-76k',
        1,
        lambda r: _home(r) and r['HX_CAP'] == 'Yes' and 50_000 < _num(r['CNTY_ASD_VALUE']) < 76_411,
    ),
    ('non-homestead capped', 3, lambda r: _home(r) and r['NON_HX_CAP'] == 'Yes' and r['HX_CAP'] == 'No'),
    (
        'older condo',
        3,
        lambda r: _home(r) and r['PARCEL_TYPE'] == 'Condo' and 0 < _num(r['YEAR_BUILT']) < 1985,
    ),
    ('newer condo', 2, lambda r: _home(r) and r['PARCEL_TYPE'] == 'Condo' and _num(r['YEAR_BUILT']) >= 2005),
    ('duplex to fourplex', 2, lambda r: _home(r) and 2 <= _num(r['TOTAL_LIVING_UNITS']) <= 4),
    ('commercial', 2, lambda r: _has_site(r) and r['PARCEL_TYPE'] == 'Commercial'),
    ('special assessment', 2, lambda r: _home(r) and _num(r['SPECIAL_ASSESSMENT']) >= 300),
    ('evac zone A', 3, lambda r: _home(r) and r['EVAC_ZONE'] == 'A'),
    ('evac zone B', 3, lambda r: _home(r) and r['EVAC_ZONE'] == 'B'),
    ('evac zone C', 3, lambda r: _home(r) and r['EVAC_ZONE'] == 'C'),
    ('evac zone D', 3, lambda r: _home(r) and r['EVAC_ZONE'] == 'D'),
    ('evac zone E', 3, lambda r: _home(r) and r['EVAC_ZONE'] == 'E'),
    ('non-evac', 4, lambda r: _home(r) and r['EVAC_ZONE'] == 'NON EVAC'),
]


def sample_properties(path: Path) -> tuple[list[str], list[list[str]]]:
    rng = random.Random(SEED)
    reservoirs: dict[str, list[list[str]]] = {name: [] for name, _, _ in BUCKETS}
    seen = dict.fromkeys(reservoirs, 0)

    with path.open(encoding='cp1252', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        for raw in reader:
            row = dict(zip(header, raw, strict=True))
            for name, size, predicate in BUCKETS:
                if predicate(row):
                    # Reservoir sampling keeps the pick uniform without loading the 350 MB file.
                    seen[name] += 1
                    if len(reservoirs[name]) < size:
                        reservoirs[name].append(raw)
                    else:
                        slot = rng.randrange(seen[name])
                        if slot < size:
                            reservoirs[name][slot] = raw
                    break

    owner_index = header.index('OWNER1')
    redacted = [i for i, col in enumerate(header) if col in REDACTED_COLUMNS]
    rows: list[list[str]] = []
    for name, _, _ in BUCKETS:
        for raw in sorted(reservoirs[name], key=lambda r: r[1]):
            raw = list(raw)
            raw[owner_index] = f'SAMPLE OWNER {len(rows) + 1:02d}'
            for i in redacted:
                raw[i] = ''
            rows.append(raw)
        print(f'{name}: {len(reservoirs[name])} of {seen[name]} candidates')
    return header, rows


def sample_millage(path: Path, districts: set[str]) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding='cp1252', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        mill_cd = header.index('MILL_CD')
        return header, [row for row in reader if row[mill_cd] in districts]


def sample_sales(path: Path, parcels: set[str]) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding='cp1252', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        parcel_number = header.index('PARCEL_NUMBER')
        redacted = [i for i, col in enumerate(header) if col in REDACTED_SALES_COLUMNS]
        rows = []
        for row in reader:
            if row[parcel_number] in parcels:
                for i in redacted:
                    row[i] = ''
                rows.append(row)
    return header, sorted(rows, key=lambda r: (r[parcel_number], r[header.index('SALE_DATE')]))


def sample_permits(path: Path, parcels: set[str]) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding='cp1252', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        parcel_number = header.index('PARCEL_NUMBER')
        rows = [row for row in reader if row[parcel_number] in parcels]
    return header, sorted(rows, key=lambda r: (r[parcel_number], r[header.index('ISSUE_DT')]))


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open('w', encoding='cp1252', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)
    print(f'Wrote {len(rows)} rows to {path}')


def main(property_csv: str, millage_csv: str, sales_csv: str | None = None, permits_csv: str | None = None) -> None:
    header, rows = sample_properties(Path(property_csv))
    write_csv(PROPERTY_OUT, header, rows)

    district_index = header.index('TAX_DISTRICT')
    districts = {row[district_index] for row in rows}
    millage_header, millage_rows = sample_millage(Path(millage_csv), districts)
    write_csv(MILLAGE_OUT, millage_header, millage_rows)

    parcels = {row[header.index('PARCEL_NUMBER')] for row in rows}
    if sales_csv:
        write_csv(SALES_OUT, *sample_sales(Path(sales_csv), parcels))
    if permits_csv:
        write_csv(PERMITS_OUT, *sample_permits(Path(permits_csv), parcels))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4, 5):
        sys.exit(__doc__)
    main(*sys.argv[1:])
