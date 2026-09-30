"""New-owner property tax estimates.

Florida caps a homesteaded owner's assessed value (Save Our Homes). The cap
resets to just value on the January 1 after a sale, so the tax bill shown on
a listing belongs to the seller and can be a fraction of what a buyer pays.

Homestead exemption under current law (Fla. Stat. 196.031):
- The first $25,000 of assessed value is exempt from every levy.
- An additional exemption applies to assessed value above $50,000 and excludes
  school levies. It is adjusted for inflation each year since 2025 ($26,411
  for 2026; PCPAO's 2026 roll confirms it).

Amendment 3 (CS/HJR 1F) is on the November 3, 2026 ballot and needs 60%.
If it passes, the non-school exemption becomes $150,000 in 2027 and $250,000
in 2028, indexed to CPI after that. School levies keep $25,000. People who
establish Florida residency after January 1, 2027 wait five years for the
larger exemption.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)

# Only these PCPAO parcel types can hold a homestead; commercial parcels
# (including 10+ unit apartments) cannot.
HOMESTEAD_PARCEL_TYPES = ('Residential', 'Condo', 'Both')


@dataclass(frozen=True)
class HomesteadRules:
    label: str
    school_exemption: Decimal
    additional_exemption: Decimal = ZERO
    additional_floor: Decimal = Decimal(50_000)
    # Amendment 3 replaces the tiered non-school exemption with one flat amount.
    nonschool_exemption: Decimal | None = None

    def exemptions(self, assessed: Decimal) -> tuple[Decimal, Decimal]:
        """Return the (school, non-school) exemption for an assessed value."""
        school = min(assessed, self.school_exemption)
        if self.nonschool_exemption is not None:
            return school, min(assessed, self.nonschool_exemption)
        additional = min(self.additional_exemption, max(ZERO, assessed - self.additional_floor))
        return school, school + additional


# Keyed by the first tax year each set of rules applies to. The Department of
# Revenue publishes each year's inflation adjustment; until it does, the latest
# published value is the best estimate.
CURRENT_LAW = {
    2026: HomesteadRules('Current law', school_exemption=Decimal(25_000), additional_exemption=Decimal(26_411)),
}
AMENDMENT_3 = {
    2027: HomesteadRules('Amendment 3', school_exemption=Decimal(25_000), nonschool_exemption=Decimal(150_000)),
    2028: HomesteadRules('Amendment 3', school_exemption=Decimal(25_000), nonschool_exemption=Decimal(250_000)),
}

# Update after the November 3, 2026 vote: 'pending', 'passed', or 'failed'.
AMENDMENT_3_STATUS = 'pending'


def _latest(schedule: dict[int, HomesteadRules], tax_year: int) -> HomesteadRules | None:
    years = [year for year in schedule if year <= tax_year]
    return schedule[max(years)] if years else None


def homestead_rules(tax_year: int, amendment_3: bool | None = None) -> HomesteadRules:
    """Rules for a tax year. amendment_3=None follows AMENDMENT_3_STATUS."""
    if amendment_3 is None:
        amendment_3 = AMENDMENT_3_STATUS == 'passed'
    if amendment_3:
        rules = _latest(AMENDMENT_3, tax_year)
        if rules:
            return rules
    return _latest(CURRENT_LAW, tax_year) or CURRENT_LAW[min(CURRENT_LAW)]


def buyer_tax_year(today: date | None = None) -> int:
    """A home bought today is reassessed, in the buyer's name, next January 1."""
    return (today or date.today()).year + 1


@dataclass(frozen=True)
class Millage:
    total: Decimal
    school: Decimal

    @property
    def nonschool(self) -> Decimal:
        return self.total - self.school


def _whole_dollars(amount: Decimal) -> int:
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _bill(school_taxable: Decimal, nonschool_taxable: Decimal, millage: Millage, special_assessment: Decimal) -> int:
    ad_valorem = (max(ZERO, school_taxable) * millage.school + max(ZERO, nonschool_taxable) * millage.nonschool) / 1000
    return _whole_dollars(ad_valorem + special_assessment)


def estimate_new_owner_tax(
    just_value: Decimal,
    millage: Millage,
    special_assessment: Decimal | None = None,
    rules: HomesteadRules | None = None,
) -> int:
    """A buyer's first full-year bill, assessed at just value.

    rules=None means no homestead: a rental, a second home, or an owner who
    didn't file. The non-homestead 10% cap also resets on sale, so it doesn't
    help in year one either.
    """
    school_exemption, nonschool_exemption = rules.exemptions(just_value) if rules else (ZERO, ZERO)
    return _bill(
        just_value - school_exemption,
        just_value - nonschool_exemption,
        millage,
        special_assessment or ZERO,
    )


def estimate_current_tax(
    county_taxable: Decimal,
    school_taxable: Decimal,
    millage: Millage,
    special_assessment: Decimal | None = None,
) -> int:
    """The current owner's bill from the county's taxable values.

    Every non-school levy uses the county taxable value. About 3% of parcels
    get a city senior exemption that lowers the city levy slightly, so this
    can run a little high for them.
    """
    return _bill(school_taxable, county_taxable, millage, special_assessment or ZERO)


@dataclass(frozen=True)
class AlternativeEstimate:
    label: str
    note: str
    amount: int


@dataclass(frozen=True)
class TaxOutlook:
    """What the detail page shows about a buyer's taxes."""

    tax_year: int
    just_value: Decimal
    millage: Millage
    millage_description: str
    special_assessment: Decimal
    current_owner: int | None
    homestead: int | None
    no_homestead: int
    alternative: AlternativeEstimate | None

    @property
    def homestead_increase(self) -> int | None:
        """Signed change from the current owner's bill. Negative is common
        when buying from an investor who has no homestead exemption."""
        if self.homestead is None or self.current_owner is None:
            return None
        return self.homestead - self.current_owner

    @property
    def homestead_difference(self) -> int | None:
        increase = self.homestead_increase
        return abs(increase) if increase is not None else None


def build_tax_outlook(listing, district_millage, today: date | None = None) -> TaxOutlook | None:
    """Estimate a buyer's taxes for a PropertyListing and its TaxDistrictMillage.

    New-owner figures are recomputed from the listing's current just value,
    so they stay right after an on-demand refresh. Whether a parcel can be
    homesteaded, and the current owner's bill, come from the import
    (est_tax_homestead is null when it can't; the county taxable values
    behind est_tax_current aren't stored).
    """
    if district_millage is None or not listing.market_value:
        return None

    millage = Millage(total=district_millage.total_mills, school=district_millage.school_mills)
    tax_year = buyer_tax_year(today)
    special_assessment = listing.special_assessment or ZERO
    homestead = alternative = None
    if listing.est_tax_homestead is not None:
        homestead = estimate_new_owner_tax(listing.market_value, millage, special_assessment, homestead_rules(tax_year))
        alternative = _alternative_estimate(listing.market_value, millage, special_assessment, tax_year)

    return TaxOutlook(
        tax_year=tax_year,
        just_value=listing.market_value,
        millage=millage,
        millage_description=district_millage.rate_description,
        special_assessment=special_assessment,
        current_owner=listing.est_tax_current,
        homestead=homestead,
        no_homestead=estimate_new_owner_tax(listing.market_value, millage, special_assessment),
        alternative=alternative,
    )


def _alternative_estimate(
    just_value: Decimal, millage: Millage, special_assessment: Decimal, tax_year: int
) -> AlternativeEstimate | None:
    if AMENDMENT_3_STATUS == 'pending':
        rules = homestead_rules(tax_year, amendment_3=True)
        if rules is homestead_rules(tax_year, amendment_3=False):
            return None
        return AlternativeEstimate(
            label='If Amendment 3 passes on November 3',
            note=(
                'Raises the non-school homestead exemption to $150,000 in 2027 and $250,000 in 2028. '
                'Needs 60% of the vote. If you establish Florida residency after January 1, 2027, '
                'you wait five years for it.'
            ),
            amount=estimate_new_owner_tax(just_value, millage, special_assessment, rules),
        )
    if AMENDMENT_3_STATUS == 'passed':
        return AlternativeEstimate(
            label='If you move to Florida after January 1, 2027',
            note="Amendment 3's larger exemption starts after five years of Florida residency.",
            amount=estimate_new_owner_tax(
                just_value, millage, special_assessment, homestead_rules(tax_year, amendment_3=False)
            ),
        )
    return None
