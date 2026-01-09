# Home Finder UX/UI Redesign

**Date:** 2026-01-08
**Status:** Approved

## Overview

A comprehensive redesign addressing four core problems:
1. Clunky workflow with too many steps
2. Dated visual design
3. Difficult property browsing experience
4. Lack of professional polish

Additionally: Add external listing links (Zillow, Redfin, Realtor.com) for cross-referencing.

---

## 1. Simplified Workflow

### Current Flow (5 steps)
Home → Keyword Selection → Search Parameters → Scraping Progress → Results (Excel/PDF)

### New Flow (3 steps)
Home → **Search** → **Property Dashboard**

### Changes

1. **Eliminate Keyword Selection page** - Merge all search criteria into a unified Search page
2. **Unified Search Page** - Single form with location autocomplete, price/bedroom sliders, property type chips
3. **Background processing** - Show cached/existing data immediately while scraper updates in background. Subtle "Refreshing data..." indicator instead of blocking progress page
4. **Property Dashboard destination** - All searches land on filterable property grid. Users browse while new data streams in

---

## 2. Visual Design System

### Color Palette

| Role | Color | Hex | Usage |
|------|-------|-----|-------|
| Primary | Deep Teal | `#0D7377` | Buttons, links, active states |
| Secondary | Warm Coral | `#FF6B6B` | Accents, favorites, alerts |
| Neutral Dark | Charcoal | `#2D3436` | Text, headers |
| Neutral Light | Warm Gray | `#F8F9FA` | Backgrounds, cards |
| Success | Emerald | `#10B981` | Available, good values |
| Warning | Amber | `#F59E0B` | Tax delinquent, attention |

### Typography

- **Headings:** Inter or Plus Jakarta Sans (modern, geometric)
- **Body:** System font stack for performance
- **Property prices:** Tabular numerals for alignment

### Design Elements

- **Shadows:** Soft shadows on cards, hover lift effects
- **Border radius:** `rounded-xl` for cards, `rounded-full` for buttons/chips
- **White space:** Generous padding throughout
- **Micro-interactions:** 200ms ease transitions on hover states
- **Photography:** Pinellas County hero images from Unsplash

### Header

- White/light background (not black)
- Sticky navigation with blur backdrop
- Prominent "Search Properties" CTA button

---

## 3. Property Dashboard

### Layout Modes

**Grid View (default):**
- Responsive grid: 3 columns desktop, 2 tablet, 1 mobile
- Property cards showing:
  - Photo placeholder / street view
  - Address, city, ZIP
  - Market value (primary) with assessed value below
  - Stats row: beds, baths, sqft, year built
  - Tax status badge (green = Paid, red = Delinquent)
  - Quick actions: Save, Details, External Links

**List View (toggle):**
- Compact rows for scanning many properties

### Filtering Sidebar

- **Location:** City dropdown, ZIP multi-select
- **Price Range:** Dual-handle slider with min/max inputs
- **Property Type:** Chips (Single Family, Condo, Multi-Family, etc.)
- **Bedrooms/Bathrooms:** Quick buttons (1+, 2+, 3+, 4+)
- **Year Built:** Range slider
- **Tax Status:** Checkbox filters
- **Clear All Filters** button

### Sorting

Dropdown options:
- Price (Low → High)
- Price (High → Low)
- Newest Listed
- Oldest
- Largest (sqft)
- Smallest (sqft)

### External Links

Each property includes "View on..." links:
- Zillow (constructed URL: `zillow.com/homes/{address}`)
- Redfin (`redfin.com/search?q={address}`)
- Realtor.com (`realtor.com/realestateandhomes-search/{address}`)
- Google Maps (for location context)

---

## 4. Professional Polish

### Loading States

- Skeleton loaders for property cards (animated gray placeholders)
- Header progress indicator during background scraping (pulsing dot)
- Optimistic UI with graceful error reversion

### Empty States

- Friendly illustrations when no results match
- Clear messaging with filter adjustment suggestions
- Quick action buttons to reset/broaden search

### Feedback & Notifications

- Toast notifications for actions ("Search saved", "Exporting...")
- Inline form validation (green checkmarks, red errors)
- Confirmation modals only for destructive actions

### Responsive Design

- Mobile-first property cards
- Bottom sheet filters on mobile (instead of sidebar)
- Touch-friendly tap targets (44px minimum)
- Optional: Swipe gestures on property cards

### Performance

- Instant page transitions with subtle fade
- Lazy load images on scroll
- Cached results show immediately

### Trust Signals

- "Data sourced from Pinellas County Property Appraiser & Tax Collector"
- Last updated timestamp per property
- County/official source badges

---

## Technical Approach

### Frontend Stack (unchanged)
- Django templates
- Tailwind CSS (update config with new colors)
- Vanilla JavaScript + existing SortableJS
- Webpack build pipeline

### New Components Needed

1. **Search form component** - Location autocomplete, range sliders, chip selectors
2. **Property card component** - Reusable card with all property data
3. **Filter sidebar component** - Collapsible on mobile
4. **Skeleton loader component** - For loading states
5. **Toast notification system** - Lightweight JS toast library or custom

### CSS Updates

- Extend Tailwind config with custom color palette
- Add Inter/Plus Jakarta Sans font
- Create component classes for cards, buttons, badges

### Template Changes

| Current | Action |
|---------|--------|
| `home.html` | Redesign hero, update CTAs |
| `keyword-selection.html` | **Delete** (merge into search) |
| `web-scraper.html` | Replace with unified Search page |
| `scraping-progress.html` | Convert to background indicator |
| **New:** `dashboard.html` | Property grid with filters |
| **New:** `property-detail.html` | Single property view |

### Backend Adjustments

- New view: Property dashboard with filtering/pagination
- API endpoint: Property search with query params
- Background task status endpoint for header indicator
- External link URL builders (Zillow, Redfin, Realtor.com)

---

## Implementation Order

1. **Design system foundation** - Colors, typography, Tailwind config
2. **Header/navigation redesign** - New sticky header with search CTA
3. **Unified search page** - Replace keyword selection + scraper form
4. **Property dashboard** - Grid view, cards, basic filtering
5. **Filter sidebar** - Full filtering capabilities
6. **Loading states & polish** - Skeletons, toasts, transitions
7. **External links** - Zillow/Redfin/Realtor.com integration
8. **Mobile optimization** - Bottom sheets, responsive refinements
9. **Home page refresh** - Updated hero and feature sections
