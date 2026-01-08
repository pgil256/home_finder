"""
Florida Department of Revenue (DOR) Use Codes to human-readable descriptions.
Reference: https://floridarevenue.com/property/Documents/pt_dr405.pdf
"""

DOR_USE_CODES = {
    '0000': 'Vacant Residential',
    '0100': 'Single Family',
    '0200': 'Mobile Home',
    '0300': 'Multi-Family (2-9 units)',
    '0400': 'Condominium',
    '0500': 'Cooperatives',
    '0600': 'Retirement Homes',
    '0700': 'Miscellaneous Residential',
    '0800': 'Multi-Family (10+ units)',
    '0900': 'Residential Common Elements',
    '1000': 'Vacant Commercial',
    '1100': 'Stores, One Story',
    '1200': 'Mixed Use (Store/Office/Residential)',
    '1300': 'Department Stores',
    '1400': 'Supermarkets',
    '1500': 'Regional Shopping Centers',
    '1600': 'Community Shopping Centers',
    '1700': 'Office Buildings (1-4 stories)',
    '1800': 'Office Buildings (5+ stories)',
    '1900': 'Professional Service Buildings',
    '2000': 'Airports, Marinas, Bus Terminals',
    '2100': 'Restaurants, Cafeterias',
    '2200': 'Drive-In Restaurants',
    '2300': 'Financial Institutions',
    '2400': 'Insurance Company Offices',
    '2500': 'Repair Service Shops',
    '2600': 'Service Stations',
    '2700': 'Auto Sales, Repair, Storage',
    '2800': 'Parking Lots',
    '2900': 'Wholesale Outlets',
    '3000': 'Florist, Greenhouse',
    '3100': 'Drive-In Theater',
    '3200': 'Enclosed Theater',
    '3300': 'Nightclubs, Bars',
    '3400': 'Bowling Alleys',
    '3500': 'Tourist Attractions',
    '3600': 'Camps',
    '3700': 'Race Tracks',
    '3800': 'Golf Courses',
    '3900': 'Hotels, Motels',
    '4000': 'Vacant Industrial',
    '4100': 'Light Manufacturing',
    '4200': 'Heavy Manufacturing',
    '4300': 'Lumber Yards',
    '4400': 'Packing Plants',
    '4500': 'Canneries',
    '4600': 'Other Food Processing',
    '4700': 'Mineral Processing',
    '4800': 'Warehousing',
    '4900': 'Open Storage',
}


def dor_code_to_description(code: str) -> str:
    """Convert DOR use code to human-readable description."""
    code = code.strip() if code else ''
    return DOR_USE_CODES.get(code, f'Unknown ({code})')
