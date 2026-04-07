import re
from django import template

register = template.Library()


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
