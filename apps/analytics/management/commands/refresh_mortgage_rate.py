"""
Store the latest 30-year fixed mortgage average for the cost calculator.

Reads Freddie Mac's weekly survey from FRED's public CSV download, which
needs no API key, and keeps it in the one-row MortgageRate table.

Usage:
    python manage.py refresh_mortgage_rate

Exits non-zero without touching the stored rate if the download fails or the
figure looks wrong, so the calculator keeps the last good rate.
"""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import MortgageRate

FRED_CSV_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv'
SERIES = 'MORTGAGE30US'
# The weekly average has stayed between 2.65% and 18.63% since 1971.
PLAUSIBLE_RATES = (Decimal(1), Decimal(20))


def parse_latest_rate(csv_text: str) -> tuple[date, Decimal]:
    """Return the newest (date, rate) in a FRED CSV. Missing weeks are '.'."""
    latest = None
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) < 2:
            continue
        try:
            latest = (date.fromisoformat(row[0].strip()), Decimal(row[1].strip()))
        except (ValueError, InvalidOperation):
            continue  # the header, or a week with no observation
    if latest is None:
        raise ValueError('no observations in the FRED response')
    low, high = PLAUSIBLE_RATES
    if not low <= latest[1] <= high:
        raise ValueError(f'implausible rate {latest[1]}')
    return latest


class Command(BaseCommand):
    help = 'Fetch the latest 30-year mortgage rate from FRED'

    def handle(self, *args, **options):
        # Two months back is plenty to find the latest weekly figure.
        since = date.today() - timedelta(days=60)
        try:
            response = requests.get(FRED_CSV_URL, params={'id': SERIES, 'cosd': since.isoformat()}, timeout=30)
            response.raise_for_status()
            as_of, rate = parse_latest_rate(response.text)
        except (requests.RequestException, ValueError) as error:
            raise CommandError(f'Could not read {SERIES} from FRED: {error}') from error

        MortgageRate.objects.update_or_create(pk=1, defaults={'rate': rate, 'as_of': as_of})
        self.stdout.write(f'30-year fixed: {rate}% as of {as_of}')
