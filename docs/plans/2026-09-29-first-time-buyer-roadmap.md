# First-time buyer roadmap — more useful, still ~$0/month

**Date:** 2026-09-29
**Goal:** Make Pinellas Market Lens genuinely useful to a first-time homebuyer without adding paid APIs or meaningful hosting cost.

## Status (2026-10-06)

Live in production: PR 0, PR 1 and PR 2 (merged together as pgil256/home_finder#5) and PR 4 (risk flags). Still to do: PR 3 and PR 5, then PR 6 before any traffic push, then PR 7–11.

What changed around the roadmap:

- **New database.** Production moved to a new Neon project on 2026-10-01. The old one exceeded its data-transfer quota in July, and Neon never lifted the restriction. pgil256/home_finder#4 caches the insights payload, runs the E2E smoke daily, moves sessions into signed cookies, and drops 14 unused indexes. The database is about 260 MB against a 512 MiB cap.
- **Unexplained wipe.** On 2026-10-02 every table in production disappeared with no operation logged by Neon and no job of ours running. A refresh rebuilt it. A daily "Database guard" workflow (pgil256/home_finder#8) now re-imports the county data if the property table is ever empty, then fails so the run gets noticed.
- **2026 millage.** The county published final 2026 millage in early October. The importer picked it up on its own, and estimates now use it.

Standing follow-ups:

1. After the November 3 vote, set `AMENDMENT_3_STATUS` in `apps/analytics/services/tax_estimate.py` to `'passed'` or `'failed'`. Once the Department of Revenue publishes the 2027 inflation-adjusted exemption, add it to `CURRENT_LAW`.
2. A full refresh reads every existing row, roughly 200 MB of the 5 GB monthly data-transfer allowance. Don't run it casually.
3. Filtered pages still set a session cookie on GET, so PR 6's work to make them CDN-cacheable remains.

### Findings from the live county files (downloaded 2026-09-30)

These corrected the plan below:

- `ELEVATION_CERT` is `N/A` on every one of 437,569 rows. It is not imported, and the risk card can't use it.
- `HX_SAVINGS` is blank for about 97% of parcels and isn't the Save Our Homes gap. It is not imported. The gap is `CNTY_JST_VALUE − CNTY_ASD_VALUE`, already stored as `market_value − assessed_value`.
- `CENSUS` is a 12-digit block group (the tract is its first 11 digits). It is deferred to the National Risk Index follow-up.
- `MILLAGE_RATE`, `LATITUDE`/`LONGITUDE` and `NBORHOOD_CD` carry float artifacts (`19.919700000000002`, `3000.2000000000003`). The importer rounds them to each field's precision. Without that, every monthly import would rewrite every row.
- The 2026 roll confirms current law: the homestead exemption is $25,000 on every levy plus **$26,411** (CPI-adjusted) on non-school levies above $50,000. For 169,041 homesteads, `CNTY_ASD_VALUE − CNTY_TAXABLE_VALUE` is exactly 51,411 and `CNTY_ASD_VALUE − SCHL_TAXABLE_VALUE` is exactly 25,000.
- `RP_MILLAGE_RATES` has 52 districts at "2025 Final". The per-district sums match `MILLAGE_RATE` on every parcel. School levies are `12A PINELLAS COUNTY SCHOOL BOARD` and `12B SCHOOL LOCAL` (6.293 mills county-wide).
- `TAX_AMOUNT_NO_EX` roughly tracks just value × millage but isn't an exact match for about half the parcels. It is nobody's bill.
- `MUNI_TAXABLE_VALUE` differs from `CNTY_TAXABLE_VALUE` for about 3% of parcels (city senior exemptions), so the current-owner estimate uses county taxable value for all non-school levies.
- The ballot measure is **Amendment 3** ("Save Our Homes From Excessive Property Taxes"). People who establish Florida residency after January 1, 2027 wait five years for the larger exemption. It also lowers the non-homestead cap from 10% to 5%, which doesn't help a buyer in year one, because the cap resets on sale.

---

## Positioning

Don't compete with Zillow/Redfin on listings. MLS/IDX feeds and property-data APIs (ATTOM, Estated, etc.) are the expensive part of real estate software, and listing sites already do that job well. The app already links out to them.

Instead, be the free **"what will this home really cost me, and what's the catch?"** companion. A first-time buyer finds a listing elsewhere, searches the address here, and gets answers that listing sites get wrong or leave out:

- What *my* property tax will be (not the seller's)
- What my monthly payment and cash-to-close will be
- Flood, evacuation, sinkhole, roof-age and condo risks, in plain English
- What comparable homes nearby actually sold for

**Cost rule:** every new data point comes from a file downloaded by the monthly GitHub Action (free), or from math that runs in the browser. There are no per-request API calls.

---

## Key finding: we already download most of this, then throw it away

`import_pcpao_data` downloads `RP_PROPERTY_INFO` monthly but maps only about 12 columns. That same file already contains:

| Column | Buyer meaning |
|---|---|
| `HX_CAP`, `HX_SAVINGS`, `NON_HX_CAP` | Whether the seller's taxes are artificially low because of Save Our Homes, and by how much |
| `MILLAGE_RATE`, `TAX_DISTRICT`, `SPECIAL_ASSESSMENT` | Inputs to estimate a new owner's tax bill |
| `CNTY_TAXABLE_VALUE`, `SCHL_TAXABLE_VALUE`, `MUNI_TAXABLE_VALUE` | Current taxable values by levy |
| `SALES_COMP` | Appraiser's comparable-sales indicated value |
| `EVAC_ZONE` | Hurricane evacuation zone A–E |
| `ELEVATION_CERT` | Elevation certificate on file (matters for flood insurance pricing) |
| `WATERFRONT_YN`, `SEAWALL`, `VIEWS`, `FRONTAGE` | Waterfront exposure, plus seawall upkeep liability |
| `SUBSIDENCE_YN` | Reported subsidence (sinkhole), a major insurance and resale flag |
| `CONTAMINATION_YN` | Contaminated-parcel flag |
| `DLHL_YN` | Local historic landmark (renovation restrictions) |
| `LATITUDE`, `LONGITUDE` | Map pins and flood-zone lookup, with no geocoding API needed |
| `NBORHOOD_CD`, `CENSUS` | Neighborhood grouping for comps |
| `TOTAL_LIVING_UNITS` | Distinguishes a true single-family home from a duplex |

PCPAO also publishes these free, separate tables. They are listed on the raw-database-files page and refreshed daily:

- `RP_SALES`: sale date, price, qualified/unqualified flag
- `RP_PERMITS`: permit type, description, issue date, estimated value
- `RP_MILLAGE_RATES`: per-taxing-authority rates, used to split school vs non-school levies
- `RP_EXEMPTIONS`: homestead status per year
- `RP_EXTRA_FEATURES`: pools, docks, etc.

---

## Tier 1 — highest value, no new data sources

### 1. New-owner property tax estimate ("tax shock") — the flagship feature

**Why:** In Florida, a homesteaded owner's assessed value is capped by Save Our Homes (3% or CPI, whichever is lower). When the home sells, the assessment resets to just value on the next January 1. The tax bill shown on listing sites belongs to the seller and can be far below what the buyer will pay. This is the most common first-time-buyer budgeting mistake in Florida, and the app has the data to fix it.

**Estimate:**

```
new_owner_taxable_nonschool = max(0, just_value - homestead_exemption_nonschool)
new_owner_taxable_school    = max(0, just_value - homestead_exemption_school)
est_tax = new_owner_taxable_school * school_millage / 1000
        + new_owner_taxable_nonschool * nonschool_millage / 1000
        + special_assessment
```

- Current law: the first $25k exemption applies to all levies. The additional $25k applies to assessed value between $50k and $75k and excludes school levies.
- Use `RP_MILLAGE_RATES` to split school and non-school millage. It is a tiny table.
- Show both "if you file for homestead" and "without homestead" (investor or second home). Show the delta against the current bill: *"Seller pays $2,140/yr. You'd pay about $6,900/yr."*
- Remind buyers to file homestead by **March 1** after purchase.

**Timing:** A property-tax amendment (CS/HJR 1F) is on the **November 3, 2026** ballot and needs 60% to pass. If it passes, the first $150k of assessed value becomes exempt from Jan 1, 2027, rising to $250k in 2028. Put exemption parameters in a small dated config structure, e.g. `{effective_year: {...}}`, so the post-election update is a one-line change. Confirm levy-by-levy details against PCPAO's legislative-update page before shipping.

**Also fix:** the detail page labels `tax_amount` as "Annual Tax", but it is imported from `TAX_AMOUNT_NO_EX` (tax before exemptions). Relabel it or replace it with the new estimate.

Precompute `est_new_owner_tax_hx` and `est_new_owner_tax_nohx` in the monthly import, not per request.

### 2. Monthly cost and cash-to-close calculator (client-side JS)

On the parcel page, prefilled and editable:

- Price (defaults to just value, clearly labeled "just value ≠ asking price, enter the list price")
- Down payment %, loan type (conventional / FHA), rate, term
- Taxes: prefilled from #1
- Homeowners insurance and HOA: user inputs with guidance text
- PMI (conventional, under 20% down) or FHA MIP

Outputs: monthly PITI + HOA, plus estimated cash to close.

Florida closing costs are largely formula-driven, not API-driven: doc stamps on the note (0.35%), intangible tax on the mortgage (0.2%), and state-promulgated title insurance rates. Who pays what varies by county custom, so verify Pinellas customs and current promulgated rates before hard-coding.

**Default rate:** fetch FRED `MORTGAGE30US` weekly in a GitHub Action (free API key) and write it to a tiny static JSON or a one-row table. There is zero runtime cost.

All math runs in the browser: no server cost, and trivially testable with Jest.

### 3. Risk flags card

A plain-English card on the parcel page, built entirely from columns in #0:

- Evacuation zone (A evacuates first)
- Waterfront / seawall (seawall repair is the owner's cost)
- Ask the seller for an elevation certificate; it can lower flood premiums. PCPAO's `ELEVATION_CERT` column is always `N/A`, so this is advice, not a data flag.
- Subsidence reported, contamination flagged, historic landmark
- Built before the 2002 Florida Building Code: ask for wind-mitigation and 4-point inspections
- Condo in an older building: Florida's post-Surfside milestone-inspection and structural-reserve rules can mean special assessments or HOA increases. Confirm current age thresholds before hard-coding.

Each flag gets a *"what to ask / what to inspect"* line. This is where a first-time buyer gets the most value per byte.

### 4. Budget-first search

Add "I can afford $X/month" as a search entry point. The same client-side calculator converts it to a max price and pre-fills `max_price`. Add filters for evacuation zone, "exclude subsidence", and (after #8) "outside flood zone".

### 5. Saved homes and compare page

The Save button already writes parcel IDs to `localStorage['savedProperties']`, but nothing reads that list. Add `/saved/` (IDs via query string from JS) with a side-by-side view: price, est. new-owner tax, monthly cost, and risk flags. No accounts means no auth infrastructure and no personal data stored server-side.

---

## Tier 2 — new free files, filtered in the Action before loading

### 6. Sales history and honest comps (`RP_SALES`)

- Add `last_sale_date`, `last_sale_price`, `last_sale_qualified` to `PropertyListing`.
- Load only **qualified, improved** sales from the last ~36 months into a slim `Sale` table.
- Parcel page: "Last sold for $X in 2021", plus neighborhood comps: median $/sqft of qualified sales in the same `NBORHOOD_CD` over 12 months.
- Flag recent flips (multiple sales within 24 months).

This retires the README limitation that the dataset "lacks MLS sale prices". Recorded qualified sales are real transaction prices. It is still not an AVM, and the honest-methodology stance stays.

### 7. Roof and system age (`RP_PERMITS`)

Derive `roof_permit_year` (and optionally HVAC or water heater) by keyword-matching permit descriptions. Validate the keywords against real rows first. Roof age strongly affects insurability and premiums in Florida; it is often the first thing an insurer asks about.

### 8. FEMA flood zone

Do a batch point-in-polygon join in the GitHub Action: parcel `LATITUDE`/`LONGITUDE` against FEMA NFHL flood-hazard polygons for Pinellas. The public ArcGIS service needs no key, or use the county FIRM download. Store `flood_zone`. In a Special Flood Hazard Area (A, AE, VE), lenders require flood insurance, which is a large monthly cost for many Pinellas homes. Link out to FEMA's map for the address.

### 9. Map

Use MapLibre GL with OpenFreeMap tiles (free, no API key) on the parcel page, from the stored coordinates. Avoid Google Maps and Mapbox paid tiers, and avoid heavy use of `tile.openstreetmap.org`, whose usage policy discourages it.

---

## Tier 3 — static guidance content (zero cost)

### 10. First-time buyer guide

Replace or extend `/help/` with:

- The process: pre-approval → offer → inspection period → appraisal → insurance binder → closing → homestead filing by March 1
- Florida specifics: 4-point and wind-mitigation inspections, flood insurance, condo reserve rules
- Down payment assistance: link to Florida Housing, Pinellas County programs, and Hometown Heroes. Link out rather than hard-coding amounts, which change often.

Link glossary terms (just value, assessed value, millage, SFHA) inline from the parcel page.

---

## Hosting and API cost guardrails

1. **Make pages CDN-cacheable.** Data changes monthly, so most GETs could be served from Vercel's edge without invoking Django or waking Neon, which keeps usage inside Neon's free 100 CU-hours/month. Two current blockers:
   - `insights_dashboard` and `_initial_search_values` write `request.session[SEARCH_SESSION_KEY]` on GET, which sets a cookie and makes responses uncacheable. Move "last search" memory to the URL or `localStorage`.
   - `property-detail.html` renders `{% csrf_token %}` for the Refresh form, which sets a CSRF cookie and `Vary: Cookie`. Load the token via a small JS fetch only when Refresh is clicked.

   Then add `Cache-Control: public, s-maxage=86400, stale-while-revalidate=604800` to insights and parcel pages.
2. **Precompute derived fields during the monthly import**: new-owner tax, last sale, flood zone, roof year. Request handlers should only read columns.
3. **Storage budget.** The Neon free tier is 0.5 GB and the dataset is 220 MB (measured 2026-10-01, after dropping unused indexes). Estimated additions: about 15 narrow columns (~20–40 MB) plus 36 months of qualified sales (<10 MB). Filter in the Action; never load full history tables. `RP_SALES_HISTORY` also carries buyer and seller mailing addresses, which aren't needed. Adding nullable columns in Postgres is metadata-only, and the importer's skip-unchanged-rows logic keeps monthly churn low because most new fields change yearly.
4. **Trim the serverless bundle.** `matplotlib` and `PyPDF2` appear unused. `selenium`, `webdriver-manager` and `bs4` are only used in the scraper path. A smaller bundle means faster cold starts. Verify before removing.
5. **Keep calculators client-side.** They add no server cost and work offline once loaded.
6. **Watch the Vercel plan.** Hobby is for non-commercial use. Adding lender or insurance referral links or ads would mean budgeting for Pro, or moving hosting.

---

## Explicitly not doing

- **Paid listing or property APIs** (MLS/IDX, Zillow, ATTOM, Estated): the expensive part, and already covered by linking out.
- **LLM "ask about this home" chat**: per-request token cost. If ever wanted, generate static explanations during the monthly import.
- **User accounts**: `localStorage` covers saved homes for now.
- **Price prediction / AVM**: comps from qualified sales are honest and sufficient.

---

## Data sources

### Today

The only runtime data source is the **Pinellas County Property Appraiser (PCPAO)**:

- `RP_PROPERTY_INFO` bulk CSV, imported monthly by `.github/workflows/refresh-data.yml`
- On-demand single-parcel scrape (`refresh_one_parcel`) behind the Refresh button
- County-hosted parcel photos

Zillow, Redfin, Realtor.com and OpenStreetMap are outbound links only, not APIs. `tasks/tax_collector_scraper.py` is only referenced by tests; nothing in the product calls it.

### After this plan

**Architecture rule:** every external call happens in a GitHub Actions job, never in a Vercel request. Request handlers only read Neon. The one exception is map tiles, which the visitor's browser loads directly from a free tile host. The repo is public, so Actions minutes are free.

| Source | Used for | Auth | Access | Cadence |
|---|---|---|---|---|
| PCPAO `RP_PROPERTY_INFO` (more columns) | Tax inputs, risk flags, coordinates, neighborhood | None | Same POST download the importer already uses | Monthly |
| PCPAO `RP_MILLAGE_RATES` | School vs non-school millage per tax district | None | Same | Monthly (changes yearly) |
| PCPAO `RP_SALES` | Last sale, qualified-sale comps, flip flag | None | Same | Monthly |
| PCPAO `RP_PERMITS` | Roof / HVAC permit year | None | Same | Monthly |
| FEMA NFHL ArcGIS REST (`/public/NFHL/MapServer/28`) | Flood zone + base flood elevation per parcel | None | Batch point-in-polygon in the Action | Quarterly |
| OpenFEMA `v3/NfipClaims` | Flood-insurance claim history by ZIP | None | REST, filter `countyCode eq '12103'` (~52k Pinellas claims) | Quarterly |
| FRED `MORTGAGE30US` (Freddie Mac PMMS) | Default mortgage rate in the calculator | Free API key | REST | Weekly |
| OpenFreeMap | Map tiles for MapLibre GL | None | Browser loads `tiles.openfreemap.org/styles/liberty` | Per page view (their cost, not ours) |
| *Optional:* HUD Fair Market Rents / Small Area FMRs | "Typical rent here" for rent-vs-buy | Free bearer token | REST | Yearly |
| *Optional:* FHFA House Price Index, ZIP5 annual | 5-year price trend by ZIP | None | ~40 MB xlsx download | Yearly |
| *Optional:* FEMA National Risk Index, census tract | Hurricane / flood / wind risk ratings (joins on PCPAO `CENSUS`) | None | Bulk download | Yearly |
| Static config (checked into repo) | Homestead exemption rules, FL closing-cost rates, FHA/conforming loan limits, FHA MIP | — | Updated by hand | Yearly, or after law changes |
| Links only | Florida Housing / Hometown Heroes, Pinellas County down-payment assistance, HUD housing counselors, FloodSmart | — | Outbound links | — |

Verified 2026-09-29:
- **OpenFEMA's v2 `FimaNfipClaims` endpoint is deprecated and removed on 2026-10-15.** Its data is frozen as of 2026-06-01. Use `v3/NfipClaims`.
- **The Census API now requires a free key.** Unkeyed requests redirect to a "Missing Key" page.
- HUD's API returns 401 without a token.
- FEMA NFHL, OpenFEMA v3, the FHFA file and OpenFreeMap all responded without auth.

**Secrets:** `FRED_API_KEY` (and `HUD_API_TOKEN` if used) live only in GitHub Actions secrets. Vercel never needs them.

---

## Implementation plan

One PR per step. Each step ships something visible and keeps CI green.

### PR 0 — Groundwork (S) — done

*As built:* `scripts/make_sample_fixture.py` samples 48 real rows from a PCPAO download (owner, mailing and deed columns blanked) and writes the matching `sample_millage_rates.csv`. `requirements-data.txt` is deferred to PR 9, the first step that needs it.

- **Fix the stale fixture.** `apps/analytics/fixtures/sample_pcpao_data.csv` uses the old column names (`PARCEL_ID`, `SITE_ADDR`, …), but `map_csv_row_to_property` reads the current schema (`PARCEL_NUMBER`, `SITE_ADDRESS`, …). The README Quick Start therefore imports **zero rows**. Regenerate the fixture with ~50 real-schema rows, including the new columns and a mix of evac zones, waterfront, homestead-capped and non-capped parcels.
- Remove `matplotlib` and `PyPDF2` from `requirements.txt`. Nothing imports either.
- Add `requirements-data.txt` for Action-only dependencies (e.g. `shapely` in PR 9) so they never enter the Vercel bundle.

### PR 1 — Import the dropped `RP_PROPERTY_INFO` columns (M) — done

*As built:* migration `0008` (`0007` is the index cleanup from pgil256/home_finder#4). Dropped `elevation_cert`, `homestead_savings` and `census_tract` (see findings). Added `frontage`. The `neighborhood_code` index is deferred to PR 7, where comps query it. `--vacuum-every N` is in place, and the refresh workflow passes `--vacuum-every 10`. Changed rows are written with one `INSERT ... ON CONFLICT DO UPDATE` per batch; `bulk_update` took about 29 minutes for a full-table rewrite.

- Migration `0007`: add nullable fields to `PropertyListing`:
  - `latitude`, `longitude`
  - `evac_zone`, `tax_district`, `neighborhood_code` (indexed), `census_tract`, `views`
  - Booleans: `elevation_cert`, `waterfront`, `seawall`, `subsidence`, `contamination`, `historic_landmark`, `homestead_cap`
  - Decimals: `homestead_savings`, `millage_rate`, `special_assessment`, `sales_comp_value`
  - `living_units`, `roll_year`

  Nullable adds are metadata-only in Postgres.
- `pcpao_importer.py`: add a `_yn()` helper, extend `map_csv_row_to_property`, and extend `update_fields` in `bulk_upsert_properties`.
- **Storage risk:** the first run after this migration changes *every* row. That creates roughly one table's worth of dead tuples on a 0.5 GB Neon project. Before merging, check current size (`SELECT pg_total_relation_size('analytics_propertylisting')`, adjusting for the table's actual `db_table`), and add a `--vacuum-every N` option that runs `vacuum_property_listing_table()` every N batches during the backfill.
- Tests: mapping tests for the new columns in `test_services.py`.

### PR 2 — New-owner tax estimate (M) — ship before Nov 3 — done

*As built:* migration `0009` adds `TaxDistrictMillage` and `est_tax_current` / `est_tax_homestead` / `est_tax_no_homestead` (whole dollars; `est_tax_homestead` is null for parcels that can't be homesteaded). Rules live in `CURRENT_LAW` and `AMENDMENT_3`, switched by `AMENDMENT_3_STATUS`. The parcel page recomputes new-owner figures from the current just value, so they survive a per-parcel refresh. It shows the Amendment 3 scenario while the vote is pending, and after a pass it shows the new-resident scenario instead. Filter labels and the insights note now say "tax before exemptions".

- Import `RP_MILLAGE_RATES` into a small `TaxDistrictMillage(district_code, year, total_mills, school_mills)` table. Classify school levies by `TAX_AUTH_NAME`; check the real values first.
- `services/tax_estimate.py`:
  - Pure function `estimate_new_owner_tax(just_value, millage, special_assessment, homestead, rules)`.
  - `HOMESTEAD_RULES` keyed by effective year: current law now, plus the CS/HJR 1F schedule to switch on if it passes.
- Precompute `est_tax_homestead` and `est_tax_no_homestead` during import so they can be filtered and sorted.
- `property-detail.html`: "Your estimated taxes" card showing seller's bill vs. yours, with the March 1 homestead filing reminder. Relabel the current "Annual Tax" (it is `TAX_AMOUNT_NO_EX`).
- Tests: table-driven cases with hand-computed expected values, including just value under $50k, between $50k and $75k, and above $75k.

### PR 3 — Monthly cost calculator + budget search (M)

- `static/js/dev/affordability.js`, pure functions:
  - `monthlyPI`, `pmi`, `fhaMip`
  - `closingCosts` (FL note doc stamps, intangible tax, promulgated title rate)
  - `maxPriceForBudget` (bisection over the forward calculation)
- Add a webpack entry and Jest tests.
- Detail page: calculator panel, seeded via `{{ data|json_script }}` with just value, estimated tax and current rate. Label clearly that just value is not the asking price.
- `.github/workflows/refresh-rates.yml` (weekly): fetch FRED `MORTGAGE30US` into a one-row `MortgageRate` table.
- `services/lending_config.py`: yearly constants (FHA MIP, FHA and conforming loan limits for Pinellas).
- `search.html`: a "monthly budget" field. JS converts it to `max_price` before submit, so there is no server change.

### PR 4 — Risk flags card + filters (S) — done

*As built:* `services/risk_flags.py` builds the card from evacuation zone, waterfront and frontage, seawall, subsidence, contamination, historic landmark, build year and property type. It also flags mobile and manufactured homes, which the county orders out for any hurricane. Condos are flagged from 25 years old, and the wording says the inspection rule applies to buildings of three or more stories, because the county file has no story count. The filters are `exclude_evac` (drop zones A through the chosen one), `exclude_subsidence` and `max_est_tax`, and all three are part of the insights cache key.

- `services/risk_flags.py`: `build_risk_flags(listing) -> list[RiskFlag(level, title, why, what_to_ask)]`, pure and unit-tested. Covers evac zone, waterfront/seawall, elevation cert, subsidence, contamination, historic landmark, pre-2002 build, older condo.
- `apply_filters`: add `evac_zone`, `exclude_subsidence`, and `max_est_tax`. Add matching `SEARCH_FIELDS` entries, chips and form fields.

### PR 5 — Saved homes + compare (S)

- `GET /analytics/compare/?ids=…`: cap at 6 IDs, reuse the tax, risk and calculator services, and render a side-by-side table.
- Nav link "Saved (n)" reads `localStorage['savedProperties']` and builds the compare URL.

### PR 6 — CDN caching (M)

- Stop writing `request.session[SEARCH_SESSION_KEY]` on GET in `insights_dashboard` and `_initial_search_values`. Keep "last search" in `localStorage` or the URL.
- Replace `{% csrf_token %}` on the detail page with a token fetched from an uncached `/analytics/csrf/` endpoint when Refresh is clicked. After a refresh, redirect to `?refreshed=<timestamp>` so the visitor doesn't get the cached pre-refresh page.
- Add `@cache_control(public=True, s_maxage=86400, stale_while_revalidate=604800)` to insights, parcel, compare and static pages.
- Test: responses carry `s-maxage`, have no `Set-Cookie`, and have no `Vary: Cookie`. Include a template that renders `messages`, since that can touch the session.
- Optional: call a Vercel deploy hook at the end of `refresh-data.yml` to purge the CDN right after each import.

### PR 7 — Sales history + comps (M)

- Stream `RP_SALES` in the Action. Keep only qualified (`QUALIFIED_FLG = 'Q'`), improved (`VACANT_IMPROVED = 'I'`) sales from the last 36 months. Drop grantee and grantor names.
- Store `last_sale_date` and `last_sale_price` on `PropertyListing`: track the max date per parcel while streaming the whole file.
- Slim `Sale(parcel_id, sale_date, price)` table, reloaded monthly with `TRUNCATE` + bulk insert. `TRUNCATE` leaves no dead tuples.
- `services/comps.py`: same `neighborhood_code` and type bucket, sold in the last 12 months, sqft within ±25%. Report median $/sqft × subject sqft with n and range, and hide it when n < 3. Add a flip flag (2+ qualified sales in 24 months).
- Update `_methodology()` and the README "Limitations" section.

### PR 8 — Roof and system age (S)

- First, profile `RP_PERMITS` (`PERMIT_TYPE` / `PERMIT_DSCR` value counts) to choose keywords.
- Derive `roof_permit_year` (and optionally `hvac_permit_year`) during import. Store only those columns.
- Risk flag: no roof permit in 15+ years (or none on record) → "ask for roof age; insurers will."

### PR 9 — Flood zone + flood-claim history (M)

- New Action step, quarterly or `workflow_dispatch`:
  - Page through NFHL layer 28 for the Pinellas bounding box (`resultOffset`, GeoJSON).
  - Build a `shapely` STRtree and join all parcel coordinates.
  - Write `flood_zone` and `static_bfe`.
  - Cache the GeoJSON between runs with `actions/cache`.
- OpenFEMA `v3/NfipClaims` for county `12103`: aggregate by ZIP (claim count, claims since 2020, median paid) into a small `ZipFloodHistory` table.
- Risk flag for Special Flood Hazard Areas (A/AE/V/VE): lenders require flood insurance. Add an "outside SFHA" filter.

### PR 10 — Map (S)

- MapLibre GL + the OpenFreeMap `liberty` style, lazy-loaded on the detail page only, with a pin from the stored coordinates.
- Optional: FEMA NFHL flood-zone overlay as a raster source pointed at FEMA's own MapServer export endpoint. That is live flood mapping with no hosting cost.
- Credit OpenStreetMap contributors and OpenFreeMap.

### PR 11 — Guide + repositioning (S)

- Rewrite `/help/` as a first-time buyer guide: steps, Florida specifics, and assistance-program links.
- Add a glossary partial linked inline from the parcel page.
- Home page: lead with "Look up any Pinellas home" address search instead of the analytics pitch. Keep the dashboard as a secondary "Explore the market" path.

### Optional follow-ups

- HUD Small Area FMR "typical rent" line in the calculator (rent vs. buy).
- FHFA ZIP5 5-year price trend on the parcel page.
- FEMA National Risk Index tract ratings in the risk card.

### Sequencing

PR 0 → PR 1 → PR 2 are the critical path; PR 2 should be live before the Nov 3 vote. PRs 3–5 depend only on PR 1. PR 6 can land any time but should come before any traffic push. PRs 7–10 are independent of each other.
