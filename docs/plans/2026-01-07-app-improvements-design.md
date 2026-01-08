# Home Finder Application Improvements

## Overview

Comprehensive improvement plan covering five key areas: reliability, user experience, performance, data quality, and new features.

---

## 1. Reliability & Error Handling

### Current Problems
- Scrapers fail silently when elements aren't found or pages timeout
- No retry logic for transient failures (network issues, rate limiting)
- Celery tasks don't gracefully handle partial failures
- Users see generic errors with no actionable information

### 1A. Scraper Resilience Layer

**Exception Hierarchy** (`apps/WebScraper/tasks/exceptions.py`):
```python
class ScraperException(Exception):
    """Base exception for all scraper errors"""
    pass

class ElementNotFound(ScraperException):
    """Expected element not found on page"""
    pass

class PageTimeout(ScraperException):
    """Page load or element wait timeout"""
    pass

class RateLimited(ScraperException):
    """Server returned rate limit response"""
    pass

class SessionExpired(ScraperException):
    """WebDriver session became invalid"""
    pass

class CaptchaDetected(ScraperException):
    """CAPTCHA challenge detected"""
    pass
```

**Retry Decorator** (`apps/WebScraper/tasks/retry.py`):
- Configurable max attempts (default: 3)
- Exponential backoff: 2s → 4s → 8s
- Jitter to prevent thundering herd
- Only retry on transient exceptions (`PageTimeout`, `RateLimited`, `SessionExpired`)
- Log each retry attempt with context

**WebDriver Manager** (enhance existing scrapers):
- `ensure_session()` - check if browser is responsive, restart if stale
- `safe_find_element()` - wraps find with timeout and raises `ElementNotFound`
- `safe_click()` - scroll into view, wait for clickable, handle overlays
- `wait_for_page_load()` - detect full page load vs partial, with timeout

**Structured Logging**:
- Each scrape operation logs: parcel_id, operation, duration, success/failure
- Failed operations include: exception type, page URL, screenshot path (optional)

### 1B. Task-Level Error Handling

- Track per-parcel success/failure in `scrape_data.py`
- Continue processing remaining parcels when one fails
- Return structured result: `{success: [...], failed: [...], errors: [...]}`
- Store failed parcel IDs for retry queue

### 1C. User-Facing Error Communication

- Add `ScrapeJob` model to track job status, progress, and errors
- Real-time error streaming to progress UI via polling
- Summary at completion: "Scraped 450/500 properties. 50 failed - click to retry"

---

## 2. User Experience

### Current Problems
- Basic form submission with redirect to progress page
- Progress bar shows percentage but no details on what's happening
- No way to browse previously scraped data without re-running scraper
- Keyword ordering UI exists but search results aren't displayed in-app

### 2A. Enhanced Progress Tracking

- Show current operation: "Scraping property 45/500: 123 Main St..."
- Display live stats: properties found, tax records matched, errors encountered
- Estimated time remaining based on average per-property duration
- Allow cancellation of in-progress jobs

### 2B. Property Dashboard

- Searchable/filterable table of all `PropertyListing` records in database
- Column sorting, pagination, bulk selection
- Quick filters: city dropdown, price range slider, property type chips
- Property detail modal with all fields + links to source URLs

### 2C. Job History

- List of past scrape jobs with timestamp, criteria used, results count
- Re-run previous searches with one click
- Download previous exports (Excel/PDF) without re-scraping

### 2D. Responsive Polish

- Mobile-friendly tables (card view on small screens)
- Loading skeletons instead of spinners
- Toast notifications for job completion/errors

---

## 3. Performance & Scale

### Current Problems
- Sequential scraping - one property at a time
- Full re-scrape required even if data exists
- No caching of scraped data
- Single Celery worker bottleneck

### 3A. Parallel Scraping

- Multiple Celery workers with separate WebDriver instances
- Chunk parcel lists and distribute across workers
- Configurable concurrency limit (respect rate limits)

### 3B. Incremental Updates

- Track `last_scraped` timestamp per property
- Only re-scrape properties older than configurable threshold (e.g., 7 days)
- "Force refresh" option to override cache

### 3C. Database Optimization

- Add indexes on frequently queried fields: `city`, `zip_code`, `market_value`
- Implement pagination for large result sets
- Consider PostgreSQL migration for production scale

### 3D. Request Caching

- Cache search result pages for short duration (avoid duplicate searches)
- Store raw HTML snapshots for debugging failed parses

---

## 4. Data Quality

### Current Problems
- No validation of scraped data
- No deduplication logic
- No way to identify stale or incomplete records
- Scraped values not type-checked

### 4A. Data Validation

- Validate scraped values before saving:
  - Parcel ID format matches expected pattern
  - Numeric fields are within reasonable ranges
  - Required fields are present
- Flag invalid records for manual review

### 4B. Deduplication

- Detect and merge duplicate parcel IDs
- Handle address variations (123 Main St vs 123 Main Street)
- Track data source and prefer authoritative values on conflict

### 4C. Data Freshness

- Add `data_quality_score` field based on completeness
- Visual indicator for stale records (> 30 days old)
- Dashboard showing data health metrics

### 4D. Type Safety

- Strict type coercion during scraping
- Handle currency formatting ($1,234 → 1234.00)
- Parse dates consistently

---

## 5. New Features

### 5A. Additional Data Sources

- Zillow/Redfin estimates (if ToS permits)
- School district ratings
- Flood zone data from FEMA
- Crime statistics

### 5B. Property Comparison

- Side-by-side comparison of 2-4 properties
- Highlight differences in key metrics
- Shareable comparison links

### 5C. Market Trends

- Historical price tracking for properties
- Neighborhood average trends
- Price per sqft by ZIP code over time

### 5D. Saved Searches & Alerts

- User accounts with saved search criteria
- Email alerts when new properties match criteria
- Favorite/watchlist functionality

### 5E. API Access

- REST API for programmatic access
- API key authentication
- Rate limiting per user

---

## Implementation Priority

### Phase 1: Foundation (Reliability)
1. Exception hierarchy and retry decorator
2. WebDriver manager with safe methods
3. Structured logging

### Phase 2: Visibility (UX)
1. Property dashboard with existing data
2. Enhanced progress tracking
3. Job history

### Phase 3: Efficiency (Performance)
1. Incremental updates
2. Database indexes
3. Parallel scraping

### Phase 4: Trust (Data Quality)
1. Data validation
2. Freshness tracking
3. Deduplication

### Phase 5: Growth (New Features)
1. Saved searches
2. Property comparison
3. Additional data sources

---

## Technical Decisions

### To Be Determined
- [ ] WebSocket vs polling for real-time updates
- [ ] PostgreSQL migration timing
- [ ] User authentication approach (Django built-in vs OAuth)
- [ ] Frontend framework (keep vanilla JS or add React/Vue)

---

## Status

| Section | Status |
|---------|--------|
| 1. Reliability | Designed |
| 2. User Experience | Proposed |
| 3. Performance | Proposed |
| 4. Data Quality | Proposed |
| 5. New Features | Proposed |
