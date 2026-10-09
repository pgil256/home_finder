# Production fix and polish plan

**Date:** 2026-10-09
**Goal:** Get the public URL working again, then fix the things a first-time buyer hits in the first minute of using the site. Still ~$0/month: no new paid services, no new Neon storage beyond a few MB.

Follows the [first-time buyer roadmap](2026-09-29-first-time-buyer-roadmap.md), which is complete. This plan came out of a review of the live site on 2026-10-09.

## Status

As of 2026-10-09 every code step has an open pull request with CI green. They are stacked in this order, each on the one before, and none is merged yet:

| Step | Pull request |
|---|---|
| 1. Monitor opens an issue | pgil256/home_finder#21 |
| 3. Address typeahead | pgil256/home_finder#23 |
| 5. Nearby homes | pgil256/home_finder#24 |
| 6. Comps headline | pgil256/home_finder#25 |
| 9. Parcel page tidy-up | pgil256/home_finder#26 |
| 10. Error pages | pgil256/home_finder#27 |
| 4. Typo tolerance (migration 0015) | pgil256/home_finder#28 |
| 7. One audience | pgil256/home_finder#29 |
| 8. Retire the filter builder | pgil256/home_finder#30 |
| 11. Trim the bundle | pgil256/home_finder#31 |
| 2. Cloudflare purge and CDN smoke test | pgil256/home_finder#32 |

Still to do by hand:

- **Step 0.** The cause is narrower than this plan guessed. `homefinder.patbuilds.dev` is attached to the right Vercel project, which marks it "Invalid Configuration": the `homefinder` record in Cloudflare DNS does not point at Vercel, so Cloudflare sends the hostname to some other host running the app with an empty database (its responses have no `X-Vercel-Id` header). In Cloudflare, set the `homefinder` CNAME to `f80956fe97dc79fd.vercel-dns-017.com`, the value Vercel shows for it and the one `pinellasmarketlens.patbuilds.dev` already uses, then find and shut down whatever the old record pointed at.
- **Step 2.** The Cloudflare Cache Rule and the two purge secrets, described in [docs/cloudflare-cache.md](../cloudflare-cache.md).
- **After Step 4 merges.** Run the "Database guard" workflow once. It applies migration 0015 and fills the street-name table. A full data refresh is not needed.

## What was found

Checked on 2026-10-09 against both hosts:

| Host | `/api/status/` parcels | `/health/` |
|---|---|---|
| `homefinder.patbuilds.dev` (README, social cards, E2E default) | 0 | `degraded`, cache table missing |
| `homefinder-jet.vercel.app` (what GitHub deploys to) | 437,582 | `ok` |

1. **The public domain serves the current build against an empty database.** Every lookup there says "No match"; the insights page shows zero parcels. The daily E2E smoke has failed on 2026-10-08 and 2026-10-09 (`test_S1_home_loads`, `test_S1c_address_lookup_no_match`) and nobody was alerted. The domain resolves to Cloudflare, and the deploy GitHub records for `main` goes to a different Vercel URL, so the domain is attached to a second Vercel project or has a different `DATABASE_URL`.
2. **Cloudflare answers `cf-cache-status: DYNAMIC` on HTML.** The `s-maxage` headers from the CDN caching PR (pgil256/home_finder#13) are ignored on the custom domain, so every page view still invokes Django and wakes Neon.
3. **The address box is unforgiving.** Prefix match only: "1700 Gulf Bvld" finds nothing, and a visitor gets no feedback until they submit. The form's own example, "1700 Gulf Blvd", resolves to a single $20M Gulf-front parcel whose page opens with "Current owner pays $286,451/yr".
4. **"Similar Properties" shows the wrong homes.** `property_detail` takes four rows from `idx_city_type_value` with no `ORDER BY`, so Postgres returns the cheapest homes at the 80% bound, from anywhere in the city. A $1,032,109 Clearwater home lists four unrelated homes all valued at about $826K.
5. **The comps headline can mislead.** With three sales spanning $398 to $778 per sqft, the page still leads with "about $1,835,000" for a home the county values at $1.03M and that sold for $900K in 2021. The caveats are there; the dollar figure wins.
6. **Two products in one skin.** The home page says "For Pinellas County home buyers" and then pitches "Exact DB KPIs" and "pandas + numpy". The insights page is headed "Public records EDA" with "Analyst Takeaways" and "IQR outliers".
7. **The legacy filter builder** (`/analytics/`, `templates/analytics/search.html`, 29 KB) is still linked from the footer and the buyer's guide. It only redirects into `/insights/`.
8. **Parcel page rough edges.** "Tax Before Exemptions $283608.00" is unformatted. The owner's name is shown. Beds and baths are mostly empty, so similar-home cards show only square footage.
9. **Bare error pages.** A bad parcel ID returns Django's unstyled "Not Found". There is no `404.html` or `500.html`.
10. **Dead weight in the serverless bundle.** `selenium`, `webdriver-manager` and `beautifulsoup4` ship to Vercel for the on-demand scraper only; `djangorestframework` is in `INSTALLED_APPS` and never imported.

## Guardrails

- Neon is at about 260 MB of 512 MiB. Any new index gets its size checked with `pg_total_relation_size` on the local Postgres before it goes near production. No `pg_trgm` index on `address` (437k rows; likely 40+ MB).
- Each full refresh costs about 200 MB of egress. Nothing here needs one. Migrations run from a workflow, not a deploy (deploys don't migrate).
- Keep pages cacheable: no cookies or CSRF on GET pages that carry `@cdn_cache`.
- One PR per step, CI green, smoke green against the Vercel URL before merge.

---

## Implementation plan

### Step 0 — Point the domain at the right project (config, no PR) — do today

Done by hand in Vercel and Cloudflare; nothing in the repo changes.

1. In Vercel, find which project owns `homefinder.patbuilds.dev`. The project GitHub deploys to is the one whose production alias is `homefinder-jet.vercel.app`.
2. If the domain is on another project: remove it there and add it to the deploying project. Vercel will show the CNAME it wants; in Cloudflare, make the `homefinder` CNAME match it.
3. If the domain is on the right project but the database is wrong: set that project's `DATABASE_URL` to the Neon "Home Finder (2026-10)" connection string (same value as the `E2E_DATABASE_URL` GitHub secret) and redeploy.
4. Verify: `curl https://homefinder.patbuilds.dev/api/status/` reports 437k parcels and `/health/` is `ok`. Then run the E2E workflow by hand and confirm it passes.
5. If the other project exists only by accident, delete it so it stops deploying.

**Acceptance:** the two hosts answer the same numbers; the scheduled E2E passes.

### Step 1 — Make the monitor shout (S)

- `tests/e2e/test_smoke.py`: add `test_S0_has_data` that reads `/api/status/` and fails if `total_properties` is below 400,000 or `last_updated` is older than 45 days. Put it first so a wipe or a misrouted domain is the first line in the log.
- `.github/workflows/e2e.yml`: on failure of the scheduled run, open or update a GitHub issue titled "Production smoke failed" (the `actions/github-script` pattern, or a small step with `gh issue create` guarded by `gh issue list`). Two failed days without a notification is how this one slipped.
- Same `on failure` step in `db-guard.yml`, which is designed to fail when it rebuilds.
- README: state both URLs and which one GitHub deploys to.

**Acceptance:** dispatch E2E against a URL that returns zero parcels; an issue appears.

### Step 2 — Cache HTML at Cloudflare (config + S)

Cloudflare does not cache HTML unless told to, so the `Cache-Control: s-maxage=86400` the app sends is wasted on the custom domain.

- Cloudflare Cache Rule for the host: cache eligible, "respect origin" TTL, so `s-maxage` and `stale-while-revalidate` from `home_finder/caching.py` apply. Bypass cache when the request has a `sessionid` or `csrftoken` cookie, and for `/admin/*`, `/health/`, `/api/status/`, `/analytics/csrf/`, `/analytics/*/refresh/`, `/analytics/download/*`.
- The `_cache_busted` redirects after a refresh or a rate limit already carry a timestamp, so flash messages still render.
- Purge the Cloudflare cache from the refresh workflow after an import, with a `CLOUDFLARE_ZONE_ID` and a purge-only API token in GitHub secrets. Otherwise a parcel page can show last month's values for up to a week after the data changes.
- Add `tests/e2e/test_smoke.py::test_S0b_cdn_serves_html` that fetches `/` twice and expects `cf-cache-status: HIT` on the second request.

**Acceptance:** a repeat fetch of `/` returns `cf-cache-status: HIT`; a parcel page after a refresh shows the new value.

### Step 3 — Address typeahead (M)

The prefix query is already served by `idx_address_prefix`, so suggestions are cheap. This is the biggest change to how the site feels.

- New view `address_suggest` at `/lookup/suggest/?q=`: normalise with `address_candidates`, run `address__startswith` on the first candidate that matches, return up to 8 rows as JSON (`parcel_id`, `address`, `city`, `market_value`). No `ORDER BY` (same reasoning as `lookup_parcels`), sorted in Python. Decorated with `@cdn_cache` and `@require_GET`; minimum query length 3 so the edge caches a bounded set of keys. Add it to `robots.txt` `Disallow`.
- `static/js/dev/lookup.js` (new bundle, loaded on the home and lookup pages): debounce 150 ms, fetch suggestions, render a listbox under the input with full keyboard and ARIA support (`role="combobox"`, `aria-activedescendant`), Enter on a highlighted row goes straight to the parcel page. Jest tests for the keyboard handling. Without JS the form works as today.
- `templates/analytics/partials/lookup-form.html`: wire the attributes; change the placeholder from "1700 Gulf Blvd" to an ordinary house (pick one from the fixture that exists in production, e.g. a 3-bed in Largo or Pinellas Park under the county median).
- Smoke test: `/lookup/suggest/?q=1029 cha` lists the Charles St parcel in under a second.

**Acceptance:** typing three characters shows matches; arrow keys and Enter open a parcel; the endpoint is cacheable and crawler-blocked.

### Step 4 — Typo tolerance without a big index (M)

- New small table `StreetName` (`name`, `city`, `parcel_count`), rebuilt by the import from `DISTINCT` street names (roughly 10k rows, a few hundred KB). A `pg_trgm` GIN index on this table is affordable; the extension already exists in Neon.
- When `address_q` finds nothing, split the query into house number and street, find the nearest street names by trigram similarity (threshold 0.4, top 3), and rerun the prefix match with each. Return results under a "Showing results for 1700 GULF BLVD" line, with the original query shown as a link to search literally.
- On the "No match" page, list the nearest street names as links.
- Unit tests in `test_address_lookup.py`: "Bvld" → "BLVD", "Mirrer Lake" → "MIRROR LAKE", a bare street name with no house number.
- Migration runs from the refresh workflow, which already does `migrate --noinput`. Dispatch it after merge.

**Acceptance:** "1700 Gulf Bvld" finds 1700 GULF BLVD; the new table and index are under 2 MB on production.

### Step 5 — Fix "Similar Properties" (S)

- `property_detail`: restrict to the same `neighborhood_code` (indexed by `idx_neighborhood`) and the same `comp_type_bucket`, order by absolute difference from the subject's `market_value`, take four. Fall back to the city query only when the neighborhood has fewer than four candidates, and then order by value distance as well.
- Rename the card "Nearby homes the county values alike" and say in one line what it is. It is not comps; the sales section is.
- Drop beds and baths from the cards; they are null for almost every parcel. Show living area, year built and value.
- Test in `test_views.py`: given one subject and six candidates at various values and neighborhoods, the four shown are the nearest by value in the same neighborhood.

**Acceptance:** the $1.03M Clearwater example shows homes from its own neighborhood near $1.0M, not four at $826K.

### Step 6 — Honest comps headline (S)

- In `build_sales_outlook`, add `CompSummary.confident = count >= 5`.
- Template: when not confident, lead with the per-sqft range and the count ("3 sales in the last 12 months, $398 to $778/sqft") and show the indicated value as a secondary line prefixed "which would put this home around". When confident, keep today's layout.
- Keep `MIN_COMPS = 3` so the section still appears for small neighborhoods.
- Update `test_views.py` assertions for both branches.

**Acceptance:** with three comps the first number a reader sees is the range.

### Step 7 — One audience: the buyer (M)

- `templates/Pages/home.html`: remove the "Engineering proof at a glance" grid. Replace it with one line, "Built on 437,000 county records, refreshed monthly", linking to About. The About page keeps the full architecture story; move the KPI tiles there.
- `templates/analytics/market-insights.html`: plain-language headings. "Exact Market KPIs" → "The market at a glance"; "Analyst Takeaways" → "What stands out"; "Auditable Outliers" → "Homes that stand out, and why"; "Value Percentiles" → "Where prices fall"; "Market vs Assessed Value" → "County value vs what owners are taxed on". Drop the "Public records EDA / pandas + numpy" eyebrow. Explain IQR in a `<details>` under the outliers table, not in the heading. Keep the methodology section; it is the honest part.
- Title tags and meta descriptions to match.
- Update `test_smoke.py` strings that assert on headings.

**Acceptance:** no page a buyer lands on uses "EDA", "KPI", "IQR" or "pandas" outside the About page and the methodology section.

### Step 8 — Retire the filter builder (M)

The monthly-budget search is the only thing `search.html` has that `/insights/` does not.

- Move the "Or start from a monthly budget" block (and its `affordability.js` hookup) into the insights filter sidebar, writing `min_price`/`max_price` on the form.
- Make `/analytics/` a 301 to `/insights/` with the query string preserved, like `/analytics/dashboard/` already does. Keep the `scraper` URL name on the redirect so `{% url 'scraper' %}` still resolves during the change, then remove the footer "Filter Builder" link and reword the buyer's guide line to point at Explore the market.
- Delete `templates/analytics/search.html`, `web_scraper_view`'s GET branch and the `data-restore-search` code in `common.js`. `localStorage` search restore moves to the insights page or is dropped.
- Delete the `search.html` tests and add a redirect test.

**Acceptance:** `/analytics/?city=Dunedin` lands on insights filtered to Dunedin; budget search works from the insights sidebar; `search.html` is gone.

### Step 9 — Parcel page tidy-up (S)

- Format every money field with the `dollars` filter (`tax_amount` at the "Tax Before Exemptions" row is the one that renders `$283608.00`). Grep the template for `$` followed by a variable to catch others.
- Remove the "Owner Information" card. The name is on the PCPAO link for anyone who needs it; it does not help a buyer and reads as surveillance.
- Hide the beds and baths rows when null instead of leaving gaps; they are null for nearly all parcels.
- Rename "Valuation & Tax Information" to "The county's numbers" and move it below the risk card; a buyer reads taxes-if-you-buy, cost per month, sales, risks, then the raw record.
- Update the parcel-page screenshot in `docs/img/`.

**Acceptance:** no unformatted dollar amounts; no owner name; section order matches the buyer's questions.

### Step 10 — Error pages (S)

- `templates/404.html` and `templates/500.html` extending `base.html`. The 404 says the parcel or page wasn't found and shows the lookup form; the 500 says the data is unavailable and links the status endpoint. `500.html` must not touch the database or `request.user`.
- A parcel 404 (`get_object_or_404` in `property_detail`) should say the parcel ID isn't in the current county file and offer the lookup box.
- Tests: `test_views.py` asserts the 404 for a bad parcel ID contains the lookup form and the site header.

**Acceptance:** `/analytics/property/00-00-00-00000-000-0000/` shows a styled page with the search box.

### Step 11 — Trim the serverless bundle (S)

- Split `requirements.txt`: web runtime (`Django`, `pandas`, `openpyxl`, `reportlab`, `requests`, `python-decouple`, `whitenoise`, `dj-database-url`, `psycopg2-binary`, `gunicorn`) and `requirements-scrape.txt` (`selenium`, `webdriver-manager`, `beautifulsoup4`, `chardet`). Test tools move to `requirements-dev.txt`. Vercel installs only `requirements.txt`; the workflows and CI install what they need.
- Remove `rest_framework` from `INSTALLED_APPS` and `djangorestframework` from requirements; nothing imports it.
- The on-demand parcel refresh imports the scraper lazily already. Guard it: if `selenium` isn't importable, `property_refresh` returns a message saying refresh isn't available on this host, instead of a 500.
- Drop the `selenium` logger from `LOGGING` if nothing else references it.
- Measure: note the Vercel function size and cold start before and after in the PR description.

**Acceptance:** CI green with the split files; the Vercel function is smaller; refresh degrades gracefully.

### Optional follow-ups

- Make `homefinder-jet.vercel.app` redirect to the custom domain once Step 0 is verified, so there is one canonical URL for search engines.
- A Cloudflare cache-hit ratio check in the daily smoke.
- Store beds and baths from the on-demand refresh only when both are present, so the few parcels that have them show them.

### Sequencing

Step 0 today, by hand. Step 1 next, so the monitor catches a regression of Step 0. Step 2 is config plus one small PR and can go any time after Step 0. Steps 3 and 4 are the user-facing win and depend on nothing else; Step 4 needs a workflow dispatch after merge for its migration. Steps 5, 6, 9 and 10 are independent small PRs. Step 7 before Step 8, since Step 8 edits the insights sidebar Step 7 renames. Step 11 last; it touches CI and deploy and is easiest to review alone.
