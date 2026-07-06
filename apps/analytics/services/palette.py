"""Shared brand palette for dashboard charts and file exports.

Single source of truth for the colors used by both the Chart.js payloads in
``market_insights`` and the openpyxl/ReportLab output in ``exports``, so the
on-screen dashboard and the downloaded workbook/PDF stay visually consistent.
"""

# Core brand hues (hex, with leading '#').
PRIMARY = '#0D7377'  # brand teal — primary series and export headers
PRIMARY_DARK = '#084547'  # darker teal — borders on the primary series
ACCENT = '#FF6B6B'  # coral — secondary series (e.g. parcel counts)
ACCENT_DARK = '#CC5656'  # darker coral — borders on the accent series

# Translucent fills derived from PRIMARY (Chart.js line/scatter fills).
PRIMARY_FILL_SOFT = 'rgba(13, 115, 119, 0.16)'
PRIMARY_FILL_MEDIUM = 'rgba(13, 115, 119, 0.55)'

# Neutral tones for export chrome.
WHITE = '#FFFFFF'
MUTED = '#6C757D'  # subtitle grey
BORDER = '#CBD5E1'  # table outer border
BORDER_LIGHT = '#E2E8F0'  # table inner grid


def openpyxl_rgb(color: str) -> str:
    """Return an ``RRGGBB`` string (no leading ``#``) as openpyxl expects."""
    return color.lstrip('#')
