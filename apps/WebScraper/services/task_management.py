from __future__ import annotations

import logging
import time
from typing import Any, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

SCRAPE_RATE_LIMIT_SECONDS = 60


def _safe_cache_get(key: str, default: Any = None) -> Any:
    try:
        return cache.get(key, default)
    except Exception as e:
        logger.warning("Cache GET failed for %s: %s", key, e)
        return default


def _safe_cache_set(key: str, value: Any, timeout: Optional[int] = None) -> bool:
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except Exception as e:
        logger.warning("Cache SET failed for %s: %s", key, e)
        return False


def get_client_ip(request) -> str:
    """Extract client IP from request, accounting for proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def check_rate_limit(client_ip: str) -> Optional[int]:
    """Return seconds to wait if rate-limited, else None.

    Cache failures fail open (request allowed) so a Redis blip doesn't 500 the page.
    """
    rate_key = f'scrape_rate:{client_ip}'
    last_submission = _safe_cache_get(rate_key)
    if last_submission:
        wait_seconds = SCRAPE_RATE_LIMIT_SECONDS - (time.time() - last_submission)
        if wait_seconds > 0:
            return int(wait_seconds)
    _safe_cache_set(rate_key, time.time(), timeout=SCRAPE_RATE_LIMIT_SECONDS)
    return None
