# Street View Property Images Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display Google Street View images of properties in dashboard and PDF reports.

**Architecture:** Fetch Street View image URLs during scraping using Google's Static API, store in existing `image_url` field, leverage existing dashboard/PDF image display code.

**Tech Stack:** Google Street View Static API, Django settings, existing Selenium scraper

---

## Task 1: Create Street View Service

**Files:**
- Create: `apps/WebScraper/services/__init__.py`
- Create: `apps/WebScraper/services/street_view.py`

**Step 1: Create the services package**

Create `apps/WebScraper/services/__init__.py`:
```python
"""WebScraper services package."""
```

**Step 2: Create the Street View service**

Create `apps/WebScraper/services/street_view.py`:
```python
"""Google Street View Static API integration."""

import logging
import urllib.parse
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Log warning once if API key missing
_api_key_warning_logged = False


def get_street_view_url(
    address: str,
    city: str = None,
    zip_code: str = None,
    size: str = None
) -> Optional[str]:
    """Build Google Street View Static API URL for a property.

    Checks metadata endpoint first to verify imagery exists.

    Args:
        address: Street address (e.g., "123 Main St")
        city: City name (e.g., "Clearwater")
        zip_code: ZIP code (e.g., "33755")
        size: Image size as "WxH" (default from settings)

    Returns:
        Street View image URL if imagery exists, None otherwise.
    """
    global _api_key_warning_logged

    api_key = getattr(settings, 'GOOGLE_STREET_VIEW_API_KEY', None)
    if not api_key:
        if not _api_key_warning_logged:
            logger.warning("GOOGLE_STREET_VIEW_API_KEY not configured - images disabled")
            _api_key_warning_logged = True
        return None

    if not address:
        return None

    # Build full address string
    location_parts = [address]
    if city:
        location_parts.append(city)
    location_parts.append("FL")  # State is always Florida for this app
    if zip_code:
        location_parts.append(zip_code)

    location = ", ".join(location_parts)

    # Check if Street View imagery exists (free API call)
    if not _has_street_view_imagery(location, api_key):
        logger.debug(f"No Street View imagery for: {location}")
        return None

    # Build image URL
    size = size or getattr(settings, 'STREET_VIEW_IMAGE_SIZE', '640x480')

    params = {
        'size': size,
        'location': location,
        'key': api_key,
    }

    url = f"https://maps.googleapis.com/maps/api/streetview?{urllib.parse.urlencode(params)}"
    logger.debug(f"Street View URL generated for: {location}")
    return url


def _has_street_view_imagery(location: str, api_key: str) -> bool:
    """Check if Street View imagery exists for a location.

    Uses the metadata endpoint which is free and doesn't count
    against the image API quota.

    Args:
        location: Full address string
        api_key: Google API key

    Returns:
        True if imagery exists, False otherwise.
    """
    metadata_url = "https://maps.googleapis.com/maps/api/streetview/metadata"

    params = {
        'location': location,
        'key': api_key,
    }

    try:
        response = requests.get(metadata_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get('status') == 'OK'
    except requests.RequestException as e:
        logger.warning(f"Street View metadata check failed for {location}: {e}")
        return False
```

**Step 3: Commit**

```bash
git add apps/WebScraper/services/
git commit -m "feat: add Google Street View service for property images"
```

---

## Task 2: Add Settings Configuration

**Files:**
- Modify: `home_finder/settings.py`

**Step 1: Add Street View settings**

Add after the existing environment variable section (around line 30):

```python
# Google Street View API
GOOGLE_STREET_VIEW_API_KEY = os.environ.get('GOOGLE_STREET_VIEW_API_KEY')
STREET_VIEW_IMAGE_SIZE = '640x480'
```

**Step 2: Update .env.example (if exists) or document in README**

Add to `.env` (user must configure):
```bash
GOOGLE_STREET_VIEW_API_KEY=your_api_key_here
```

**Step 3: Commit**

```bash
git add home_finder/settings.py
git commit -m "feat: add Street View API configuration settings"
```

---

## Task 3: Integrate Street View into Scraper

**Files:**
- Modify: `apps/WebScraper/tasks/pcpao_scraper.py`

**Step 1: Add import at top of file**

Add with other imports (around line 10):

```python
from apps.WebScraper.services.street_view import get_street_view_url
```

**Step 2: Replace PCPAO image extraction with Street View**

In `scrape_property_details()` method, find the section that calls `_extract_property_image()` (around line 590-596) and replace with:

```python
            # Get Street View image instead of PCPAO image
            image_url = get_street_view_url(
                address=property_data.get('address'),
                city=property_data.get('city'),
                zip_code=property_data.get('zip_code')
            )
            if image_url:
                property_data['image_url'] = image_url
```

**Step 3: Update logging**

The existing logging already handles image status:
```python
f"image={'found' if property_data.get('image_url') else 'not found'}"
```

This will now reflect Street View availability.

**Step 4: Commit**

```bash
git add apps/WebScraper/tasks/pcpao_scraper.py
git commit -m "feat: integrate Street View images into property scraper"
```

---

## Task 4: Testing

**Step 1: Set up API key**

Add to `.env`:
```bash
GOOGLE_STREET_VIEW_API_KEY=your_actual_key
```

**Step 2: Test service directly**

```bash
python3 manage.py shell
```

```python
from apps.WebScraper.services.street_view import get_street_view_url
url = get_street_view_url("400 Cleveland St", "Clearwater", "33755")
print(url)  # Should print a Google Street View URL
```

**Step 3: Test scraper with a few properties**

Run a small scrape and check:
- Logs show "image=found" for most properties
- Database `image_url` field contains Street View URLs

**Step 4: Verify dashboard display**

- Start dev server: `python3 manage.py runserver`
- Navigate to dashboard
- Verify images load (not placeholders)

**Step 5: Verify PDF generation**

- Generate a PDF report
- Verify Street View images appear in property headers

---

## Summary

| File | Change |
|------|--------|
| `apps/WebScraper/services/__init__.py` | New package init |
| `apps/WebScraper/services/street_view.py` | New Street View API service |
| `home_finder/settings.py` | Add API key and image size settings |
| `apps/WebScraper/tasks/pcpao_scraper.py` | Replace PCPAO image extraction with Street View |

## API Costs

- Metadata checks: Free
- Image URLs: $7 per 1,000 requests
- Free tier: $200/month (~28,500 images)

## Notes

- API key is visible in image URLs (acceptable with restricted key)
- Metadata check prevents storing URLs that return "no imagery" screen
- Existing dashboard/PDF code handles display automatically
- Graceful fallback to placeholder if API key not configured
