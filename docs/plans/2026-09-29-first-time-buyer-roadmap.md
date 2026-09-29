# First-time buyer roadmap — more useful, still ~$0/month

**Date:** 2026-09-29
**Goal:** Make Pinellas Market Lens genuinely useful to a first-time homebuyer without adding paid APIs or meaningful hosting cost.

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
- Elevation certificate on file (ask the seller for it; it can lower flood premiums)
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
3. **Storage budget.** The Neon free tier is 0.5 GB and the current dataset is about 150 MB. Estimated additions: about 15 narrow columns (~20–40 MB) plus 36 months of qualified sales (<10 MB). Filter in the Action; never load full history tables. `RP_SALES_HISTORY` also carries buyer and seller mailing addresses, which aren't needed. Adding nullable columns in Postgres is metadata-only, and the importer's skip-unchanged-rows logic keeps monthly churn low because most new fields change yearly.
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

## Suggested order

1. Import the extra `RP_PROPERTY_INFO` columns (one migration + importer mapping). This unblocks #1, #3, #4, #8 and #9.
2. New-owner tax estimate + fix the "Annual Tax" label. Ship before Nov 3 with the exemption config ready to flip.
3. Monthly cost calculator + budget-first search.
4. Risk flags card.
5. Saved/compare page.
6. CDN caching refactor.
7. Sales comps, roof permits, flood zone.
8. Guide content.
