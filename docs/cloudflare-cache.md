# Caching HTML at Cloudflare

Cloudflare fronts the homelab deployment for both public domains. Cacheable HTML carries a one-day shared cache lifetime and a seven-day stale-while-revalidate window. Browsers revalidate on each visit. The cache rules live in Cloudflare. After switching the origin, use a single-file purge for each affected URL on both domains and check the public smoke workflow.

The example below documents the cache rule created for the homefinder domain on October 9, 2026.

## 1. Cache Rule

Cloudflare dashboard → the `patbuilds.dev` zone → Caching → Cache Rules → Create rule.

**When incoming requests match** (custom filter expression):

```
(http.host eq "homefinder.patbuilds.dev")
and not starts_with(http.request.uri.path, "/admin/")
and not (http.request.uri.path in {"/health/" "/api/status/" "/analytics/csrf/"})
and not starts_with(http.request.uri.path, "/analytics/download/")
and not (http.cookie contains "sessionid")
and not (http.cookie contains "csrftoken")
```

The parcel refresh URL needs no exclusion: it only answers `POST`, which Cloudflare never caches.

**Then:**

- Cache eligibility: **Eligible for cache**
- Edge TTL: not set, so the lifetime comes from the origin's headers
- Browser TTL: **Respect origin TTL**. Without this the zone's default (4 hours) replaces the `max-age=0` the app sends, and browsers hold pages that long.

The cookie conditions keep a visitor who has just used the Refresh button (which sets a CSRF cookie and shows a flash message) on uncached pages. The app also marks any response that sets a cookie as `private, no-store`, so a personal page is not stored even if the rule matches.

## 2. Purge after the data changes

The "Refresh PCPAO data" and "Refresh flood data" workflows end by calling `.github/scripts/purge-cdn.sh`, which purges Cloudflare's cache for the hostname. It needs two repository secrets:

| Secret | Value |
|---|---|
| `CLOUDFLARE_ZONE_ID` | Zone ID from the zone's Overview page |
| `CLOUDFLARE_PURGE_TOKEN` | An API token with one permission: Zone → Cache Purge → Purge, limited to this zone |

```bash
gh secret set CLOUDFLARE_ZONE_ID
```

```bash
gh secret set CLOUDFLARE_PURGE_TOKEN
```

Run each from an interactive terminal and paste the value when prompted. Without the secrets the step prints a notice and passes.

## 3. Check it

```bash
curl -sI https://homefinder.patbuilds.dev/ | grep -i cf-cache-status
```

The second request should say `HIT`. The daily smoke test checks the same thing (`test_S0b_cdn_serves_html`) and is skipped for hosts that are not behind Cloudflare.
