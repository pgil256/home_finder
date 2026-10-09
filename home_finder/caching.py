"""CDN caching for pages that are the same for every visitor."""

from __future__ import annotations

from functools import wraps

from django.views.decorators.cache import cache_control

# The county data changes once a month, so Vercel's edge can answer most page
# views without invoking Django or waking the database. The edge keeps a page
# for a day, then serves the stale copy for up to a week while it fetches a
# fresh one. max-age=0 keeps browsers revalidating, so a visitor never holds a
# copy the edge has already replaced.
CDN_MAX_AGE_SECONDS = 86400
CDN_STALE_WHILE_REVALIDATE_SECONDS = 604800

# Vercel's edge uses s-maxage and then removes it from Cache-Control, so a CDN
# in front of Vercel (Cloudflare, on the custom domain) only sees max-age=0
# and treats every page as already stale. CDN-Cache-Control is the standard
# header for telling CDNs apart from browsers: Vercel honors it and passes it
# on, and Cloudflare reads it in preference to Cache-Control.
CDN_CACHE_CONTROL_HEADER = 'CDN-Cache-Control'
CDN_CACHE_CONTROL = (
    f'public, s-maxage={CDN_MAX_AGE_SECONDS}, stale-while-revalidate={CDN_STALE_WHILE_REVALIDATE_SECONDS}'
)

_browser_and_edge = cache_control(
    public=True,
    max_age=0,
    s_maxage=CDN_MAX_AGE_SECONDS,
    stale_while_revalidate=CDN_STALE_WHILE_REVALIDATE_SECONDS,
)


def cdn_cache(view):
    """Mark a view's response as the same for every visitor and cacheable by CDNs."""

    @wraps(view)
    def with_cdn_header(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        response[CDN_CACHE_CONTROL_HEADER] = CDN_CACHE_CONTROL
        return response

    return _browser_and_edge(with_cdn_header)
