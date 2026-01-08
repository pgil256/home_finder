# Critical Bug Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 critical bugs preventing the Home Finder app from functioning end-to-end.

**Architecture:** Fix each issue in isolation, verify with Django checks, then test integrated workflow.

**Tech Stack:** Django 5.0.4, Celery, Redis

---

### Task 1: Remove Duplicate SessionMiddleware

**Files:**
- Modify: `home_finder/settings.py:49-58`

**Step 1: Remove duplicate middleware**

Change lines 49-58 from:
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

To:
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

**Step 2: Verify Django check passes**

Run: `python manage.py check`
Expected: "System check identified no issues"

**Step 3: Commit**

```bash
git add home_finder/settings.py
git commit -m "fix: remove duplicate SessionMiddleware"
```

---

### Task 2: Fix Admin Field References

**Files:**
- Modify: `apps/WebScraper/admin.py`

**Step 1: Update admin configuration**

Replace entire file with:
```python
from django.contrib import admin
from .models import PropertyListing


class PropertyListingAdmin(admin.ModelAdmin):
    list_display = (
        'parcel_id', 'address', 'city', 'market_value', 'building_sqft',
        'bedrooms', 'bathrooms', 'land_size', 'tax_status', 'last_scraped'
    )
    list_filter = ('city', 'property_type', 'tax_status', 'delinquent', 'bedrooms')
    search_fields = ('parcel_id', 'address', 'owner_name', 'city')
    list_per_page = 25
    readonly_fields = ('last_scraped', 'created_at')


admin.site.register(PropertyListing, PropertyListingAdmin)
```

**Step 2: Verify Django check passes**

Run: `python manage.py check`
Expected: "System check identified no issues"

**Step 3: Commit**

```bash
git add apps/WebScraper/admin.py
git commit -m "fix: update admin to use correct PropertyListing fields"
```

---

### Task 3: Remove Missing View URLs

**Files:**
- Modify: `apps/WebScraper/urls.py`

**Step 1: Remove broken URL patterns**

Replace entire file with:
```python
from django.urls import path
from . import views

urlpatterns = [
    path("scraper/", views.web_scraper_view, name="scraper"),
    path("scraping-progress/<str:task_id>/", views.scraping_progress, name="scraping-progress"),
    path("task-status/<str:task_id>/", views.get_task_status, name="task-status"),
]
```

**Step 2: Verify Django check passes**

Run: `python manage.py check`
Expected: "System check identified no issues"

**Step 3: Commit**

```bash
git add apps/WebScraper/urls.py
git commit -m "fix: remove non-existent view references from URLs"
```

---

### Task 4: Fix View Context

**Files:**
- Modify: `apps/WebScraper/views.py:69-71`

**Step 1: Update web_scraper_view to pass correct context**

Change lines 69-71 from:
```python
    # GET request - show the scraping interface
    keywords = Keyword.objects.filter(is_active=True).order_by('-priority')
    return render(request, 'WebScraper/web-scraper.html', {'keywords': keywords})
```

To:
```python
    # GET request - show the scraping interface
    keywords = Keyword.objects.filter(is_active=True).order_by('-priority')
    context = {
        'keywords': keywords,
        'state_options': ['FL'],  # Pinellas County is in Florida
    }
    return render(request, 'WebScraper/web-scraper.html', context)
```

**Step 2: Verify Django check passes**

Run: `python manage.py check`
Expected: "System check identified no issues"

**Step 3: Commit**

```bash
git add apps/WebScraper/views.py
git commit -m "fix: add state_options to scraper view context"
```

---

### Task 5: Fix Template to Use Keyword Model Fields

**Files:**
- Modify: `templates/WebScraper/web-scraper.html`

**Step 1: Fix form action URL**

Change line 9 from:
```html
    <form method="post" action="{% url 'submit-form' %}" class="space-y-6" onsubmit="return validateForm();">
```

To:
```html
    <form method="post" action="{% url 'scraper' %}" class="space-y-6" onsubmit="return validateForm();">
```

**Step 2: Fix state options loop**

Change lines 26-28 from:
```html
                    {% for state in form_context.state_options %}
                    <option value="{{ state }}">{{ state }}</option>
                    {% endfor %}
```

To:
```html
                    {% for state in state_options %}
                    <option value="{{ state }}">{{ state }}</option>
                    {% endfor %}
```

**Step 3: Fix fields loop**

Change line 32 from:
```html
        {% for field in form_context.fields %}
```

To:
```html
        {% for field in keywords %}
```

**Step 4: Fix field type references**

Change line 35 from:
```html
            {% if field.type == 'range_select' %}
```

To:
```html
            {% if field.data_type == 'range_select' %}
```

**Step 5: Fix field options in range_select**

Change lines 41-43 from:
```html
                    {% for option in field.options %}
                    <option value="{{ option }}">{{ option }}</option>
                    {% endfor %}
```

To:
```html
                    {% for option in field.extra_json.options %}
                    <option value="{{ option }}">{{ option }}</option>
                    {% endfor %}
```

**Step 6: Fix second range_select options (lines 50-52)**

Same change as Step 5.

**Step 7: Fix select type check**

Change line 55 from:
```html
            {% elif field.type == 'select' %}
```

To:
```html
            {% elif field.data_type == 'select' %}
```

**Step 8: Fix select options (lines 60-62)**

Same change as Step 5.

**Step 9: Fix else clause input type**

Change line 65 from:
```html
            <input type="{{ field.type }}" id="{{ field.name }}" name="{{ field.name }}"
```

To:
```html
            <input type="{{ field.data_type }}" id="{{ field.name }}" name="{{ field.name }}"
```

**Step 10: Verify Django check passes**

Run: `python manage.py check`
Expected: "System check identified no issues"

**Step 11: Verify template renders**

Run: `python manage.py runserver`
Visit: http://127.0.0.1:8000/scraper/
Expected: Form renders without errors

**Step 12: Commit**

```bash
git add templates/WebScraper/web-scraper.html
git commit -m "fix: update template to use Keyword model fields"
```

---

### Task 6: Final Integration Verification

**Step 1: Run full Django check**

Run: `python manage.py check`
Expected: "System check identified no issues"

**Step 2: Start server and verify pages**

Run: `python manage.py runserver`

Verify:
1. http://127.0.0.1:8000/scraper/ - Form renders
2. http://127.0.0.1:8000/admin/WebScraper/propertylisting/ - Admin loads (after login)

**Step 3: Final commit**

```bash
git add -A
git commit -m "fix: complete critical bug fixes for end-to-end functionality"
```
