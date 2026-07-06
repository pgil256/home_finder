# Portfolio Cleanup & Improvement Plan

**Date:** 2026-07-06
**Goal:** Take Pinellas Market Lens from "good side project" to "polished portfolio piece" by removing scraper-era residue, aligning naming with the rebrand, tightening tests, and improving first-impression presentation.

**Context:** The core code is already strong — `market_insights.py` and `models.py` are showpieces, settings are security-hardened, and CI runs lint → test → build. The problems are almost all *residue*: a dead app, dead deploy configs, misleading names, and internal working docs that a reviewer would stumble over.

---

## Phase 1 — Remove dead weight (~1–2 hours)

The highest-value work. A reviewer who opens the repo and finds an unused `KeywordSelection` app or a `Procfile` for a platform you left will discount everything else.

### 1.1 Delete the KeywordSelection app
It is installed and routed but nothing in the live product links to it — the dashboard uses free-text search, not keyword priorities.
- Remove `apps.KeywordSelection` from `INSTALLED_APPS` (home_finder/settings.py)
- Remove its `include()` from home_finder/urls.py
- Delete `apps/KeywordSelection/` (models, views, fixtures, tests, `load_initial_data` / `load_pinellas_data` commands — verify `load_pinellas_data` isn't the seed path referenced in the README Quick Start first; if it is, move that command into WebScraper before deleting)
- Delete `templates/KeywordSelection/keyword-selection.html`
- Delete `static/js/dev/keywordSelection.js` and `static/js/dev/__tests__/keywordSelection.test.js`; remove the `keywordSelection` entry from webpack.config.js; rebuild `static/js/dist/`
- Check `common.js` for sortablejs usage — if drag-drop was only for keyword ordering, drop `sortablejs` from package.json too

### 1.2 Delete dead deploy configs
Production is Vercel + Neon + GitHub Actions. Remove the Railway/Heroku era:
- `Procfile`, `railway.toml`, `.railwayignore`, `nixpacks.toml`, `runtime.txt`
- Decide on `Dockerfile`: either delete it, or keep it *and* document it in the README as a supported local-container path. Don't leave it ambiguous.

### 1.3 Delete dead tests and templates
- `apps/WebScraper/tests/test_e2e_scrapers.py` (927 lines of Selenium tests for scraping that no longer happens — this is the single biggest chunk of dead code in the repo)
- `templates/WebScraper/web-scraper.html` if it's only a legacy alias (verify no route renders it first)

### 1.4 Clean the docs folder
- Delete `docs/SESSION_NOTES.md` (internal working notes)
- Curate `docs/plans/` (18 files): keep 2–3 that tell the project's story well — e.g. `2026-05-07-search-architecture-pivot.md` and `2026-01-08-architecture-alternatives.md` show real engineering judgment — and delete the rest. Skim each for personal info before deciding.
- Fold `docs/GMAIL_APP_PASSWORD.md` into a short "Email setup" note in the README or a single `docs/SETUP.md`, then delete it. (No secrets in it, but a top-level doc named "GMAIL_APP_PASSWORD" reads badly.)

**Commit checkpoint:** one commit per bullet group; run `make lint && make test && npm test && npm run build` after each.

---

## Phase 2 — Fix the naming mismatch (~1–2 hours)

The product is "Pinellas Market Lens" but the repo is `home_finder` and the core app is `WebScraper` — an app that does no scraping. This is the thing most likely to raise a reviewer's eyebrow after Phase 1.

### 2.1 Rename the `WebScraper` Django app → `analytics` (or `market`)
This is the invasive one, so do it on a branch and verify carefully:
- Rename `apps/WebScraper/` → `apps/analytics/`; update the AppConfig `name`/`label`, imports, `INSTALLED_APPS`, and template/static namespaced paths
- Migrations reference the old app label: either set `label = "WebScraper"` in the new AppConfig (zero-risk, keeps DB tables/migration history intact — recommended, with a one-line comment explaining it), or do a full label migration (riskier, touches `django_migrations` and content types in prod Neon; not worth it)
- Rename URL prefixes: `/scraper/...` routes → `/analytics/...` or promote them to top level, keeping old paths as redirects so existing links and the live-site smoke tests don't break

### 2.2 Rename the repo (optional but cheap)
`pgil256/home_finder` → `pgil256/pinellas-market-lens`. GitHub redirects old URLs automatically. Update: README clone command, CI badge URL, `package.json` name, Vercel project linkage. If you skip this, add one line to the README: "originally built as *home_finder*, pivoted to an analytics product" — it turns the mismatch into a story instead of an oversight.

### 2.3 Decide the fate of `property_refresh`
The per-parcel refresh button is functional but scraper-era in spirit. Pick one:
- **Keep:** add a tooltip on the button and a README line ("data refreshes monthly via GitHub Actions; individual parcels can be refreshed on demand"). It's actually a nice demo of rate-limiting via cache.
- **Remove:** delete the view, `task_management.py`, and the button.
Keeping it is the better portfolio move — just document it.

---

## Phase 3 — Tighten quality (~2–3 hours)

### 3.1 Tests
- Raise `cov-fail-under` from 50 → 60 in pytest.ini
- Add ~5–8 tests to `test_market_insights.py` (currently only 4 tests for 641 lines): empty DataFrame handling, NaN cleaning, IQR outlier logic, percentile edge cases, chart payload shape
- Add isolated unit tests for `filtering.py` filter branches (invalid values, bounds, residential defaults)
- Add a couple of direct tests for `exports.py` (workbook has expected sheets, PDF response has correct content type and non-empty body)
- Expand `marketInsights.test.js` (78 lines) with data-transformation tests; consider raising the Jest coverage threshold from 40%

### 3.2 Small code fixes
- Consolidate `.babelrc` and `babel.config.js` into one `babel.config.js` (env-keyed), or add a comment in each explaining the webpack-vs-Jest split
- Add type hints to `exports.py` (rest of codebase has them; this file is the outlier)
- Wrap export generation in error handling so a ReportLab/openpyxl failure returns a friendly error instead of a 500
- Name the magic colors in `market_insights.py`/`exports.py` (`#0D7377` etc.) as module constants shared by both

### 3.3 UX nits
- Add a favicon (`<link rel="icon">` in base.html — the OG image exists but the favicon doesn't)
- Tooltip on the property-refresh button explaining what it does

---

## Phase 4 — Presentation (~1–2 hours)

What a reviewer sees in the first 30 seconds.

### 4.1 README screenshots
`manual-e2e-screenshots/` already has good captures (dashboard, detail page, mobile). Pick 2–3, optimize them, commit under `docs/img/` (adjust .gitignore's `manual-e2e-screenshots/` rule stays), and embed near the top of the README. A live-site link plus screenshots is the single highest-leverage portfolio improvement.

### 4.2 Architecture section
The README's mermaid diagram is good. Add a short "Design decisions" subsection (3–5 bullets): why exact DB aggregates + capped pandas frames, why Vercel serverless + Neon, why monthly bulk CSV import over live scraping, why DatabaseCache over Redis. These trade-off narratives are what interviewers actually ask about.

### 4.3 Verify the live site
After all changes deploy, click through homefinder.patbuilds.dev: dashboard, filters, a parcel drilldown, both exports, `/health/`. The e2e smoke workflow runs every 4 hours, but do one manual pass — a broken live link is worse than no live link.

---

## Explicitly out of scope (don't bother)

- Dark mode — nice-to-have, low signal for effort
- Refactoring `apply_filters()` into a builder pattern — current code is clear; 14 readable branches beat a clever abstraction at this scale
- Replacing the webpack/Jest toolchain — proportionate to the JS present once keywordSelection is gone
- Chasing 80%+ coverage — 60–65% with meaningful tests reads better than padded coverage

## Order of operations

Phase 1 → Phase 2 → Phase 3 → Phase 4, one commit per logical change, full test suite green between phases. Total: roughly 6–9 hours. Phases 1 and 4 alone (~3 hours) capture most of the reviewer-facing value if time is short.
