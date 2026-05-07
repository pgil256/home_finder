# Search architecture pivot — make the app actually find properties

**Goal:** The deployed app at `homefinder.patbuilds.dev` should reliably return real properties matching real search criteria. Currently a search for "St. Petersburg, $4k–$600k" returns zero results — that's the opposite of "connect people with properties and give them market data."

**Non-goals:** New features. UI redesigns. The visual design and dashboard rendering are fine; the data layer is the problem.

---

## Root cause

The current flow:

1. User submits search form → POST `/scraper/`
2. View calls `run_scrape(search_criteria, limit=15)` synchronously
3. `run_scrape` calls PCPAO's quick-search API with a **hardcoded keyword per city** (`'St. Petersburg': '1ST AVE'` in [`apps/WebScraper/tasks/pcpao_scraper.py:67`](apps/WebScraper/tasks/pcpao_scraper.py:67))
4. PCPAO returns ≤15 properties whose address contains "1ST AVE" — could be any city in Pinellas with a 1st Ave
5. Post-filter applies price range, beds, baths, etc.
6. Most/all get filtered out — user sees zero results

The whole approach is upside down. The repo already has the right tool: `python manage.py import_pcpao_data` bulk-loads PCPAO's full ~400k-row CSV into the DB ([`apps/WebScraper/management/commands/import_pcpao_data.py`](apps/WebScraper/management/commands/import_pcpao_data.py)). With that data loaded, every search becomes a fast indexed DB query against real, complete data — no scraping required.

---

## Current vs target architecture

| Layer | Current | Target |
|---|---|---|
| Source of truth | Per-search live PCPAO scrape (≤15 rows) | Bulk import (~400k rows in Neon) |
| Search latency | 15–30s sync scrape, often returns 0 | < 200ms indexed DB query |
| Filter accuracy | Faked via hardcoded street-name keywords | Real `WHERE city = ... AND market_value BETWEEN ...` |
| Loading state needed? | Yes (and we don't have one) | No (instant) |
| Rate limit needed? | Yes (60s/IP) | No |
| Live scraper role | Primary data path | Optional refresh of one parcel |
| `MAX_SCRAPE_LIMIT` constraint | 15, blocks larger queries | Removed |

---

## Plan

### Phase 1 — Seed the database (one-shot, you decide cadence later)

Run the bulk import locally, pointed at Neon:

```bash
export DATABASE_URL="<neon-url>"
python manage.py import_pcpao_data
```

What this does:
- Downloads PCPAO's `RP_PROPERTY_INFO.csv` (~150 MB)
- Maps DOR use codes → human-readable property type names via [`apps/WebScraper/services/property_types.py`](apps/WebScraper/services/property_types.py)
- Bulk-upserts into `WebScraper_propertylisting` in batches

Expected: ~400k rows, ~10–20 min, ~150 MB on Neon (well under free 512 MB).

Risks:
- PCPAO download URL may have changed (verify [`apps/WebScraper/services/pcpao_importer.py:20`](apps/WebScraper/services/pcpao_importer.py:20))
- DOR code → property type mapping may not cover all rows (check `Unknown` count after import)
- First run could fail partway — importer should be idempotent (uses `update_or_create`), so safe to rerun

### Phase 2 — Repurpose the search form (DB query, no scrape)

**[`apps/WebScraper/views.py`](apps/WebScraper/views.py)** — `web_scraper_view`:
- Remove `run_scrape(...)` call
- Remove rate-limit check (no longer needed — DB queries are cheap)
- Remove `MAX_SCRAPE_LIMIT`
- POST handler builds dashboard URL from form fields and 302s to it
- GET handler unchanged

Form field → dashboard query-param translation needed because the names don't match today:

| Search form field | Dashboard filter |
|---|---|
| `city` | `city` |
| `zip_code` | (not yet supported by `apply_filters` — add) |
| `property_type` | `property_type` |
| `min_value` | `min_price` |
| `max_value` | `max_price` |
| `bedrooms_min` | `beds` |
| `bathrooms_min` | `baths` |
| `year_built_after` | `year_built` |
| `tax_status` | `tax_status` |
| `sqft_min` | (add) |
| `sqft_max` | (add) |

Two ways to fix the mismatch:
- **A.** Rename form fields to match `apply_filters`. Cleaner, but touches the template.
- **B.** Translate names in the view's POST→redirect step. Smaller blast radius.

Recommend **B** for this phase, **A** as cleanup later.

**[`apps/WebScraper/services/filtering.py`](apps/WebScraper/services/filtering.py)** — `apply_filters`:
- Add `zip_code` filter (exact match)
- Add `min_sqft` / `max_sqft` filters on `building_sqft`

### Phase 3 — Demote the scraper to "refresh one property"

The scraper code is still useful for getting fresh data on a specific property the user is interested in. Don't delete it — repurpose it.

**[`apps/WebScraper/views.py`](apps/WebScraper/views.py)** + [`urls.py`](apps/WebScraper/urls.py):
- Add `POST /scraper/property/<parcel_id>/refresh/` route
- Calls `run_scrape({'parcel_id': pid}, limit=1)` — needs scraper API to support single-parcel refresh
- Returns redirect back to `/scraper/property/<pid>/`
- Keep button-level `LoadingButton` spinner (already wired)
- Add a 60s/parcel rate limit (cache-table backed, already in place)

**[`apps/WebScraper/tasks/scrape_data.py`](apps/WebScraper/tasks/scrape_data.py)** — `run_scrape`:
- Add `parcel_id` to accepted `search_criteria` keys
- If present, skip the keyword search, fetch the detail URL directly

This phase is optional for the core pivot, but it's the right home for the existing scraper code.

### Phase 4 — Cleanup

- Delete `MAX_SCRAPE_LIMIT` constant from [`views.py`](apps/WebScraper/views.py)
- Delete `check_rate_limit` and `get_client_ip` from [`task_management.py`](apps/WebScraper/services/task_management.py) (or scope to per-parcel refresh in Phase 3)
- Delete `templates/WebScraper/scraping-progress.html` (orphan since the Celery removal)
- Remove the `psycopg2` cache table reset in `tests/e2e/conftest.py` (no rate limit to reset)
- Update existing E2E tests:
  - F1, F4, F5: now expect 302 → dashboard with the right query string, no DB write
  - F2 (rate limit): delete or rewrite for per-parcel refresh in Phase 3
  - F3 (limit cap): delete (no cap anymore)
  - B1: still valid — submit form, navigate to dashboard
- Update [`docs/plans/2026-05-07-e2e-tests.md`](docs/plans/2026-05-07-e2e-tests.md) — note the F-test changes

### Phase 5 — Refresh strategy (decide, then implement)

The bulk import is a snapshot. PCPAO updates monthly; market values shift. Pick one:

| Option | Effort | Tradeoff |
|---|---|---|
| **Manual** — rerun `import_pcpao_data` when you remember | Zero | Data goes stale, you have to remember |
| **GitHub Actions cron** (weekly/monthly) | ~30 min | Free, runs in GH runner, needs Neon credentials in secrets, max 6h runtime per job |
| **Vercel Cron** | Won't fit | 60s function timeout, the import is 10–20 min |
| **Separate worker** (Fly/Render free tier) | ~2 hr | Adds infra, but is the "right" answer for any future scheduled work |

Recommend **GitHub Actions cron** — free, no extra infra, and the import is one-shot so duration doesn't matter.

---

## Success criteria

1. Search for "St. Petersburg, $4k–$600k" returns 100+ real properties
2. Search returns in < 1s end-to-end
3. No loading state needed — page transitions are instant
4. E2E smoke + functional suites still pass (after F-test updates in Phase 4)
5. The "Refresh this property" flow works on the detail page (Phase 3, optional)

---

## Open questions

1. **Run the bulk import now?** Locally pointed at Neon. ~10–20 min. Will populate Neon to ~150 MB / 400k rows.
2. **Phase 3 or skip?** Per-property refresh is nice-to-have, not must-have. Skipping it means the scraper code becomes dead but the app works fine.
3. **Refresh cadence (Phase 5)?** GitHub Actions cron is the easy answer; weekly or monthly?
4. **Field rename in template (Phase 2 option A vs B)?** Translate-in-view is faster; template rename is cleaner long-term. Pick one.
