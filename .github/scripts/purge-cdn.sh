#!/usr/bin/env bash
# Drop Cloudflare's cached copies of the site after the data changes.
#
# Pages are cached at the edge for a day and may be served stale for a week
# more (home_finder/caching.py), so without this a parcel page can show last
# month's values well after an import.
#
# Needs two repository secrets, passed in as environment variables:
#   CLOUDFLARE_ZONE_ID      the zone the site's domain lives in
#   CLOUDFLARE_PURGE_TOKEN  an API token with only Zone > Cache Purge > Purge
# Without them this prints a notice and succeeds, so the data job still passes
# before the secrets exist. A failed purge is a warning for the same reason:
# the import already worked, and the cache expires on its own.
#
# Usage: purge-cdn.sh <hostname>
set -euo pipefail

host="${1:?usage: purge-cdn.sh <hostname>}"

if [ -z "${CLOUDFLARE_ZONE_ID:-}" ] || [ -z "${CLOUDFLARE_PURGE_TOKEN:-}" ]; then
  echo "::notice::Cloudflare cache not purged: CLOUDFLARE_ZONE_ID or CLOUDFLARE_PURGE_TOKEN is not set."
  exit 0
fi

# Purge by hostname, so other sites in the same zone keep their cache.
response=$(curl --silent --show-error --max-time 30 \
  --request POST "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/purge_cache" \
  --header "Authorization: Bearer ${CLOUDFLARE_PURGE_TOKEN}" \
  --header "Content-Type: application/json" \
  --data "{\"hosts\":[\"${host}\"]}") || {
  echo "::warning::Cloudflare cache purge request failed for ${host}."
  exit 0
}

if echo "$response" | grep -q '"success": *true'; then
  echo "Purged Cloudflare's cache for ${host}."
else
  echo "::warning::Cloudflare refused the cache purge for ${host}: ${response}"
fi
