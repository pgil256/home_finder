import re
import urllib.parse

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def street_view_url(address, city, zip_code, size='640x360'):
    """Build a Google Street View Static API URL for a property.

    Returns '' (empty string) if GOOGLE_STREET_VIEW_API_KEY isn't configured —
    template falls back to placeholder. No metadata pre-check (would require
    one API call per card per page render); if an address has no imagery,
    Google returns the standard 'no imagery' sign-image, which the template's
    existing onerror handler doesn't trip on (it's still a valid 200).

    Cost reminder: image loads bill at ~$7 / 1000 to whoever owns the API key.
    """
    api_key = getattr(settings, 'GOOGLE_STREET_VIEW_API_KEY', '')
    if not api_key or not address:
        return ''
    parts = [address]
    if city:
        parts.append(city)
    parts.append('FL')
    if zip_code:
        parts.append(zip_code)
    params = {
        'size': size,
        'location': ', '.join(parts),
        'key': api_key,
    }
    return f'https://maps.googleapis.com/maps/api/streetview?{urllib.parse.urlencode(params)}'


@register.filter
def clean_property_type(value):
    """Strip DOR use code prefix from property type.

    Converts '0430 Condominium' to 'Condominium',
    '0110 Single Family Home' to 'Single Family Home', etc.
    """
    if not value:
        return 'Unknown'
    # Strip leading DOR code (4 digits + space)
    cleaned = re.sub(r'^\d{4}\s+', '', str(value))
    return cleaned or value


@register.filter
def format_price(value):
    """Format price with $ and commas, or 'Contact for Price' if unavailable."""
    if value is None:
        return 'Contact for Price'
    try:
        num = float(value)
        if num == 0:
            return 'Contact for Price'
        return f'${num:,.0f}'
    except (ValueError, TypeError):
        return 'Contact for Price'
