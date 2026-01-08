# Fix Broken Pieces Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix broken references in URLs, admin, and models so the application can run without errors.

**Architecture:** Three targeted fixes - add missing view stubs, correct admin configuration to match actual model fields, and add missing `is_active` field to Keyword model with migration.

**Tech Stack:** Django 5.0.4, Python 3.12, SQLite3

---

## Task 1: Add `is_active` Field to Keyword Model

The view filters by `is_active=True` but the field doesn't exist on the Keyword model.

**Files:**
- Modify: `apps/KeywordSelection/models.py:4-13`
- Create: Migration file (auto-generated)

**Step 1: Add `is_active` field to Keyword model**

In `apps/KeywordSelection/models.py`, add the field after line 8 (after `priority`):

```python
class Keyword(models.Model):
    name = models.CharField(max_length=255, unique=True)
    data_type = models.CharField(max_length=50, default='text')
    help_text = models.TextField(blank=True)
    priority = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)  # ADD THIS LINE
    extra_json = JSONField(blank=True, default=dict)
    listing_field = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.priority})"
```

**Step 2: Generate migration**

Run: `source venv/Scripts/activate && python3 manage.py makemigrations KeywordSelection`

Expected output: `Migrations for 'KeywordSelection': ... - Add field is_active to keyword`

**Step 3: Apply migration**

Run: `python3 manage.py migrate`

Expected output: `Applying KeywordSelection.000X_... OK`

**Step 4: Commit**

```bash
git add apps/KeywordSelection/models.py apps/KeywordSelection/migrations/
git commit -m "Add is_active field to Keyword model"
```

---

## Task 2: Fix PropertyListingAdmin Field References

The admin references fields that don't exist: `price`, `home_size`, `lot_size`, `description`, `time_on_market`.

**Files:**
- Modify: `apps/WebScraper/admin.py:1-23`

**Step 1: Replace admin.py with corrected version**

Replace entire contents of `apps/WebScraper/admin.py`:

```python
from django.contrib import admin
from .models import PropertyListing


class PropertyListingAdmin(admin.ModelAdmin):
    list_display = (
        'parcel_id', 'address', 'city', 'market_value', 'bedrooms', 'bathrooms',
        'building_sqft', 'property_type', 'year_built', 'tax_status'
    )

    list_filter = ('city', 'property_type', 'bedrooms', 'bathrooms', 'tax_status', 'delinquent')

    search_fields = ('parcel_id', 'address', 'owner_name', 'city')

    list_per_page = 25

    readonly_fields = ('last_scraped', 'created_at')


admin.site.register(PropertyListing, PropertyListingAdmin)
```

**Step 2: Verify admin loads**

Run: `python3 manage.py check`

Expected output: `System check identified no issues (0 silenced).`

**Step 3: Commit**

```bash
git add apps/WebScraper/admin.py
git commit -m "Fix PropertyListingAdmin to use actual model fields"
```

---

## Task 3: Add Missing View Functions

URLs reference `submit_form` and `submit_email` but they don't exist.

**Files:**
- Modify: `apps/WebScraper/views.py:109` (append to end)

**Step 1: Add missing view functions**

Append to `apps/WebScraper/views.py`:

```python


@csrf_exempt
def submit_form(request):
    """Handle form submission for property search"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    search_criteria = {
        'city': request.POST.get('city'),
        'zip_code': request.POST.get('zip_code'),
        'property_type': request.POST.get('property_type'),
        'min_value': request.POST.get('min_value'),
        'max_value': request.POST.get('max_value'),
    }
    search_criteria = {k: v for k, v in search_criteria.items() if v}

    limit = int(request.POST.get('limit', 10))
    user_email = request.POST.get('email', '')

    task = start_processing_pipeline.apply_async(
        args=[search_criteria, limit, user_email]
    )

    return JsonResponse({'task_id': task.id, 'status': 'started'})


@csrf_exempt
def submit_email(request):
    """Handle email submission for receiving results"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    email = request.POST.get('email')
    task_id = request.POST.get('task_id')

    if not email:
        return JsonResponse({'error': 'Email required'}, status=400)

    # Store email association with task (could use cache or session)
    cache.set(f'task_email_{task_id}', email, timeout=3600)

    return JsonResponse({'status': 'Email registered', 'email': email})
```

**Step 2: Verify no syntax errors**

Run: `python3 -c "from apps.WebScraper import views; print('OK')"`

Expected output: `OK`

**Step 3: Commit**

```bash
git add apps/WebScraper/views.py
git commit -m "Add missing submit_form and submit_email views"
```

---

## Task 4: Verify Application Starts

**Step 1: Run Django system check**

Run: `python3 manage.py check`

Expected output: `System check identified no issues (0 silenced).`

**Step 2: Test runserver starts**

Run: `python3 manage.py runserver --noreload &` then `sleep 3 && curl -s http://127.0.0.1:8000/ | head -20`

Expected: HTML response (or redirect) without errors.

Kill server after test.

**Step 3: Final commit if any cleanup needed**

```bash
git status
# If clean, done. If changes, commit them.
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add `is_active` to Keyword model | models.py + migration |
| 2 | Fix admin field references | admin.py |
| 3 | Add missing view functions | views.py |
| 4 | Verify app starts | N/A |
