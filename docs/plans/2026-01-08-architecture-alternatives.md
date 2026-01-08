# Home Finder Architecture Alternatives

> **Status:** Implemented - see `apps/WebScraper/services/pcpao_importer.py` and `manage.py import_pcpao_data`

## Problem Statement

The current Selenium-based scraping setup feels overkill for the application's needs. It requires:
- Chrome browser binaries and WebDriver
- Significant memory overhead per scrape
- Fragile HTML selectors that break when sites change
- Sequential 1-second delays per property (10 properties = 20-30 seconds minimum)

## Discovery: PCPAO Bulk Data Downloads

Pinellas County Property Appraiser offers **free bulk data downloads** in CSV, JSON, Excel, and XML formats at:
https://www.pcpao.gov/tools-data/data-downloads/raw-database-files

### Available Data Files

| File | Description | Key Fields |
|------|-------------|------------|
| **RP_PROPERTY_INFO** | Comprehensive parcel data | Addresses, owners, assessed values, building details, evacuation zones, tax info |
| **RP_BUILDING** | Construction details | Foundation type, exterior walls, year built, square footage, quality ratings |
| **RP_ALL_SITE_ADDRESSES** | Location data | Street addresses, building numbers |
| **RP_ALL_OWNERS** | Ownership records | Owner names from deeds |
| **RP_SALES** | Transaction details | Sale dates, prices, qualified/unqualified, buyer/seller |
| **RP_SALES_HISTORY** | Complete deed history | Grantor/grantee, document stamps |
| **RP_LAND** | Land information | Use codes, acreage, dimensions, unit values |
| **RP_MILLAGE_RATES** | Tax rates | District codes, taxing authorities, rates |
| **RP_EXEMPTIONS** | Tax exemptions | Homestead status, property classifications |
| **RP_EXTRA_FEATURES** | Improvements | Pools, docks, values, installation dates |
| **RP_PERMITS** | Construction permits | Issue dates, descriptions, estimated values |
| **RP_STRUCTURAL_ELEMENTS** | Building attributes | Foundation, roof, cooling systems, finishes |
| **RP_SUB_AREAS** | Building subdivisions | Square footage measurements, adjustment factors |
| **RP_LEGAL** | Legal descriptions | Complete legal property descriptions |
| **RP_INACTIVE_PARCEL_LIST** | Historical parcels | Deleted, split, or combined parcels |

### Additional Resources

- **GIS Shape Files**: https://www.pcpao.gov/tools-data/maps-gis/shape-files
- **Enterprise GIS Portal**: https://new-pinellas-egis.opendata.arcgis.com/
- **ArcGIS Feature Services**: Available for programmatic access

## Architecture Comparison

### Current Architecture

```
User Search Form
       │
       ▼
Django View (web_scraper_view)
       │
       ▼
Celery Task Chain
       │
       ├──► scrape_pinellas_properties
       │         │
       │         ▼
       │    PCPAOScraper (Selenium + Chrome)
       │         │
       │         ▼
       │    Navigate to pcpao.gov
       │    Fill search form
       │    Click through paginated results
       │    Visit each parcel detail page
       │    Parse HTML for data
       │         │
       ├──► scrape_tax_data
       │         │
       │         ▼
       │    TaxCollectorScraper (Selenium + Chrome)
       │         │
       │         ▼
       │    Navigate to taxcollect.com
       │    Search each parcel ID
       │    Parse HTML for tax info
       │         │
       ├──► generate_sorted_properties (Excel)
       ├──► generate_listing_pdf (PDF)
       ├──► analyze_data (Charts)
       └──► send_results_via_email

Total time for 10 properties: ~30-60 seconds
Dependencies: Chrome binary, ChromeDriver, Selenium, Redis, Celery
```

### Proposed Architecture (Bulk Data)

```
Scheduled Job (daily/weekly)
       │
       ▼
Download CSV files from PCPAO
       │
       ▼
Pandas DataFrame processing
       │
       ▼
Bulk insert/update SQLite/PostgreSQL
       │
       ▼
User Search Form
       │
       ▼
Django ORM query (instant)
       │
       ▼
Generate reports (Excel/PDF)

Total time for search: <1 second (database query)
Dependencies: Pandas, requests (for download)
Removed: Chrome, ChromeDriver, Selenium, Celery (optional)
```

## Trade-offs

### Bulk Data Approach

**Pros:**
- Dramatically simpler architecture
- No browser automation fragility
- Instant search results (database queries)
- Complete county data (~400k parcels) actually feasible
- Lower resource usage (no Chrome instances)
- More reliable (no HTML parsing failures)

**Cons:**
- Data freshness depends on download frequency
- Initial setup to map CSV fields to model
- Need to handle incremental updates
- Tax Collector data may still need separate approach

### Hybrid Approach

If real-time tax data is needed:
- Use bulk PCPAO data for property information
- Use lightweight HTTP requests (not Selenium) for tax lookups
- Cache tax data with TTL

## Tax Collector Considerations

The Tax Collector site (pinellastaxcollector.gov) does not appear to offer bulk downloads. Options:

1. **Skip tax data initially** - Focus on property data, add tax later
2. **Lightweight scraping** - Use `requests` + BeautifulSoup instead of Selenium (if site doesn't require JS)
3. **On-demand lookups** - Fetch tax data only when user views a specific property
4. **Contact Tax Collector** - Request bulk data access or API

## Data Freshness Requirements

**Decision: Daily updates**

Daily freshness is sufficient for this application's use case (home buyers, real estate agents, investors researching properties).

### Implementation

```
┌─────────────────────────────────────────────────────┐
│  Daily Import Job (cron or systemd timer)           │
│  Runs: 2:00 AM EST (off-peak)                       │
├─────────────────────────────────────────────────────┤
│  1. Download latest CSV files from PCPAO            │
│  2. Load into Pandas DataFrames                     │
│  3. Compare with existing DB records (by parcel_id) │
│  4. Bulk upsert changed/new records                 │
│  5. Log import stats (added, updated, unchanged)    │
│  6. Optional: Alert on anomalies (>5% change)       │
└─────────────────────────────────────────────────────┘
```

### Cron Example

```bash
# /etc/cron.d/home-finder-import
0 2 * * * home_finder /path/to/venv/bin/python manage.py import_pcpao_data --quiet
```

### Why Daily Works

- PCPAO updates their data regularly but not in real-time
- Property values, ownership, and building info change infrequently
- 24-hour lag is acceptable for research/buying decisions
- Avoids unnecessary load on county servers

## Next Steps

1. **Decide on data freshness requirements**
2. **Download sample PCPAO files** to verify field coverage
3. **Map CSV fields to PropertyListing model**
4. **Build import script** using Pandas
5. **Evaluate Tax Collector options** (test if HTTP requests work)
6. **Simplify or remove Celery** if no longer needed for scraping

## References

- [PCPAO Raw Database Files](https://www.pcpao.gov/tools-data/data-downloads/raw-database-files)
- [PCPAO Shape Files](https://www.pcpao.gov/tools-data/maps-gis/shape-files)
- [Pinellas County Enterprise GIS](https://new-pinellas-egis.opendata.arcgis.com/)
- [Pinellas County Tax Collector](https://pinellastaxcollector.gov/property-tax/)
