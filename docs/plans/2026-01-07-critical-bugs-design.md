# Critical Bug Fixes Design

## Goal

Fix 7 critical bugs preventing the Home Finder app from functioning end-to-end.

## Issues and Fixes

### 1. Missing Celery Configuration

**File:** `home_finder/settings.py`

**Problem:** No Celery broker or result backend configured.

**Fix:** Add configuration:
```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
```

### 2. Duplicate Middleware

**File:** `home_finder/settings.py`

**Problem:** SessionMiddleware appears twice in MIDDLEWARE list.

**Fix:** Remove the duplicate entry.

### 3. Admin Field Mismatches

**File:** `apps/WebScraper/admin.py`

**Problem:** PropertyListingAdmin references non-existent fields: `price`, `home_size`, `lot_size`, `time_on_market`.

**Fix:** Update to use actual model fields:
```python
list_display = ['parcel_id', 'address', 'market_value', 'building_sqft', 'land_size', 'last_scraped']
list_filter = ['tax_status', 'delinquent', 'last_scraped']
search_fields = ['parcel_id', 'address', 'owner_name']
```

### 4. Missing View Functions in URLs

**File:** `apps/WebScraper/urls.py`

**Problem:** Routes reference `submit_form` and `submit_email` views that don't exist.

**Fix:** Remove the unused URL patterns:
```python
urlpatterns = [
    path('', views.web_scraper_view, name='web-scraper'),
    path('progress/', views.scraping_progress, name='scraping-progress'),
    path('task-status/', views.get_task_status, name='task-status'),
]
```

### 5. Template Property Mismatches

**File:** `templates/WebScraper/web-scraper.html`

**Problem:** Template expects `form_context.fields` with `.type` and `.options`, but Keyword model has `data_type` and `extra_json`.

**Fix:** Update template to use Keyword model properties:
- Change `field.type` to `field.data_type`
- Change `field.options` to `field.extra_json.options`
- Change form action from `{% url 'submit-form' %}` to `{% url 'web-scraper' %}`
- Change loop from `form_context.fields` to `keywords`

### 6. View Context

**File:** `apps/WebScraper/views.py`

**Problem:** View doesn't provide expected context variables.

**Fix:** Update view to pass correct context:
```python
def web_scraper_view(request):
    keywords = Keyword.objects.filter(is_active=True).order_by('priority')
    context = {
        'keywords': keywords,
        'state_options': ['FL'],
    }
    # ... POST handling ...
    return render(request, 'WebScraper/web-scraper.html', context)
```

### 7. Celery Task Signature Mismatch

**Files:** `apps/WebScraper/views.py`, `apps/WebScraper/tasks/email_results.py`

**Problem:** `send_results_via_email(email, pdf_path, excel_path)` but chain calls it as `send_results_email.s(user_email)`.

**Fix:** Ensure task chain passes file paths correctly:
- Each task in chain must return data needed by next task
- `create_visualizations` should return `(pdf_path, excel_path)`
- Email task signature should accept chained results

## Order of Implementation

1. Settings (Celery config, duplicate middleware)
2. Admin panel (field references)
3. URLs (remove unused routes)
4. Template (property names, form action)
5. Views (context structure)
6. Task signatures (chain data flow)

## Verification

After each fix:
1. `python manage.py check` - Django system check
2. `python manage.py runserver` - No startup errors

Full integration test:
1. Access `/web-scraper/` - Form renders correctly
2. Access `/admin/WebScraper/propertylisting/` - Admin works
3. Submit form - Pipeline triggers without errors
