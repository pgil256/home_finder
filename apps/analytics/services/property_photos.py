"""Validation helpers for county-hosted property photos."""

from urllib.parse import urlsplit


def sanitize_county_photo_url(value: object) -> str | None:
    """Return an HTTPS PCPAO URL, or ``None`` for every other value.

    Historical rows may still contain Google Street View URLs. Keeping this
    check at render and ingestion time makes those rows harmless even before a
    cleanup migration has run.
    """
    if not value:
        return None

    candidate = str(value).strip()
    if not candidate or any(character.isspace() or ord(character) < 32 for character in candidate):
        return None

    try:
        parsed = urlsplit(candidate)
        hostname = (parsed.hostname or '').lower().rstrip('.')
        port = parsed.port
    except ValueError:
        return None

    is_county_host = hostname == 'pcpao.gov' or hostname.endswith('.pcpao.gov')
    if (
        parsed.scheme.lower() != 'https'
        or not is_county_host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return None

    return candidate
