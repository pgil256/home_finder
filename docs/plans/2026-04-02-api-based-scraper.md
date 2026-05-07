# API-Based PCPAO Scraper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Selenium browser automation with direct PCPAO API calls for property search and detail scraping, enabling pre-filtering by property use code and eliminating Chrome dependency.

**Architecture:** The PCPAO website exposes a server-side DataTables API at `/dal/quicksearch/searchProperty` that returns property listings as JSON. Detail pages at `/property-details?s=<strap_id>` return full HTML without JS rendering. Both require a session cookie obtained by visiting any page first. The new scraper uses `requests.Session` for all HTTP calls and `BeautifulSoup` for HTML parsing — no browser needed.

**Tech Stack:** Python `requests`, `BeautifulSoup4` (both already in requirements.txt). Selenium/webdriver-manager become optional (kept for backwards compatibility but unused by default path).

---

## Key Discovery: PCPAO API Structure

**Search API:** `POST https://www.pcpao.gov/dal/quicksearch/searchProperty`
- Requires session cookie (GET any page first)
- Requires `X-Requested-With: XMLHttpRequest` header
- DataTables server-side format (`draw`, `start`, `length`, `columns[N][data]`, `order[0][column]`, `order[0][dir]`)
- Custom params: `input` (search term), `searchsort` (one of: `address`, `owner`, `parcel_number`, `subcondo`)
- Returns JSON with `recordsTotal`, `recordsFiltered`, `data` (array of arrays)

**Response columns:**
- `col[4]` = Parcel ID (e.g., "01-30-14-94577-000-0200")
- `col[5]` = Address (e.g., "2517 CORAL CT")
- `col[6]` = Municipality code (e.g., "IRB", "CLW", "SRTU")
- `col[7]` = Use code + description (e.g., "0110 Single Family Home", "0430 Condominium")
- `col[8]` = Legal description
- `col[2]` contains `<a href="...property-details?s=<strap_id>...">` link

**Use code mapping for pre-filtering:**
- `01xx` = Residential (0100 Single Family, 0110 SF Home, 0133 PUD, etc.)
- `04xx` = Condos (0430 Condo, 0431 Condo land lease, 0436 Condo conversion)
- `08xx` = Multi-family (0810 SF multi-house, 0820 Duplex/Triplex/Fourplex)
- `10xx` = Vacant land (1000 Commercial, 1090 w/XFSB)
- `17xx` = Office, `48xx` = Warehouse, `19xx` = Medical

**Detail pages:** `GET https://www.pcpao.gov/property-details?s=<strap_id>` returns full HTML with all property data in raw HTML (no JS rendering required). The existing `BeautifulSoup` extraction methods work unchanged.

---

## Property Type → Use Code Mapping

The search form offers these types. Map them to PCPAO use code prefixes for pre-filtering:

| App Property Type | PCPAO Use Code Prefixes |
|---|---|
| Single Family | `01` (residential) |
| Condo | `04` (condo) |
| Townhouse | `01` (often coded as residential PUD) |
| Multi-Family | `08` (multi-family) |
| Vacant Land | `00`, `10`, `11`, `12`, `13`, `14`, `15`, `16` |
| Mobile Home | `02` (mobile home) |
| Commercial | `10`-`39`, `40`-`49` (non-condo), `17`, `19`, `48` |

---

### Task 1: Add API client method to PCPAOScraper

**Files:**
- Modify: `apps/WebScraper/tasks/pcpao_scraper.py`

**Step 1: Add the `_search_via_api` method**

Add a new method that uses `requests.Session` to hit the PCPAO search API directly. This replaces the Selenium-based `search_properties_with_urls` for the default path.

```python
def _search_via_api(self, search_criteria: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, str]]:
    """Search properties via PCPAO DataTables API (no browser needed).
    
    Returns list of dicts with parcel_id, detail_url, use_code, address, municipality.
    """
    import requests as req
    from bs4 import BeautifulSoup as BS
    
    session = req.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest',
    })
    
    # Establish session cookie
    session.get('https://www.pcpao.gov/quick-search', timeout=15)
    
    # Build search input from criteria
    search_terms = []
    if search_criteria.get('zip_code'):
        search_terms.append(search_criteria['zip_code'])
    elif search_criteria.get('address'):
        search_terms.append(search_criteria['address'])
    elif search_criteria.get('city'):
        search_terms.append(search_criteria['city'])
    elif search_criteria.get('owner_name'):
        search_terms.append(search_criteria['owner_name'])
    
    search_input = ' '.join(search_terms) if search_terms else 'Clearwater'
    
    # Determine searchsort based on criteria
    if search_criteria.get('owner_name'):
        searchsort = 'owner'
    elif search_criteria.get('parcel_id'):
        searchsort = 'parcel_number'
    else:
        searchsort = 'address'
    
    # Determine how many to fetch (overfetch to allow for filtering)
    fetch_count = min((limit or 50) * 5, 500)
    
    # Get property type filter for pre-filtering
    requested_types = search_criteria.get('property_type', [])
    if isinstance(requested_types, str):
        requested_types = [requested_types]
    use_code_prefixes = self._get_use_code_prefixes(requested_types)
    
    parcels = []
    start = 0
    
    while len(parcels) < (limit or 50):
        resp = session.post(
            'https://www.pcpao.gov/dal/quicksearch/searchProperty',
            data={
                'draw': '1', 'start': str(start), 'length': str(fetch_count),
                'input': search_input, 'searchsort': searchsort,
                'url': 'https://www.pcpao.gov',
                'columns[0][data]': '0', 'columns[1][data]': '1',
                'columns[2][data]': '2', 'columns[3][data]': '3',
                'columns[4][data]': '4', 'columns[5][data]': '5',
                'columns[6][data]': '6', 'columns[7][data]': '7',
                'columns[8][data]': '8',
                'order[0][column]': '2', 'order[0][dir]': 'asc',
            },
            timeout=30,
        )
        data = resp.json()
        
        if not data['data']:
            break
        
        for row in data['data']:
            use_text = BS(str(row[7]), 'html.parser').get_text(strip=True)
            use_code = use_text[:2] if use_text else ''
            
            # Pre-filter by use code if property types requested
            if use_code_prefixes and use_code not in use_code_prefixes:
                continue
            
            parcel_id = BS(str(row[4]), 'html.parser').get_text(strip=True)
            address = BS(str(row[5]), 'html.parser').get_text(strip=True)
            municipality = BS(str(row[6]), 'html.parser').get_text(strip=True)
            
            link = BS(str(row[2]), 'html.parser').find('a')
            detail_url = link['href'] if link else None
            if detail_url and not detail_url.startswith('http'):
                detail_url = f"{self.BASE_URL}{detail_url.lstrip('/')}"
            
            parcels.append({
                'parcel_id': parcel_id,
                'detail_url': detail_url,
                'use_code': use_text,
                'address': address,
                'municipality': municipality,
            })
            
            if limit and len(parcels) >= limit:
                break
        
        # If we got fewer results than requested, we've exhausted results
        if len(data['data']) < fetch_count:
            break
        start += fetch_count
    
    logger.info(f"API search for '{search_input}': {len(parcels)} properties "
                f"(pre-filtered from {data.get('recordsTotal', '?')} total)")
    return parcels


@staticmethod
def _get_use_code_prefixes(property_types: List[str]) -> set:
    """Map user-facing property types to PCPAO use code prefixes."""
    if not property_types:
        return set()
    
    TYPE_TO_CODES = {
        'single family': {'01'},
        'condo': {'04'},
        'townhouse': {'01'},
        'multi-family': {'08'},
        'vacant land': {'00', '10', '11', '12', '13', '14', '15', '16'},
        'mobile home': {'02'},
        'commercial': {'10', '11', '12', '13', '14', '15', '16', '17', '18', '19',
                        '20', '21', '22', '23', '24', '25', '26', '27', '28', '29',
                        '30', '31', '32', '33', '34', '35', '36', '37', '38', '39',
                        '48'},
    }
    
    prefixes = set()
    for pt in property_types:
        codes = TYPE_TO_CODES.get(pt.lower(), set())
        prefixes.update(codes)
    return prefixes
```

**Step 2: Add `_scrape_detail_via_requests` method**

Replace Selenium detail page scraping with pure `requests`:

```python
def _scrape_detail_via_requests(self, parcel_id: str, detail_url: str, session=None) -> Dict[str, Any]:
    """Scrape property detail page using requests (no browser)."""
    import requests as req
    
    if session is None:
        session = req.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        session.get('https://www.pcpao.gov/quick-search', timeout=15)
    
    property_data = {'parcel_id': parcel_id}
    
    try:
        resp = session.get(detail_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        property_data['appraiser_url'] = detail_url
        
        # Reuse ALL existing extraction methods (they only need a BeautifulSoup object)
        # H2 fields
        h2_fields = {
            'building_sqft': ['Living SF', 'Heated SF'],
            'gross_sqft': ['Gross SF'],
            'living_units': ['Living Units'],
            'buildings': ['Buildings'],
        }
        for field, labels in h2_fields.items():
            for label in labels:
                value = self._get_h2_value(soup, label)
                if value and value not in ['n/a', 'N/A', '']:
                    try:
                        parsed_value = int(re.sub(r'[^\d]', '', value))
                        if parsed_value <= 10_000_000:
                            property_data[field] = parsed_value
                            break
                    except (ValueError, TypeError):
                        pass
        
        page_parcel = self._get_parcel_from_page(soup)
        if page_parcel:
            property_data['parcel_id'] = page_parcel
        
        sibling_fields = {
            'owner_name': 'Owner Name',
            'year_built': 'Year Built',
            'property_type': 'Property Use',
        }
        for field, label in sibling_fields.items():
            value = self._get_sibling_value(soup, label)
            if value and value not in ['n/a', 'N/A', '']:
                if field == 'year_built':
                    try:
                        year_match = re.search(r'\b(19|20)\d{2}\b', value)
                        if year_match:
                            year = int(year_match.group())
                            if 1800 <= year <= 2100:
                                property_data[field] = year
                    except (ValueError, TypeError):
                        pass
                elif field == 'owner_name':
                    value = re.sub(r'More$', '', value).strip()
                    value = re.sub(r'([a-z])([A-Z])', r'\1 \2', value)
                    property_data[field] = value
                else:
                    property_data[field] = value
        
        address_parts = self._get_address_parts(soup)
        property_data.update(address_parts)
        
        valuation = self._get_valuation_data(soup)
        property_data.update(valuation)
        
        image_url = get_street_view_url(
            address=property_data.get('address'),
            city=property_data.get('city'),
            zip_code=property_data.get('zip_code')
        )
        if image_url:
            property_data['image_url'] = image_url
    
    except Exception as e:
        logger.error(f"Error scraping property {parcel_id}: {e}")
    
    logger.info(f"Scraped property {parcel_id}: address={property_data.get('address')}, "
                f"city={property_data.get('city')}, market_value={property_data.get('market_value')}, "
                f"owner={property_data.get('owner_name')}, sqft={property_data.get('building_sqft')}, "
                f"image={'found' if property_data.get('image_url') else 'not found'}")
    
    return property_data
```

**Step 3: Update `scrape_by_criteria` to use API path**

Replace the main entry point to use the API methods:

```python
def scrape_by_criteria(self, search_criteria: Dict[str, Any], limit: Optional[int] = None, max_workers: int = 3) -> List[Dict[str, Any]]:
    """Search and scrape properties using direct API calls (no browser needed)."""
    import requests as req
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Step 1: Search via API
    parcels = self._search_via_api(search_criteria, limit=limit)
    
    if not parcels:
        return []
    
    logger.info(f"Scraping details for {len(parcels)} properties via API")
    
    # Step 2: Create shared session for detail page requests
    session = req.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    session.get('https://www.pcpao.gov/quick-search', timeout=15)
    
    # Step 3: Scrape details (sequential with small delay to be respectful)
    results = []
    for i, parcel in enumerate(parcels):
        detail_url = parcel.get('detail_url')
        if not detail_url:
            continue
        property_data = self._scrape_detail_via_requests(
            parcel['parcel_id'], detail_url, session=session
        )
        results.append(property_data)
        time.sleep(0.3)  # Rate limiting
    
    return results
```

**Step 4: Update `scrape_data.py` to use new API path**

The `scrape_pinellas_properties` task in `scrape_data.py` needs a small update to not call `setup_driver()`/`close_driver()` since the new path doesn't need them:

In `scrape_pinellas_properties`, replace:
```python
scraper.setup_driver()
try:
    parcels = scraper.search_properties_with_urls(search_criteria)
    if limit:
        parcels = parcels[:limit]
finally:
    scraper.close_driver()
```
With:
```python
parcels = scraper._search_via_api(search_criteria, limit=limit)
```

And replace the parallel scraping section with:
```python
# Scrape details via API (no browser needed)
import requests as req
session = req.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
session.get('https://www.pcpao.gov/quick-search', timeout=15)

scraped_properties = []
for i, parcel in enumerate(parcels_to_scrape):
    detail_url = parcel.get('detail_url')
    if not detail_url:
        continue
    property_data = scraper._scrape_detail_via_requests(
        parcel['parcel_id'], detail_url, session=session
    )
    scraped_properties.append(property_data)
    progress_recorder.set_progress(
        10 + int(60 * (i + 1) / len(parcels_to_scrape)), 100,
        description=f"Scraping property {i + 1}/{len(parcels_to_scrape)}..."
    )
    time.sleep(0.3)
```

**Step 5: Run test**

Run: `source venv/bin/activate && python3 -c "from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper; s = PCPAOScraper(); results = s.scrape_by_criteria({'zip_code': '33756', 'property_type': ['Single Family']}, limit=3); print(f'{len(results)} results'); [print(f'  {r.get(\"parcel_id\")} {r.get(\"property_type\")} {r.get(\"address\")} {r.get(\"city\")} ${r.get(\"market_value\")}') for r in results]"`

Expected: 3 Single Family properties with addresses, cities, market values, and no browser launched.

**Step 6: Commit**

```bash
git add apps/WebScraper/tasks/pcpao_scraper.py apps/WebScraper/tasks/scrape_data.py
git commit -m "feat: replace Selenium search with direct PCPAO API calls

Use requests.Session to hit PCPAO DataTables API directly,
pre-filter by use code, and scrape detail pages via HTTP.
Eliminates Chrome browser dependency for search and detail scraping."
```

---

### Task 2: Deploy updated worker to Railway

**Step 1: Deploy to Railway**

Run: `railway up --service web`

**Step 2: Verify worker starts**

Run: `railway logs --lines 10`
Expected: Celery worker starting without Chrome errors

**Step 3: Test end-to-end via the live site**

Navigate to https://homefinder-jet.vercel.app/scraper/, select "St. Petersburg" + "Single Family", submit. Verify the progress page completes and the dashboard shows Single Family homes with images.

---

## Benefits of This Approach

1. **No Chrome/Selenium needed** for searching — pure HTTP requests
2. **Pre-filtering by use code** — only fetch detail pages for matching property types
3. **Much faster** — no browser startup, no JS rendering, no page navigation
4. **Lower memory** — no Chrome processes on Railway worker
5. **More reliable** — no flaky Selenium waits, no stale element exceptions
6. **Simpler Dockerfile** — Chrome installation could be removed (but kept for now)
