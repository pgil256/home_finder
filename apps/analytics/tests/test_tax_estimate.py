"""Expected values below are worked by hand from St. Petersburg's 2025 final
millage: 19.9197 total, of which 6.2930 is school (3.045 + 3.248) and
13.6267 is non-school."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.analytics.services import tax_estimate
from apps.analytics.services.tax_estimate import (
    AMENDMENT_3,
    CURRENT_LAW,
    Millage,
    buyer_tax_year,
    estimate_current_tax,
    estimate_new_owner_tax,
    homestead_rules,
)

ST_PETE = Millage(total=Decimal('19.9197'), school=Decimal('6.2930'))
CURRENT = CURRENT_LAW[2026]


class TestHomesteadExemptions:
    @pytest.mark.parametrize(
        ('assessed', 'school', 'nonschool'),
        [
            (Decimal(20_000), Decimal(20_000), Decimal(20_000)),  # exemption can't exceed the value
            (Decimal(40_000), Decimal(25_000), Decimal(25_000)),  # below $50k: no additional exemption
            (Decimal(60_000), Decimal(25_000), Decimal(35_000)),  # partial additional exemption
            (Decimal(76_411), Decimal(25_000), Decimal(51_411)),  # additional exemption maxes out
            (Decimal(300_000), Decimal(25_000), Decimal(51_411)),
        ],
    )
    def test_current_law(self, assessed, school, nonschool):
        assert CURRENT.exemptions(assessed) == (school, nonschool)

    def test_amendment_3_flat_nonschool_exemption(self):
        assert AMENDMENT_3[2027].exemptions(Decimal(300_000)) == (Decimal(25_000), Decimal(150_000))
        assert AMENDMENT_3[2028].exemptions(Decimal(300_000)) == (Decimal(25_000), Decimal(250_000))
        assert AMENDMENT_3[2027].exemptions(Decimal(120_000)) == (Decimal(25_000), Decimal(120_000))


class TestEstimateNewOwnerTax:
    @pytest.mark.parametrize(
        ('just_value', 'expected'),
        [
            # 275,000 x 6.293 + 248,589 x 13.6267 = 1,730.58 + 3,387.45
            (Decimal(300_000), 5118),
            # 35,000 x 6.293 + 25,000 x 13.6267 = 220.26 + 340.67
            (Decimal(60_000), 561),
            # 15,000 x 6.293 + 15,000 x 13.6267 = 94.40 + 204.40
            (Decimal(40_000), 299),
            (Decimal(20_000), 0),
        ],
    )
    def test_with_homestead(self, just_value, expected):
        assert estimate_new_owner_tax(just_value, ST_PETE, rules=CURRENT) == expected

    def test_without_homestead_taxes_full_just_value(self):
        # 300,000 x 19.9197
        assert estimate_new_owner_tax(Decimal(300_000), ST_PETE) == 5976

    def test_adds_special_assessment(self):
        assert estimate_new_owner_tax(Decimal(300_000), ST_PETE, Decimal(140), CURRENT) == 5118 + 140

    def test_amendment_3_2027(self):
        # 275,000 x 6.293 + 150,000 x 13.6267 = 1,730.58 + 2,044.01
        assert estimate_new_owner_tax(Decimal(300_000), ST_PETE, rules=AMENDMENT_3[2027]) == 3775

    def test_amendment_3_2028(self):
        # 275,000 x 6.293 + 50,000 x 13.6267 = 1,730.58 + 681.34
        assert estimate_new_owner_tax(Decimal(300_000), ST_PETE, rules=AMENDMENT_3[2028]) == 2412

    def test_matches_county_when_there_is_no_cap_gap(self):
        """Parcel 11-31-16-53046-000-0280: just value equals assessed value, so a
        new owner's taxable values match the county's (397,684 school,
        371,273 county)."""
        new_owner = estimate_new_owner_tax(Decimal(422_684), ST_PETE, rules=CURRENT)
        county = estimate_current_tax(Decimal(371_273), Decimal(397_684), ST_PETE)
        assert new_owner == county == 7562


class TestEstimateCurrentTax:
    def test_uses_school_and_county_taxable_values(self):
        # Parcel 36-30-16-78588-003-0060: 52,124 x 6.293 + 25,713 x 13.6267 = 328.02 + 350.38
        assert estimate_current_tax(Decimal(25_713), Decimal(52_124), ST_PETE) == 678

    def test_adds_special_assessment(self):
        assert estimate_current_tax(Decimal(0), Decimal(0), ST_PETE, Decimal('84.00')) == 84


class TestHomesteadRules:
    def test_current_law_carries_forward_until_updated(self):
        assert homestead_rules(2027, amendment_3=False) is CURRENT_LAW[2026]
        assert homestead_rules(2030, amendment_3=False) is CURRENT_LAW[2026]

    def test_amendment_3_by_year(self):
        assert homestead_rules(2027, amendment_3=True) is AMENDMENT_3[2027]
        assert homestead_rules(2029, amendment_3=True) is AMENDMENT_3[2028]

    def test_amendment_3_starts_in_2027(self):
        assert homestead_rules(2026, amendment_3=True) is CURRENT_LAW[2026]

    def test_follows_ballot_status(self):
        with patch.object(tax_estimate, 'AMENDMENT_3_STATUS', 'pending'):
            assert homestead_rules(2027) is CURRENT_LAW[2026]
        with patch.object(tax_estimate, 'AMENDMENT_3_STATUS', 'passed'):
            assert homestead_rules(2027) is AMENDMENT_3[2027]
        with patch.object(tax_estimate, 'AMENDMENT_3_STATUS', 'failed'):
            assert homestead_rules(2027) is CURRENT_LAW[2026]


def test_buyer_tax_year_is_next_year():
    assert buyer_tax_year(date(2026, 9, 30)) == 2027
    assert buyer_tax_year(date(2026, 12, 31)) == 2027
    assert buyer_tax_year(date(2027, 1, 1)) == 2028
