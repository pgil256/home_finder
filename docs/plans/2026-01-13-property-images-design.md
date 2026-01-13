# Property Images Feature Design

## Overview

Add property images from PCPAO to the dashboard cards and PDF reports.

## Requirements

- **Image Source**: PCPAO website property detail pages
- **Dashboard Display**: Card thumbnail replacing placeholder icons
- **PDF Display**: Small thumbnail in property page header

## Data Model

### PropertyListing Model Change

Add a single field to store the image URL:

```python
image_url = models.URLField(max_length=500, blank=True, null=True)
```

### Design Decisions

- **Store URL, not image**: Reference PCPAO-hosted images directly
- **No local storage**: Avoids storage costs and keeps images current
- **Nullable field**: Graceful fallback when images unavailable

## PCPAO Scraper Enhancement

### Location
`apps/WebScraper/tasks/pcpao_scraper.py` - `scrape_property_details()` method

### Changes

1. Add image extraction after page loads:
   - Look for property photo in standard PCPAO page structure
   - Extract `src` attribute from the image element
   - Store full URL (handle relative paths)

2. Add to returned `property_data` dict:
   ```python
   property_data['image_url'] = image_url
   ```

### Fallback
If no image found, `image_url` remains unset (null in database).

## Dashboard UI

### Grid View Card Changes

Location: `templates/WebScraper/dashboard.html`

Replace inline SVG placeholder with dynamic image:

```html
<div class="relative h-48 overflow-hidden">
  {% if property.image_url %}
    <img
      src="{{ property.image_url }}"
      alt="Property at {{ property.address }}"
      class="w-full h-48 object-cover"
      loading="lazy"
      onerror="this.onerror=null; this.src='/static/WebScraper/images/property-placeholder.svg';"
    >
  {% else %}
    <div class="w-full h-48 bg-gradient-to-br from-charcoal-200 to-charcoal-300 flex items-center justify-center">
      <!-- Existing SVG placeholder -->
    </div>
  {% endif %}
</div>
```

### List View Changes

Same pattern for the thumbnail column in list view.

### Static Placeholder

Create `static/WebScraper/images/property-placeholder.svg` - house icon on gradient background for broken image fallback.

## PDF Report

### Location
`apps/WebScraper/tasks/listings_pdf.py`

### Property Page Header Layout

Current:
```
┌─────────────────────────────────────────┐
│ Property 1 of 150                       │
│ 123 MAIN ST                             │
│ Clearwater, FL 33755                    │
│ $245,000                                │
└─────────────────────────────────────────┘
```

New with thumbnail:
```
┌─────────────────────────────────────────┐
│ Property 1 of 150                       │
├────────────┬────────────────────────────┤
│            │ 123 MAIN ST                │
│  [IMAGE]   │ Clearwater, FL 33755       │
│  120x90    │ $245,000                   │
│            │                            │
├────────────┴────────────────────────────┤
│ Quick Stats Row...                      │
└─────────────────────────────────────────┘
```

### Implementation

1. Import ReportLab Image class and urllib for fetching
2. Create helper function to safely fetch/embed image:
   ```python
   def get_property_image(url, width=120, height=90):
       """Fetch image from URL and return ReportLab Image object."""
       # Returns None on failure
   ```
3. Modify property page generation:
   - If `image_url` exists, attempt to fetch and create two-column header
   - If fetch fails or no URL, use current full-width header

### Image Specifications
- Size: 120x90 pixels (4:3 aspect ratio)
- Position: Left side of header, aligned with address block

## Migration

```bash
python manage.py makemigrations WebScraper
python manage.py migrate
```

## Files to Modify

1. `apps/WebScraper/models.py` - Add `image_url` field
2. `apps/WebScraper/tasks/pcpao_scraper.py` - Extract image URL
3. `templates/WebScraper/dashboard.html` - Display images in cards
4. `apps/WebScraper/tasks/listings_pdf.py` - Add thumbnail to property pages
5. `static/WebScraper/images/property-placeholder.svg` - New fallback image

## Testing

1. Run scraper on a few properties, verify `image_url` populated
2. Check dashboard displays images correctly
3. Generate PDF, verify thumbnails appear
4. Test fallback behavior with missing/broken URLs
