# Home Finder Development Session Notes

**Last Updated:** January 8, 2026

---

## Session 1: Bug Fixes (January 7, 2026)

Fixed 14+ critical bugs preventing the pipeline from running end-to-end.

### Changes Made

1. **Duplicate Middleware Removed** - `home_finder/settings.py`
2. **Admin Field References Fixed** - `apps/WebScraper/admin.py`
3. **Broken URL Patterns Removed** - `apps/WebScraper/urls.py`
4. **View Context Fixed** - `apps/WebScraper/views.py`
5. **Template Variables Fixed** - `templates/WebScraper/web-scraper.html`
6. **Task Chain Data Flow Fixed** - All task files updated to pass data correctly
7. **Celery Configured for Testing** - In-memory broker for development
8. **Database Migrations Recreated**

---

## Session 2: Production Setup (January 8, 2026)

Completed all production configuration and tested end-to-end pipeline.

### Changes Made

#### 1. Visualization Fixes (`apps/WebScraper/tasks/visual_data.py`)
- Added `COLUMN_MAPPING` to translate model fields to display names
- Added calculated columns: `Price Per Sqft`, `Estimated Monthly Payment`
- Made plots resilient to missing columns with `has_columns()` helper
- Changed Plot 5 from "Time on Market" to "Year Built vs. Listing Price"
- Fixed deprecated PyPDF2: `PdfFileMerger` → `PdfMerger`, `PdfFileReader` → `PdfReader`

#### 2. Redis Configuration (`home_finder/settings.py`, `.env`)
- Updated Celery settings to use environment variables
- Added Redis broker/backend URLs to `.env`
- Set `CELERY_TASK_ALWAYS_EAGER=False` for async execution

#### 3. Chrome for Testing Setup
- Downloaded Chrome for Testing v143 to `~/.chrome-for-testing/`
- Updated both scrapers to use Chrome for Testing binary
- Added Service configuration with custom ChromeDriver path

### Files Modified
```
apps/WebScraper/tasks/visual_data.py
apps/WebScraper/tasks/pcpao_scraper.py
apps/WebScraper/tasks/tax_collector_scraper.py
home_finder/settings.py
.env
docs/SESSION_NOTES.md
```

### Commits
```
71a3481 fix: visualization column mapping and PyPDF2 deprecation
0a8eef4 feat: configure Celery to use Redis for production
9bad6fc feat: configure scrapers to use Chrome for Testing
```

---

## Current Status

### Working Components

| Component | Status | Notes |
|-----------|--------|-------|
| Django App | ✅ Working | Runs on `python manage.py runserver` |
| Database | ✅ Working | SQLite with migrations applied |
| Task Chain | ✅ Working | All 6 tasks execute successfully |
| Excel Generation | ✅ Working | Creates PropertyListings.xlsx |
| PDF Generation | ✅ Working | Creates listing reports |
| Visualizations | ✅ Working | 8 charts in Data_Analysis.pdf |
| PDF Concatenation | ✅ Working | Merges reports correctly |
| Redis | ✅ Running | `redis-server` on localhost:6379 |
| Chrome for Testing | ✅ Installed | v143 in ~/.chrome-for-testing/ |
| Selenium Scrapers | ✅ Configured | Both scrapers use Chrome for Testing |

### Pending Configuration

| Component | Status | Action Required |
|-----------|--------|-----------------|
| Email Sending | ⚠️ Needs Config | Generate Gmail App Password |
| Actual Scraping | ⚠️ Untested | Test against live PCPAO/Tax sites |

---

## How to Run

### Development Mode (Testing)

```bash
# Single terminal - tasks run synchronously
cd ~/projects/home_finder
source venv/bin/activate  # or: venv/bin/activate on some systems
python manage.py runserver
```

### Production Mode (Async Tasks)

```bash
# Terminal 1: Start Redis
sudo service redis-server start

# Terminal 2: Start Celery Worker
cd ~/projects/home_finder
venv/bin/python -m celery -A home_finder worker --loglevel=info

# Terminal 3: Start Django
cd ~/projects/home_finder
venv/bin/python manage.py runserver
```

### Access the App
- Web Scraper Form: http://127.0.0.1:8000/scraper/
- Admin Panel: http://127.0.0.1:8000/admin/

---

## What To Do Next

### 1. Enable Email Notifications (Optional)

Gmail requires an App Password for SMTP access:

1. Enable 2-Step Verification on Google Account
2. Go to: https://myaccount.google.com/apppasswords
3. Generate an App Password for "Mail"
4. Update `.env`:
   ```
   EMAIL_HOST_PASSWORD='xxxx xxxx xxxx xxxx'
   ```

### 2. Test Live Scraping

The scrapers are configured but haven't been tested against live sites:

```bash
venv/bin/python << 'EOF'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'home_finder.settings')
django.setup()

from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

scraper = PCPAOScraper(headless=True)
scraper.setup_driver()

# Test search (may need to adjust for current site structure)
results = scraper.search_properties({'city': 'Clearwater'})
print(f"Found {len(results)} properties")

scraper.close_driver()
EOF
```

### 3. Potential Enhancements

- **Error Handling**: Add retry logic for network failures
- **Rate Limiting**: Respect source site rate limits
- **Caching**: Cache scraped data to avoid redundant requests
- **Progress UI**: Verify celery-progress updates work in frontend
- **Data Validation**: Validate scraped data before saving
- **Logging**: Add structured logging for production debugging

### 4. Deployment Considerations

For server deployment:
- Use gunicorn instead of Django dev server
- Configure nginx as reverse proxy
- Set up systemd services for Redis/Celery
- Use environment variables for all secrets
- Enable HTTPS

---

## File Structure Reference

```
home_finder/
├── apps/
│   ├── KeywordSelection/     # Search criteria management
│   ├── Pages/                # Dashboard views
│   └── WebScraper/
│       ├── tasks/
│       │   ├── scrape_data.py         # Celery task orchestration
│       │   ├── pcpao_scraper.py       # Property Appraiser scraper
│       │   ├── tax_collector_scraper.py # Tax Collector scraper
│       │   ├── sort_data.py           # Excel generation
│       │   ├── listings_pdf.py        # PDF generation
│       │   ├── visual_data.py         # Charts & visualization
│       │   └── email_results.py       # Email notifications
│       ├── models.py          # PropertyListing model
│       ├── views.py           # Form handling & pipeline
│       └── urls.py            # URL routing
├── home_finder/
│   ├── settings.py            # Django & Celery config
│   └── celery.py              # Celery app setup
├── templates/
│   └── WebScraper/
│       └── web-scraper.html   # Search form template
├── .env                       # Environment variables
├── requirements.txt           # Python dependencies
└── docs/
    └── SESSION_NOTES.md       # This file
```

---

## Troubleshooting

### Port Already in Use
```bash
# Find and kill process on port 8000
lsof -i :8000
kill -9 <PID>
```

### Redis Connection Failed
```bash
# Check if Redis is running
redis-cli ping  # Should return PONG

# Start Redis
sudo service redis-server start
```

### Chrome/Selenium Errors
```bash
# Verify Chrome for Testing is installed
~/.chrome-for-testing/chrome-linux64/chrome --version

# Test headless mode
~/.chrome-for-testing/chrome-linux64/chrome --headless --no-sandbox --dump-dom https://google.com
```

### Celery Tasks Not Running
```bash
# Check if worker is connected
venv/bin/python -m celery -A home_finder inspect active

# Check Redis has tasks
redis-cli LLEN celery
```

---

## Session 3: Architecture pivot — Celery out, search reworked (May 7, 2026)

Started with a production 500 on `/scraper/` POST. Ended with a different
architecture: Vercel + Neon Postgres only, no Celery/Redis, search backed
by a 437k-row bulk import instead of live scrapes.

### What broke

1. **500 on every scrape submit.** Traceback in Vercel logs showed
   `redis.exceptions.ConnectionError: Error while reading from
   hopper.proxy.rlwy.net:48270 : (104, 'Connection reset by peer')`.
   The Redis on Railway used as Celery broker + Django cache had become
   unreachable. Cache lookup happened on the request path
   (`check_rate_limit` → `cache.get`), so any Redis hiccup 500'd the page.

2. **Search returned wrong results.** Manual test: "St. Petersburg, $4k–$600k"
   returned **0** properties. Root cause in
   [`apps/WebScraper/tasks/pcpao_scraper.py`](../apps/WebScraper/tasks/pcpao_scraper.py:67):
   the live scraper faked city filtering with hardcoded street-name
   keywords (`'St. Petersburg': '1ST AVE'`), then post-filtered the ≤15
   returned properties by price. The keyword search returned random "1st Ave"
   addresses, many out of range or in other cities — typical result was 0.

### What changed

**Architecture:**
- **Out:** Celery, Redis broker, broker-side cache, the `progress/` and
  `status/` URL routes, the `celery-progress` URL include, the
  `home_finder/__init__.py` celery autoload, the Django Redis cache, all
  pipeline tasks (`generate_sorted_properties`, `generate_listing_pdf`,
  `analyze_data`, `send_results_via_email`) from the request path
- **In:** `DatabaseCache` for rate-limit (in Postgres), synchronous flow
  for everything user-facing, bulk-import-as-source-of-truth

**Search flow:**
- POST `/scraper/` no longer scrapes. It translates form field names to
  the dashboard's filter param names and 302s to `/scraper/dashboard/`
  with the query string. Rendering the dashboard becomes a fast indexed
  Postgres query.
- Field rename in `templates/WebScraper/search.html`: `min_value` →
  `min_price`, `max_value` → `max_price`, `bedrooms_min` → `beds`,
  `bathrooms_min` → `baths`, `year_built_after` → `year_built`,
  `sqft_min` → `min_sqft`, `sqft_max` → `max_sqft`. IDs and JS hooks
  unchanged (those don't get submitted).
- `apply_filters` extended with `zip_code`, `min_sqft`, `max_sqft`.
  Property type matching switched from `__in` to `__icontains`-OR so
  "Single Family" matches PCPAO's "Single Family Home".

**Bulk import:**
- PCPAO retired the static `/Data/Downloads/<file>.csv` paths and the
  CSV column schema. New endpoint:
  `POST https://www.pcpao.gov/dal/databasefile/downloadDatabaseFile`
  with `hdn_tbl_name=RP_PROPERTY_INFO&hdn_ftype=csv`, returns a 90 MB zip
  → 333 MB CSV with 81 columns. Mapped the new column names
  (`PARCEL_NUMBER`, `SITE_ADDRESS`, `STR_CITY`, `STR_ZIP`,
  `CNTY_JST_VALUE`, `PROPERTY_USE` etc.) in
  [`pcpao_importer.py`](../apps/WebScraper/services/pcpao_importer.py).
  Added city normalization (`'ST PETERSBURG'` → `'St. Petersburg'`)
  so imports match the search form's dropdown values.
- ORM-based `bulk_create` over WAN to Neon was on track for **5+ hours**
  (~1700 rows/min over us-west-2 from Florida). Wrote
  [`scripts/bulk_import_copy.py`](../scripts/bulk_import_copy.py) using
  PostgreSQL `COPY` into a temp table then
  `INSERT … ON CONFLICT DO UPDATE`. **Full 437k-row load in ~2 minutes.**
  Use this for the initial seed; the GH Actions monthly refresh runs
  from us-east and can use the regular ORM path.

**Downloads:**
- `download_excel` and `download_pdf` now apply the request's filters
  (so the export reflects what the user is browsing, not the whole
  county). Excel capped at 5000 rows, PDF at 200 — both fit Vercel's
  60 s function budget.

**E2E tests:**
- New top-level `tests/e2e/` directory (kept out of `apps/` so the
  default `pytest` invocation doesn't pick it up; run via
  `make e2e-smoke` / `e2e-functional` / `e2e-browser` / `e2e-all`).
- Smoke (S1–S9): 9 read-only HTTP checks, `make e2e-smoke`.
- Functional (F1–F7): 7 write-path checks. F7 is the canary for the
  St. Petersburg bug — fails if the bulk import is missing.
- Browser (B1–B4): Playwright tests for form submit navigation,
  loading-state wiring, property-card click, mobile viewport.
- `.github/workflows/e2e.yml`: smoke against prod every 4 hours,
  manual `workflow_dispatch` for the full suite.
- Plan: [`docs/plans/2026-05-07-e2e-tests.md`](plans/2026-05-07-e2e-tests.md).

**Refresh cadence:**
- `.github/workflows/refresh-data.yml`: monthly cron (5th @ 06:00 UTC)
  + manual dispatch. Runs `python manage.py import_pcpao_data` against
  Neon. Needs `E2E_DATABASE_URL` in GH secrets to function.

### Result

- Search: **< 200 ms** (was 15-30 s)
- "St. Petersburg, $4k–$600k": **106,538 matches** (was 0)
- E2E suite: **20/20 pass in 40 s** against production
- Architecture: **2 services** (Vercel + Neon), all $0 free tier
- Source of truth: **437,434 indexed PCPAO rows in Neon**
- Latest deployed commit: `b4c801e`

### Where we left off

**Done:** Phases 1, 2, 4, 5 of
[`docs/plans/2026-05-07-search-architecture-pivot.md`](plans/2026-05-07-search-architecture-pivot.md).

**Not done — Phase 3 (optional):** A "Refresh this property" button on
the property detail page. Would call the existing PCPAO scraper for one
parcel and update the row in Neon. The bulk import already runs monthly
so this is nice-to-have, not necessary. Would touch:
- new URL `POST /scraper/property/<id>/refresh/`
- new view (and a 60 s/parcel rate limit, reusing
  `services/task_management.py`)
- refresh form on `templates/WebScraper/property-detail.html`
- a `parcel_id`-aware path in `tasks/scrape_data.py:run_scrape`

**Action items on the user's side:**

1. **Add `E2E_DATABASE_URL` GitHub repo secret** (Settings → Secrets and
   variables → Actions → New) — set to the Neon connection string.
   Without it, the monthly refresh and the manual full E2E workflow
   both fail.
2. **Delete unused `neon-crimson-engine` storage** in Vercel dashboard
   (Storage tab → … → Delete). Removes the 18 unused `STORAGE_*` env
   vars left over from the marketplace integration that auto-created
   a duplicate Neon DB. No urgency — it's idle.

### Decisions worth knowing about for next session

- **Vercel Hobby's function timeout is ≥15 s on this account** (Phase 1
  of the E2E session confirmed by a 14.9 s scrape). Don't need to drop
  to `MAX_SCRAPE_LIMIT = 10` etc.
- **Beds/baths are not in `RP_PROPERTY_INFO`.** They live in
  `RP_BUILDING`. The bulk import skips them. Form has beds/baths inputs
  but they currently filter on null columns. To enable them, import
  `RP_BUILDING` and join on parcel_id.
- **PCPAO data drift risk.** Their bulk file column names changed
  significantly between when the importer was first written and now.
  `_search_via_api` in `pcpao_scraper.py` may have similar drift —
  worth re-verifying if Phase 3 ever happens.
- **The 60s rate limit is still live** (`SCRAPE_RATE_LIMIT_SECONDS = 60`
  in `services/task_management.py`) but unused by the new search path.
  Kept around for Phase 3 if/when it lands; harmless otherwise.

### Files added or significantly changed

```
docs/plans/2026-05-07-e2e-tests.md          (plan)
docs/plans/2026-05-07-search-architecture-pivot.md (plan)
scripts/bulk_import_copy.py                 (new — COPY-based loader)
.github/workflows/e2e.yml                   (new — smoke + manual full)
.github/workflows/refresh-data.yml          (new — monthly bulk refresh)
tests/e2e/conftest.py                       (fixtures)
tests/e2e/test_smoke.py                     (S1-S9)
tests/e2e/test_functional.py                (F1-F7)
tests/e2e/browser/test_journeys.py          (B1-B4)

apps/WebScraper/views.py                    (rewritten: sync DB redirect)
apps/WebScraper/urls.py                     (dropped progress/status routes)
apps/WebScraper/services/task_management.py (rate-limit-only, safe cache)
apps/WebScraper/services/filtering.py       (added zip/sqft filters)
apps/WebScraper/services/exports.py         (filter-aware + capped)
apps/WebScraper/services/pcpao_importer.py  (new endpoint + new schema)
apps/WebScraper/management/commands/
    import_pcpao_data.py                    (skip rows missing addr/city)
apps/WebScraper/tasks/scrape_data.py        (Celery task → plain fn)
home_finder/__init__.py                     (no celery autoload)
home_finder/urls.py                         (no celery-progress include)
home_finder/settings.py                     (DatabaseCache, no Celery cfg)
templates/WebScraper/search.html            (form field renames + error)
templates/WebScraper/scraping-progress.html (deleted; orphan)
vercel.json                                 (minimal: framework: django)
Makefile                                    (e2e-* targets)
```

### Commit trail

```
b4c801e Filter and cap exports; add COPY-based bulk loader
42af35e Pivot search to DB query against bulk-imported PCPAO data
eee9ea7 Add E2E functional + browser tests, CI workflow
c929bca Add E2E smoke test suite
550b2bc Drop Celery worker and Redis broker; run scrape inline
```
