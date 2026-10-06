"""Plain-English risk flags for a parcel, built from the county record.

Every flag says what the record shows, why a buyer should care, and what to
ask or inspect. The flags come only from PCPAO columns the monthly import
stores; they are prompts for due diligence, not findings.

Rules checked in October 2026:
- Pinellas evacuation zones run A to E. A is the most exposed to storm surge
  and is ordered out first. Mobile and manufactured homes are ordered out for
  any hurricane, whatever the zone. Evacuation zones are not FEMA flood zones.
- The statewide Florida Building Code took effect on March 1, 2002.
- Condo and co-op buildings of three or more habitable stories need a
  milestone structural inspection at 30 years (some coastal jurisdictions
  require it at 25), then every 10 years, plus a structural integrity reserve
  study (Fla. Stat. 553.899 and 718.112, as amended by HB 913 in 2025).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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
    return listing.subsidence is not None or listing.evac_zone is not None


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
        # Zones A-C already carry the elevation certificate advice.
        flags.append(_waterfront_flag(listing.frontage, mention_certificate=listing.evac_zone not in ('A', 'B', 'C')))

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
