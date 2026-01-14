# Scraper Performance Optimizations

## Overview

Four optimizations to reduce scrape time from ~7.7s/property to ~1-2s/property:

1. **Parallel browser instances** - 3 concurrent Chrome instances for property detail scraping
2. **Remove tax scraper** - Use PCPAO bulk data only, skip real-time tax lookups
3. **Reduce empty page threshold** - Stop after 1 empty page instead of 3
4. **24-hour caching** - Skip re-scraping properties updated within 24 hours

## Expected Performance

| Scenario | Before | After | Improvement |
|----------|--------|-------|-------------|
| 10 properties | 77s | ~15-20s | 4x faster |
| 100 properties | ~13 min | ~2-3 min | 5x faster |
| 1000 properties | ~2 hours | ~25 min | 5x faster |

## Architecture

```
Current Flow (sequential):
PCPAO Search → [Property 1] → [Property 2] → ... → [Property N] → Tax Scraper → Done
                   3.7s          3.7s                  3.7s          2.4s/each

Optimized Flow (parallel + cached):
PCPAO Search → ┌─[Browser 1: Properties 1,4,7...]─┐
               ├─[Browser 2: Properties 2,5,8...]─┤ → Done
               └─[Browser 3: Properties 3,6,9...]─┘
                        ~1.2s/property (3 concurrent)
               + Skip cached properties (< 24h old)
               + Skip tax scraper entirely
```

## Implementation Details

### 1. Parallel Browser Implementation

New method `scrape_properties_parallel()` in `pcpao_scraper.py`:
- Creates pool of 3 browser instances (configurable via `max_workers`)
- Uses `concurrent.futures.ThreadPoolExecutor` to distribute properties
- Each browser scrapes assigned properties sequentially
- Results collected and returned in original order

Thread safety:
- Each thread gets its own `PCPAOScraper` instance with isolated Chrome driver
- No shared state between workers
- Progress reporting aggregated from all workers

Resource limits:
- Default 3 workers
- Each Chrome headless instance uses ~150-200MB
- Total: ~600MB peak memory usage

### 2. 24-Hour Cache Implementation

Before scraping, query database for recently-scraped properties:
- Properties scraped within 24 hours are skipped
- Their existing data is used in reports
- Progress UI shows "X cached, Y scraped"
- Uses existing `last_scraped` field (auto_now=True)

### 3. Remove Tax Scraper

The `scrape_tax_data` task becomes a passthrough:
- Tax data comes from PCPAO bulk import only
- Task preserved for pipeline compatibility
- `tax_collector_scraper.py` no longer called

Rationale: The tax collector site (`pinellastaxcollector.gov`) doesn't have property-specific tax data. The actual tax database (`pinellas.county-taxes.com`) has Cloudflare protection.

### 4. Empty Page Threshold

Change from 3 consecutive empty pages to 1:
- PCPAO paginates consistently
- Empty page means end of results
- Saves ~4 seconds per search

## Files Modified

| File | Changes |
|------|---------|
| `pcpao_scraper.py` | Add `scrape_properties_parallel()`, update `scrape_by_criteria()` |
| `scrape_data.py` | Add 24-hour cache check, simplify `scrape_tax_data` |
| `pcpao_scraper.py` | Change empty page threshold 3 → 1 |

## Rollback

All changes are backward compatible. Can revert to sequential by setting `max_workers=1`.
