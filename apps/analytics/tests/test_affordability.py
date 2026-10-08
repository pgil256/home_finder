import json
import re
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import ProgrammingError

from apps.analytics.management.commands.refresh_mortgage_rate import parse_latest_rate
from apps.analytics.models import MortgageRate, PropertyListing, TaxDistrictMillage
from apps.analytics.services import lending_config, tax_estimate

pytestmark = pytest.mark.django_db

FRED_GET = 'apps.analytics.management.commands.refresh_mortgage_rate.requests.get'
FRED_CSV = 'observation_date,MORTGAGE30US\n2026-09-24,7.03\n2026-10-01,7.28\n2026-10-08,7.40\n'


def _fred_response(text=FRED_CSV):
    response = Mock(text=text)
    response.raise_for_status = Mock()
    return response


def _page_config(html: str) -> dict:
    match = re.search(r'<script id="affordability-data" type="application/json">(.*?)</script>', html, re.S)
    assert match, 'the page has no calculator data'
    return json.loads(match.group(1))


class TestCurrentMortgageRate:
    def test_falls_back_to_the_constant_before_the_first_refresh(self):
        quote = lending_config.current_mortgage_rate()

        assert quote.rate == lending_config.FALLBACK_MORTGAGE_RATE
        assert quote.is_fallback

    def test_falls_back_when_the_table_has_not_been_migrated_yet(self):
        with patch.object(MortgageRate.objects, 'first', side_effect=ProgrammingError('no such table')):
            quote = lending_config.current_mortgage_rate()

        assert quote.is_fallback

    def test_uses_the_stored_rate(self):
        MortgageRate.objects.create(pk=1, rate=Decimal('6.85'), as_of=date(2026, 11, 5))

        quote = lending_config.current_mortgage_rate()

        assert (quote.rate, quote.as_of, quote.is_fallback) == (Decimal('6.85'), date(2026, 11, 5), False)

    def test_config_is_json_ready(self):
        MortgageRate.objects.create(pk=1, rate=Decimal('6.85'), as_of=date(2026, 11, 5))

        config = lending_config.affordability_config(today=date(2026, 11, 6))

        assert json.loads(json.dumps(config)) == config
        assert config['rate'] == 6.85
        assert config['rateAsOf'] == 'Nov 5, 2026'
        assert config['lending']['conformingLimit'] == 832_750
        assert config['lending']['fhaLimit'] == 541_287


class TestLoanLimits:
    def test_keeps_the_latest_published_year_until_the_next_is_added(self):
        assert lending_config.loan_limits(date(2026, 6, 1))[0] == 2026
        assert lending_config.loan_limits(date(2027, 1, 15))[0] == 2026

    def test_picks_up_a_new_year_once_it_applies(self):
        limits = {2026: {'conforming': 1, 'fha': 1}, 2027: {'conforming': 2, 'fha': 2}}
        with patch.object(lending_config, 'LOAN_LIMITS', limits):
            assert lending_config.loan_limits(date(2026, 12, 1))[0] == 2026
            assert lending_config.loan_limits(date(2027, 1, 1))[0] == 2027


class TestParseLatestRate:
    def test_reads_the_newest_observation(self):
        assert parse_latest_rate(FRED_CSV) == (date(2026, 10, 8), Decimal('7.40'))

    def test_skips_weeks_with_no_observation(self):
        csv_text = 'observation_date,MORTGAGE30US\n2026-10-01,7.28\n2026-10-08,.\n'

        assert parse_latest_rate(csv_text) == (date(2026, 10, 1), Decimal('7.28'))

    @pytest.mark.parametrize(
        'csv_text',
        [
            'observation_date,MORTGAGE30US\n',
            '<html>Service unavailable</html>',
            'observation_date,MORTGAGE30US\n2026-10-08,74.0\n',
            'observation_date,MORTGAGE30US\n2026-10-08,0\n',
        ],
    )
    def test_rejects_empty_and_implausible_responses(self, csv_text):
        with pytest.raises(ValueError):
            parse_latest_rate(csv_text)


class TestRefreshMortgageRate:
    def test_stores_one_row_and_overwrites_it(self):
        with patch(FRED_GET, return_value=_fred_response()) as get:
            call_command('refresh_mortgage_rate')
            call_command('refresh_mortgage_rate')

        assert get.call_args.kwargs['params']['id'] == 'MORTGAGE30US'
        stored = MortgageRate.objects.get()
        assert (stored.rate, stored.as_of) == (Decimal('7.40'), date(2026, 10, 8))

    @pytest.mark.parametrize(
        'failure',
        [
            {'side_effect': requests.ConnectionError('down')},
            {'return_value': _fred_response('<html>Sign in</html>')},
        ],
    )
    def test_a_bad_download_fails_and_keeps_the_last_good_rate(self, failure):
        MortgageRate.objects.create(pk=1, rate=Decimal('6.85'), as_of=date(2026, 9, 3))

        with patch(FRED_GET, **failure), pytest.raises(CommandError, match='FRED'):
            call_command('refresh_mortgage_rate')

        assert MortgageRate.objects.get().rate == Decimal('6.85')


class TestCostCalculatorCard:
    @pytest.fixture(autouse=True)
    def buying_in_2026(self):
        with patch.object(tax_estimate, 'buyer_tax_year', return_value=2027):
            yield

    @pytest.fixture
    def home(self, db):
        TaxDistrictMillage.objects.create(
            district_code='SP',
            tax_year=2025,
            rate_description='2025 Final',
            total_mills=Decimal('19.9197'),
            school_mills=Decimal('6.2930'),
        )
        return PropertyListing.objects.create(
            parcel_id='36-30-16-78588-003-0060',
            address='1043 61ST AVE N',
            city='St. Petersburg',
            zip_code='33703',
            property_type='Single Family Home',
            market_value=Decimal('282885'),
            assessed_value=Decimal('77124'),
            tax_district='SP',
            special_assessment=Decimal('0'),
            est_tax_current=678,
            est_tax_homestead=4777,
            est_tax_no_homestead=5635,
        )

    def _html(self, client, listing):
        return client.get(f'/analytics/property/{listing.parcel_id}/').content.decode('utf-8', 'ignore')

    def test_is_seeded_with_just_value_tax_estimates_and_the_rate(self, client, home):
        MortgageRate.objects.create(pk=1, rate=Decimal('6.85'), as_of=date(2026, 11, 5))

        html = self._html(client, home)
        config = _page_config(html)

        assert config['parcel'] == {
            'price': 282885.0,
            'taxHomestead': 4777,
            'taxNoHomestead': 5635,
            'millsTotal': 19.9197,
        }
        assert config['rate'] == 6.85
        assert 'value="282885"' in html
        assert 'value="6.85"' in html
        assert 'week of Nov 5, 2026' in html
        assert 'not the asking price' in html
        assert 'js/dist/affordability.bundle.js' in html

    def test_offers_no_homestead_choice_when_the_parcel_cannot_be_homesteaded(self, client, home):
        home.est_tax_homestead = None
        home.save()

        html = self._html(client, home)

        assert _page_config(html)['parcel']['taxHomestead'] is None
        assert 'data-calc-input="homestead"' not in html

    def test_no_calculator_without_a_tax_estimate(self, client, home):
        TaxDistrictMillage.objects.all().delete()

        html = self._html(client, home)

        assert 'id="cost-calculator"' not in html
        assert 'affordability.bundle.js' not in html


class TestBudgetSearchField:
    def test_search_form_offers_a_monthly_budget_that_is_not_submitted(self, client):
        html = client.get('/analytics/').content.decode('utf-8', 'ignore')

        budget_input = re.search(r'<input[^>]*id="budget-monthly"[^>]*>', html).group(0)
        assert 'name=' not in budget_input
        assert _page_config(html)['budgetTaxRatePct'] == lending_config.BUDGET_TAX_RATE_PCT
        assert 'js/dist/affordability.bundle.js' in html
