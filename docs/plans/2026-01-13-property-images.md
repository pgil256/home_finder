# Property Images Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display property images from PCPAO in dashboard cards and PDF report headers.

**Architecture:** Add `image_url` field to PropertyListing model, extract image URLs during scraping, display with graceful fallbacks in dashboard and PDF.

**Tech Stack:** Django models, Selenium/BeautifulSoup scraping, ReportLab PDF generation, Tailwind CSS

---

## Task 1: Add image_url Field to Model

**Files:**
- Modify: `apps/WebScraper/models.py:39` (after tax_collector_url)
- Create: Migration file (auto-generated)

**Step 1: Add the field to the model**

In `apps/WebScraper/models.py`, add after line 40 (after `tax_collector_url`):

```python
    image_url = models.URLField(max_length=500, null=True, blank=True)
```

**Step 2: Create and apply migration**

Run:
```bash
python3 manage.py makemigrations WebScraper --name add_image_url
```
Expected: Migration file created in `apps/WebScraper/migrations/`

**Step 3: Apply migration**

Run:
```bash
python3 manage.py migrate WebScraper
```
Expected: `Applying WebScraper.XXXX_add_image_url... OK`

**Step 4: Commit**

```bash
git add apps/WebScraper/models.py apps/WebScraper/migrations/
git commit -m "feat: add image_url field to PropertyListing model"
```

---

## Task 2: Extract Image URL in PCPAO Scraper

**Files:**
- Modify: `apps/WebScraper/tasks/pcpao_scraper.py:407-527` (scrape_property_details method)

**Step 1: Add image extraction helper method**

Add after line 405 (before `scrape_property_details`):

```python
    def _extract_property_image(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property image URL from detail page.

        PCPAO may have property photos in various locations. This method
        attempts multiple selectors to find the primary property image.

        Args:
            soup: BeautifulSoup object of the property detail page

        Returns:
            Full URL to property image, or None if not found
        """
        # Common selectors for property photos on county appraiser sites
        selectors = [
            'img.property-photo',
            'img.property-image',
            'img[alt*="property"]',
            'img[alt*="Property"]',
            '.property-photo img',
            '.property-image img',
            '#property-photo img',
            '.photo-gallery img',
            '.main-photo img',
            'img[src*="property"]',
            'img[src*="parcel"]',
        ]

        for selector in selectors:
            img = soup.select_one(selector)
            if img and img.get('src'):
                src = img['src']
                # Handle relative URLs
                if src.startswith('//'):
                    return f"https:{src}"
                elif src.startswith('/'):
                    return f"{self.BASE_URL.rstrip('/')}{src}"
                elif src.startswith('http'):
                    return src

        # Fallback: look for any large image that might be a property photo
        for img in soup.find_all('img'):
            src = img.get('src', '')
            # Skip small icons, logos, and UI elements
            if any(skip in src.lower() for skip in ['logo', 'icon', 'button', 'arrow', 'nav']):
                continue
            # Check for reasonable image dimensions if available
            width = img.get('width', '')
            height = img.get('height', '')
            if width and height:
                try:
                    if int(width) >= 200 and int(height) >= 150:
                        if src.startswith('/'):
                            return f"{self.BASE_URL.rstrip('/')}{src}"
                        elif src.startswith('http'):
                            return src
                except ValueError:
                    pass

        return None
```

**Step 2: Call image extraction in scrape_property_details**

In `scrape_property_details` method, add after line 517 (after `property_data.update(valuation)`):

```python
            # Extract property image URL
            image_url = self._extract_property_image(soup)
            if image_url:
                property_data['image_url'] = image_url
```

**Step 3: Update logging to include image status**

Modify line 524-526 to add image status:

```python
        logger.info(f"Scraped property {parcel_id}: address={property_data.get('address')}, "
                    f"city={property_data.get('city')}, market_value={property_data.get('market_value')}, "
                    f"owner={property_data.get('owner_name')}, sqft={property_data.get('building_sqft')}, "
                    f"image={'found' if property_data.get('image_url') else 'not found'}")
```

**Step 4: Commit**

```bash
git add apps/WebScraper/tasks/pcpao_scraper.py
git commit -m "feat: extract property image URL from PCPAO detail pages"
```

---

## Task 3: Create Static Placeholder Image

**Files:**
- Create: `static/WebScraper/images/property-placeholder.svg`

**Step 1: Create the directory if needed**

Run:
```bash
mkdir -p static/WebScraper/images
```

**Step 2: Create the placeholder SVG**

Create `static/WebScraper/images/property-placeholder.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" fill="none">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#e5e7eb"/>
      <stop offset="100%" style="stop-color:#d1d5db"/>
    </linearGradient>
  </defs>
  <rect width="400" height="300" fill="url(#bg)"/>
  <path d="M200 80 L280 140 L280 220 L120 220 L120 140 Z" stroke="#9ca3af" stroke-width="3" fill="none"/>
  <path d="M200 80 L120 140 M200 80 L280 140" stroke="#9ca3af" stroke-width="3"/>
  <rect x="170" y="160" width="60" height="60" stroke="#9ca3af" stroke-width="2" fill="none"/>
  <line x1="200" y1="160" x2="200" y2="220" stroke="#9ca3af" stroke-width="2"/>
  <line x1="170" y1="190" x2="230" y2="190" stroke="#9ca3af" stroke-width="2"/>
  <text x="200" y="260" text-anchor="middle" fill="#9ca3af" font-family="system-ui" font-size="14">No Image Available</text>
</svg>
```

**Step 3: Commit**

```bash
git add static/WebScraper/images/property-placeholder.svg
git commit -m "feat: add property placeholder image for fallback display"
```

---

## Task 4: Update Dashboard Grid View to Display Images

**Files:**
- Modify: `templates/WebScraper/dashboard.html:218-224` (grid view image section)

**Step 1: Replace the placeholder with conditional image**

Replace lines 218-224 (the grid view image div):

```html
                <!-- Property Image -->
                <div class="relative overflow-hidden">
                    {% if property.image_url %}
                    <img
                        src="{{ property.image_url }}"
                        alt="Property at {{ property.address }}"
                        class="property-card-image object-cover"
                        loading="lazy"
                        onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\'property-card-image bg-gradient-to-br from-charcoal-200 to-charcoal-300 flex items-center justify-center\'><svg class=\'w-16 h-16 text-charcoal-400\' fill=\'none\' viewBox=\'0 0 24 24\' stroke=\'currentColor\' stroke-width=\'1\'><path stroke-linecap=\'round\' stroke-linejoin=\'round\' d=\'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6\' /></svg></div>';"
                    >
                    {% else %}
                    <div class="property-card-image bg-gradient-to-br from-charcoal-200 to-charcoal-300 flex items-center justify-center">
                        <svg class="w-16 h-16 text-charcoal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                        </svg>
                    </div>
                    {% endif %}
```

**Step 2: Commit**

```bash
git add templates/WebScraper/dashboard.html
git commit -m "feat: display property images in dashboard grid view"
```

---

## Task 5: Update Dashboard List View to Display Images

**Files:**
- Modify: `templates/WebScraper/dashboard.html:367-372` (list view thumbnail)

**Step 1: Replace the list view thumbnail**

Replace lines 367-372 (the list view thumbnail div):

```html
                    <!-- Thumbnail -->
                    {% if property.image_url %}
                    <img
                        src="{{ property.image_url }}"
                        alt="Property at {{ property.address }}"
                        class="w-full sm:w-32 h-24 rounded-lg flex-shrink-0 object-cover"
                        loading="lazy"
                        onerror="this.onerror=null; this.outerHTML='<div class=\'w-full sm:w-32 h-24 bg-gradient-to-br from-charcoal-200 to-charcoal-300 rounded-lg flex-shrink-0 flex items-center justify-center\'><svg class=\'w-8 h-8 text-charcoal-400\' fill=\'none\' viewBox=\'0 0 24 24\' stroke=\'currentColor\' stroke-width=\'1\'><path stroke-linecap=\'round\' stroke-linejoin=\'round\' d=\'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6\' /></svg></div>';"
                    >
                    {% else %}
                    <div class="w-full sm:w-32 h-24 bg-gradient-to-br from-charcoal-200 to-charcoal-300 rounded-lg flex-shrink-0 flex items-center justify-center">
                        <svg class="w-8 h-8 text-charcoal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                        </svg>
                    </div>
                    {% endif %}
```

**Step 2: Commit**

```bash
git add templates/WebScraper/dashboard.html
git commit -m "feat: display property images in dashboard list view"
```

---

## Task 6: Add Image Support to PDF Generation

**Files:**
- Modify: `apps/WebScraper/tasks/listings_pdf.py`

**Step 1: Add imports for image handling**

Add after line 16 (after the existing imports):

```python
from reportlab.platypus import Image as RLImage
from io import BytesIO
import urllib.request
import urllib.error
```

**Step 2: Add image fetching helper function**

Add after line 48 (after HIDDEN_FIELDS):

```python
def fetch_property_image(url, max_width=120, max_height=90):
    """Fetch and resize property image for PDF embedding.

    Args:
        url: URL of the property image
        max_width: Maximum width in points
        max_height: Maximum height in points

    Returns:
        ReportLab Image object or None if fetch fails
    """
    if not url:
        return None

    try:
        # Set a timeout and user agent for the request
        request = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; PropertyReport/1.0)'}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            image_data = BytesIO(response.read())

        # Create ReportLab image with aspect ratio preserved
        img = RLImage(image_data, width=max_width, height=max_height)
        img.hAlign = 'LEFT'
        return img

    except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
        logger.debug(f"Failed to fetch property image from {url}: {e}")
        return None
```

**Step 3: Update HIDDEN_FIELDS to include image_url**

Modify line 45-48 to add image_url (it shouldn't appear in the data tables):

```python
HIDDEN_FIELDS = {
    'id', 'appraiser_url', 'tax_collector_url', 'created_at',
    'last_scraped', 'image_of_property', 'garage', 'image_url'
}
```

**Step 4: Modify create_property_page to include image**

In `create_property_page` function (around line 506), modify the header section. Replace lines 522-547 with:

```python
    # Main header with address, price, and optional image
    address = property_dict.get('address', 'Address Not Available')
    city = property_dict.get('city', '')
    zip_code = property_dict.get('zip_code', '')
    location_line = f"{city}, FL {zip_code}" if city else ""

    market_value = property_dict.get('market_value')
    price_display = format_value(market_value, 'currency') if market_value else '-'

    # Try to fetch property image
    image_url = property_dict.get('image_url')
    property_image = fetch_property_image(image_url) if image_url else None

    header_left = [
        Paragraph(str(address), styles['property_title']),
        Paragraph(location_line, styles['property_subtitle']),
    ]

    # Property type badge
    prop_type = property_dict.get('property_type', '-')

    if property_image:
        # Two-column layout with image
        address_block = Table([[e] for e in header_left], colWidths=[2.8*inch])
        address_block.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))

        main_header = Table(
            [[property_image, address_block, Paragraph(price_display, styles['price_large'])]],
            colWidths=[1.3*inch, 2.7*inch, 2.5*inch]
        )
    else:
        # Original layout without image
        main_header = Table(
            [[header_left, Paragraph(price_display, styles['price_large'])]],
            colWidths=[4*inch, 2.5*inch]
        )

    main_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (-1, 0), (-1, 0), 'RIGHT'),
    ]))
    story.append(main_header)
```

**Step 5: Commit**

```bash
git add apps/WebScraper/tasks/listings_pdf.py
git commit -m "feat: add property images to PDF report headers"
```

---

## Task 7: Manual Testing

**Step 1: Start development server**

Run:
```bash
python3 manage.py runserver
```

**Step 2: Test dashboard with existing data**

- Navigate to http://localhost:8000/dashboard/
- Verify properties without images show placeholder
- Check both grid and list views

**Step 3: Test scraper with a few properties**

- Run a small scrape job for 2-3 properties
- Check logs for "image=found" or "image=not found"
- Verify database has image_url populated (if images exist on PCPAO)

**Step 4: Test PDF generation**

- Generate a PDF report
- Verify properties with images show thumbnails in header
- Verify properties without images use standard header layout

**Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues found during manual testing"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `apps/WebScraper/models.py` | Add `image_url` URLField |
| `apps/WebScraper/tasks/pcpao_scraper.py` | Add `_extract_property_image()` method, call it in `scrape_property_details()` |
| `static/WebScraper/images/property-placeholder.svg` | New placeholder image |
| `templates/WebScraper/dashboard.html` | Update grid and list views to show images with fallback |
| `apps/WebScraper/tasks/listings_pdf.py` | Add `fetch_property_image()`, modify `create_property_page()` for image header |

## Notes

- Image extraction uses multiple CSS selectors to handle various PCPAO page structures
- All image displays have graceful fallbacks to placeholders
- PDF image fetching has a 5-second timeout to avoid blocking report generation
- Images are lazy-loaded in dashboard for performance
