"""Plain-English risk flags for a parcel, built from the county record.

Every flag says what the record shows, why a buyer should care, and what to
ask or inspect. The flags come from PCPAO columns the monthly import stores
and the FEMA flood zone the flood refresh stores; they are prompts for due
diligence, not findings.

Rules checked in October 2026:
- Pinellas evacuation zones run A to E. A is the most exposed to storm surge
  and is ordered out first. Mobile and manufactured homes are ordered out for
  any hurricane, whatever the zone. Evacuation zones are not FEMA flood zones.
- The statewide Florida Building Code took effect on March 1, 2002.
- Condo and co-op buildings of three or more habitable stories need a
  milestone structural inspection at 30 years (some coastal jurisdictions
  require it at 25), then every 10 years, plus a structural integrity reserve
  study (Fla. Stat. 553.899 and 718.112, as amended by HB 913 in 2025).
- An insurer can't refuse a home only because its roof is old if the roof is
  under 15 years old. From 15 years it can require an inspection, and must
  still cover the home if the roof has five or more years of useful life left
  (Fla. Stat. 627.7011(5), added in 2022).

Permit years come from the county's RP_PERMITS file, which starts in 1997. In
October 2026, 90% of single-family homes built before 2012 had a roof permit
on record and 74% had one from the last 15 years. Condo units (7%), townhomes
in planned developments (42%) and manufactured homes (36%) mostly don't,
because the association owns the roof or the work isn't permitted per unit,
so a missing permit is only flagged for houses. Only 53% of those houses have
any heating/air permit, so a missing one is never flagged.

Flood zones are FEMA's, at the county's map point for the parcel
(services/flood_zones.py). In zones A and V, the Special Flood Hazard Area, a
federally regulated or insured lender must require flood insurance on a
building (42 U.S.C. 4012a).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .flood_zones import COASTAL_ZONES, MINIMAL_RISK, SFHA_ZONES, SHADED_X
from .permits_importer import PERMIT_RECORDS_START_YEAR

HIGH = 'high'
MEDIUM = 'medium'
INFO = 'info'
GOOD = 'good'
_ORDER = {HIGH: 0, MEDIUM: 1, INFO: 2, GOOD: 3}

EVAC_ZONES = ('A', 'B', 'C', 'D', 'E')
NOT_IN_EVAC_ZONE = 'NONE'

FLORIDA_BUILDING_CODE_YEAR = 2002
# Flag condos a few years ahead of the earliest (25-year) inspection deadline.
CONDO_MILESTONE_WARNING_AGE = 25
ROOF_INSPECTION_AGE = 15
RECENT_HVAC_AGE = 10

# FRONTAGE values that name the water a waterfront parcel sits on. The county's
# waterfront flag is the trigger; most pond-frontage lots are not flagged.
TIDAL_FRONTAGE = ('Gulf', 'Intracoastal', 'Tampa Bay', 'Canal/River')
FRESHWATER_FRONTAGE = ('Lake', 'Pond')

_ELEVATION_CERTIFICATE = 'Ask the seller for an elevation certificate; it can lower the premium.'


@dataclass(frozen=True)
class RiskFlag:
    level: str
    title: str
    why: str
    ask: str


def allowed_evac_zones(exclude_through: str) -> list[str] | None:
    """Zones left after excluding A through `exclude_through`, or None if it isn't a zone.

    'B' leaves C, D, E and parcels outside every zone.
    """
    zone = (exclude_through or '').strip().upper()
    if zone not in EVAC_ZONES:
        return None
    return [*EVAC_ZONES[EVAC_ZONES.index(zone) + 1 :], NOT_IN_EVAC_ZONE]


def evac_filter_label(exclude_through: str) -> str:
    """Label for the "exclude zones A through X" search filter."""
    zone = exclude_through.strip().upper()
    if zone == EVAC_ZONES[0]:
        return 'Outside evacuation zone A'
    if zone == EVAC_ZONES[-1]:
        return 'Not in an evacuation zone'
    return f'Outside evacuation zones A-{zone}'


EVAC_FILTER_CHOICES = [(zone, evac_filter_label(zone)) for zone in EVAC_ZONES]


def has_risk_data(listing) -> bool:
    """False for rows imported before the county's risk columns were stored."""
    return listing.subsidence is not None or listing.evac_zone is not None or listing.flood_zone is not None


def build_risk_flags(listing, today: date | None = None) -> list[RiskFlag]:
    """Flags for a PropertyListing, most serious first."""
    flags: list[RiskFlag] = []
    property_type = (listing.property_type or '').lower()

    if listing.subsidence:
        flags.append(
            RiskFlag(
                HIGH,
                'Subsidence on record',
                "The county's record notes subsidence, which can mean past sinkhole activity or settling. "
                'It affects insurance and resale.',
                'Ask for the engineering report and proof of repair, and get insurance quotes before your '
                'inspection period ends.',
            )
        )

    if listing.contamination:
        flags.append(
            RiskFlag(
                HIGH,
                'Contamination on record',
                "The county's record flags environmental contamination on or affecting this parcel.",
                "Ask for environmental reports, and check the Florida Department of Environmental Protection's "
                'records for the site.',
            )
        )

    flags.extend(_evacuation_flags(listing.evac_zone))

    # Zones A-C already carry the elevation certificate advice.
    surge_zone = listing.evac_zone in ('A', 'B', 'C')
    in_sfha = listing.flood_zone in SFHA_ZONES
    flags.extend(_flood_zone_flags(listing.flood_zone, listing.static_bfe, mention_certificate=not surge_zone))

    is_manufactured = 'mobile home' in property_type or 'manufactured home' in property_type
    if is_manufactured:
        flags.append(
            RiskFlag(
                MEDIUM,
                'Mobile or manufactured home',
                'Pinellas County orders mobile and manufactured homes to evacuate for any hurricane, '
                'whatever the zone.',
                'Ask about tie-downs and the year it was built, and get insurance quotes early.',
            )
        )

    if listing.waterfront:
        flags.append(_waterfront_flag(listing.frontage, mention_certificate=not surge_zone and not in_sfha))

    if listing.seawall:
        flags.append(
            RiskFlag(
                MEDIUM,
                'Seawall',
                "Seawall upkeep and replacement are the owner's cost.",
                'Ask how old it is, and have a marine contractor inspect it.',
            )
        )

    # A manufactured-home "land condo" is a lot, not a condo building.
    is_condo = 'condo' in property_type and not is_manufactured
    flags.extend(_age_flags(listing.year_built, is_condo, today or date.today()))

    is_house = property_type.startswith('single family') or 'duplex' in property_type
    flags.extend(_permit_flags(listing, is_house, today or date.today()))

    if listing.historic_landmark:
        flags.append(
            RiskFlag(
                INFO,
                'Local historic landmark',
                'Exterior changes and demolition need approval from the local historic preservation board.',
                'Ask the city what work needs a certificate of appropriateness before you plan renovations.',
            )
        )

    # sorted() is stable, so flags of the same level keep the order above.
    return sorted(flags, key=lambda flag: _ORDER[flag.level])


def _waterfront_flag(frontage: str | None, mention_certificate: bool) -> RiskFlag:
    if frontage in FRESHWATER_FRONTAGE:
        return RiskFlag(
            INFO,
            f'Waterfront: {frontage}',
            'Lakes and ponds can rise in heavy rain even far from the coast.',
            'Ask whether the lot has flooded, and check the FEMA flood map.',
        )
    return RiskFlag(
        MEDIUM,
        f'Waterfront: {frontage}' if frontage in TIDAL_FRONTAGE else 'Waterfront',
        'Homes on the water face more wind and flood exposure, and insurance usually costs more.',
        'Get flood and wind insurance quotes before you make an offer.'
        + (f' {_ELEVATION_CERTIFICATE}' if mention_certificate else ''),
    )


def _evacuation_flags(zone: str | None) -> list[RiskFlag]:
    not_flood_zone = 'Evacuation zones are about storm surge, not FEMA flood zones. Check the flood map as well.'
    if zone == 'A':
        return [
            RiskFlag(
                HIGH,
                'Evacuation zone A',
                'Zone A is the most exposed to storm surge and is ordered to leave first.',
                f'Get a flood insurance quote before you make an offer. {_ELEVATION_CERTIFICATE}',
            )
        ]
    if zone in ('B', 'C'):
        return [
            RiskFlag(
                MEDIUM,
                f'Evacuation zone {zone}',
                f'Zone {zone} is ordered to leave for stronger storms, after zone A.',
                f'Get a flood insurance quote. {_ELEVATION_CERTIFICATE}',
            )
        ]
    if zone in ('D', 'E'):
        return [
            RiskFlag(
                INFO,
                f'Evacuation zone {zone}',
                f'Zone {zone} is among the last ordered to leave, for the strongest storms.',
                not_flood_zone,
            )
        ]
    if zone == NOT_IN_EVAC_ZONE:
        return [
            RiskFlag(
                GOOD,
                'Not in an evacuation zone',
                "This parcel is outside the county's storm-surge evacuation zones.",
                not_flood_zone,
            )
        ]
    return []


def _flood_zone_flags(zone: str | None, bfe, mention_certificate: bool) -> list[RiskFlag]:
    if zone in SFHA_ZONES:
        coastal = zone in COASTAL_ZONES
        why = (
            f"FEMA's flood map puts this parcel in zone {zone}, a Special Flood Hazard Area: at least a 1% chance "
            'of flooding in any year'
            + (', with wave action on top of rising water. ' if coastal else '. ')
            + 'Lenders must require flood insurance on a mortgaged building here, and it can cost thousands of '
            'dollars a year.'
        )
        if bfe:
            why += f' The base flood elevation is {float(bfe):g} feet.'
        return [
            RiskFlag(
                HIGH,
                f'FEMA flood zone {zone}' + (' (coastal high hazard)' if coastal else ''),
                why,
                'Get a flood insurance quote before you make an offer, and ask the seller whether the home has '
                'flooded or had a flood claim.' + (f' {_ELEVATION_CERTIFICATE}' if mention_certificate else ''),
            )
        ]
    if zone == SHADED_X:
        return [
            RiskFlag(
                INFO,
                'Moderate flood risk (FEMA zone X, shaded)',
                "FEMA's flood map puts this parcel between the 1% and 0.2% annual-chance flood lines. Lenders "
                "don't require flood insurance here, but these areas do flood.",
                "Get a flood insurance quote anyway; it usually costs less here. Homeowners insurance doesn't "
                'cover flooding.',
            )
        ]
    if zone == MINIMAL_RISK:
        return [
            RiskFlag(
                GOOD,
                "Outside FEMA's high-risk flood zones",
                "FEMA's flood map puts this parcel in zone X, an area of minimal flood hazard, so lenders don't "
                'require flood insurance.',
                "Homes here can still flood in heavy rain, and homeowners insurance doesn't cover it. Ask what a "
                'flood policy would cost.',
            )
        ]
    return []


def _permit_flags(listing, is_house: bool, today: date) -> list[RiskFlag]:
    year_built = listing.year_built
    if not year_built:
        return []

    flags: list[RiskFlag] = []
    # A permit from the year the home was built, or earlier, is for the
    # original roof or a building that stood there before.
    roof_year = listing.roof_permit_year if (listing.roof_permit_year or 0) > year_built else None
    roof_age = today.year - (roof_year or year_built)
    if roof_year and roof_age < ROOF_INSPECTION_AGE:
        flags.append(
            RiskFlag(
                GOOD,
                f'Roof permit in {roof_year}',
                f"The county's record shows a roof permit issued in {roof_year}. A permit can cover a repair "
                'as well as a new roof.',
                'Ask the seller whether the whole roof was replaced, and for the contract or warranty. '
                'Insurers will ask how old the roof is.',
            )
        )
    elif is_house and roof_age >= ROOF_INSPECTION_AGE:
        if roof_year:
            title = f'Last roof permit was in {roof_year}'
            record = f"The county's most recent roof permit for this home is from {roof_year}."
        else:
            title = 'No roof permit on record'
            record = (
                f"The county's permit records go back to {PERMIT_RECORDS_START_YEAR} and show no roof permit for "
                f'this home, built in {year_built}.'
            )
        flags.append(
            RiskFlag(
                MEDIUM,
                title,
                f'{record} Florida insurers can require an inspection before covering a roof '
                f'{ROOF_INSPECTION_AGE} years or older, and some decline older roofs.',
                "Ask the seller for the roof's age and material, and get insurance quotes before your inspection "
                'period ends. Tile and metal roofs last longer than shingle.',
            )
        )

    hvac_year = listing.hvac_permit_year
    if hvac_year and hvac_year > year_built and today.year - hvac_year < RECENT_HVAC_AGE:
        flags.append(
            RiskFlag(
                GOOD,
                f'Heating and air permit in {hvac_year}',
                f"The county's record shows a heating or air-conditioning permit issued in {hvac_year}.",
                'Ask what was replaced, and whether a warranty transfers to you.',
            )
        )
    return flags


def _age_flags(year_built: int | None, is_condo: bool, today: date) -> list[RiskFlag]:
    if not year_built:
        return []

    flags: list[RiskFlag] = []
    age = today.year - year_built
    if is_condo and age >= CONDO_MILESTONE_WARNING_AGE:
        flags.append(
            RiskFlag(
                MEDIUM,
                f'Condo building about {age} years old',
                'Florida requires condo buildings of three or more stories to pass a milestone structural '
                'inspection at 30 years (25 in some coastal areas) and to fund reserves for structural repairs. '
                'Either can mean a special assessment or higher dues.',
                'Ask the association for the milestone inspection report, the structural integrity reserve study, '
                'the reserve balance, and any pending special assessments.',
            )
        )
    if year_built < FLORIDA_BUILDING_CODE_YEAR:
        flags.append(
            RiskFlag(
                INFO,
                f'Built in {year_built}, before the 2002 Florida Building Code',
                'Homes built before the statewide code took effect in March 2002 predate its wind standards, '
                'and insurers price that in.',
                'Ask for a wind-mitigation report and a 4-point inspection. Many insurers require them for older '
                'homes, and wind features can earn discounts.',
            )
        )
    return flags
