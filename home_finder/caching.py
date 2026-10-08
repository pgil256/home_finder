"""CDN caching for pages that are the same for every visitor."""

from __future__ import annotations

from django.views.decorators.cache import cache_control

# The county data changes once a month, so Vercel's edge can answer most page
# views without invoking Django or waking the database. The edge keeps a page
# for a day, then serves the stale copy for up to a week while it fetches a
# fresh one. max-age=0 keeps browsers revalidating, so a visitor never holds a
# copy the edge has already replaced.
CDN_MAX_AGE_SECONDS = 86400
CDN_STALE_WHILE_REVALIDATE_SECONDS = 604800

cdn_cache = cache_control(
    public=True,
    max_age=0,
    s_maxage=CDN_MAX_AGE_SECONDS,
    stale_while_revalidate=CDN_STALE_WHILE_REVALIDATE_SECONDS,
)
