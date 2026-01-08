# Home Finder Development Session Notes

**Last Updated:** January 8, 2026

---

## Session 1: Bug Fixes (January 7, 2026)

Fixed 14+ critical bugs preventing the pipeline from running end-to-end.

### Changes Made

1. **Duplicate Middleware Removed** - `home_finder/settings.py`
2. **Admin Field References Fixed** - `apps/WebScraper/admin.py`
3. **Broken URL Patterns Removed** - `apps/WebScraper/urls.py`
4. **View Context Fixed** - `apps/WebScraper/views.py`
5. **Template Variables Fixed** - `templates/WebScraper/web-scraper.html`
6. **Task Chain Data Flow Fixed** - All task files updated to pass data correctly
7. **Celery Configured for Testing** - In-memory broker for development
8. **Database Migrations Recreated**

---

## Session 2: Production Setup (January 8, 2026)

Completed all production configuration and tested end-to-end pipeline.

### Changes Made

#### 1. Visualization Fixes (`apps/WebScraper/tasks/visual_data.py`)
- Added `COLUMN_MAPPING` to translate model fields to display names
- Added calculated columns: `Price Per Sqft`, `Estimated Monthly Payment`
- Made plots resilient to missing columns with `has_columns()` helper
- Changed Plot 5 from "Time on Market" to "Year Built vs. Listing Price"
- Fixed deprecated PyPDF2: `PdfFileMerger` → `PdfMerger`, `PdfFileReader` → `PdfReader`

#### 2. Redis Configuration (`home_finder/settings.py`, `.env`)
- Updated Celery settings to use environment variables
- Added Redis broker/backend URLs to `.env`
- Set `CELERY_TASK_ALWAYS_EAGER=False` for async execution

#### 3. Chrome for Testing Setup
- Downloaded Chrome for Testing v143 to `~/.chrome-for-testing/`
- Updated both scrapers to use Chrome for Testing binary
- Added Service configuration with custom ChromeDriver path

### Files Modified
```
apps/WebScraper/tasks/visual_data.py
apps/WebScraper/tasks/pcpao_scraper.py
apps/WebScraper/tasks/tax_collector_scraper.py
home_finder/settings.py
.env
docs/SESSION_NOTES.md
```

### Commits
```
71a3481 fix: visualization column mapping and PyPDF2 deprecation
0a8eef4 feat: configure Celery to use Redis for production
9bad6fc feat: configure scrapers to use Chrome for Testing
```

---

## Current Status

### Working Components

| Component | Status | Notes |
|-----------|--------|-------|
| Django App | ✅ Working | Runs on `python manage.py runserver` |
| Database | ✅ Working | SQLite with migrations applied |
| Task Chain | ✅ Working | All 6 tasks execute successfully |
| Excel Generation | ✅ Working | Creates PropertyListings.xlsx |
| PDF Generation | ✅ Working | Creates listing reports |
| Visualizations | ✅ Working | 8 charts in Data_Analysis.pdf |
| PDF Concatenation | ✅ Working | Merges reports correctly |
| Redis | ✅ Running | `redis-server` on localhost:6379 |
| Chrome for Testing | ✅ Installed | v143 in ~/.chrome-for-testing/ |
| Selenium Scrapers | ✅ Configured | Both scrapers use Chrome for Testing |

### Pending Configuration

| Component | Status | Action Required |
|-----------|--------|-----------------|
| Email Sending | ⚠️ Needs Config | Generate Gmail App Password |
| Actual Scraping | ⚠️ Untested | Test against live PCPAO/Tax sites |

---

## How to Run

### Development Mode (Testing)

```bash
# Single terminal - tasks run synchronously
cd ~/projects/home_finder
source venv/bin/activate  # or: venv/bin/activate on some systems
python manage.py runserver
```

### Production Mode (Async Tasks)

```bash
# Terminal 1: Start Redis
sudo service redis-server start

# Terminal 2: Start Celery Worker
cd ~/projects/home_finder
venv/bin/python -m celery -A home_finder worker --loglevel=info

# Terminal 3: Start Django
cd ~/projects/home_finder
venv/bin/python manage.py runserver
```

### Access the App
- Web Scraper Form: http://127.0.0.1:8000/scraper/
- Admin Panel: http://127.0.0.1:8000/admin/

---

## What To Do Next

### 1. Enable Email Notifications (Optional)

Gmail requires an App Password for SMTP access:

1. Enable 2-Step Verification on Google Account
2. Go to: https://myaccount.google.com/apppasswords
3. Generate an App Password for "Mail"
4. Update `.env`:
   ```
   EMAIL_HOST_PASSWORD='xxxx xxxx xxxx xxxx'
   ```

### 2. Test Live Scraping

The scrapers are configured but haven't been tested against live sites:

```bash
venv/bin/python << 'EOF'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'home_finder.settings')
django.setup()

from apps.WebScraper.tasks.pcpao_scraper import PCPAOScraper

scraper = PCPAOScraper(headless=True)
scraper.setup_driver()

# Test search (may need to adjust for current site structure)
results = scraper.search_properties({'city': 'Clearwater'})
print(f"Found {len(results)} properties")

scraper.close_driver()
EOF
```

### 3. Potential Enhancements

- **Error Handling**: Add retry logic for network failures
- **Rate Limiting**: Respect source site rate limits
- **Caching**: Cache scraped data to avoid redundant requests
- **Progress UI**: Verify celery-progress updates work in frontend
- **Data Validation**: Validate scraped data before saving
- **Logging**: Add structured logging for production debugging

### 4. Deployment Considerations

For server deployment:
- Use gunicorn instead of Django dev server
- Configure nginx as reverse proxy
- Set up systemd services for Redis/Celery
- Use environment variables for all secrets
- Enable HTTPS

---

## File Structure Reference

```
home_finder/
├── apps/
│   ├── KeywordSelection/     # Search criteria management
│   ├── Pages/                # Dashboard views
│   └── WebScraper/
│       ├── tasks/
│       │   ├── scrape_data.py         # Celery task orchestration
│       │   ├── pcpao_scraper.py       # Property Appraiser scraper
│       │   ├── tax_collector_scraper.py # Tax Collector scraper
│       │   ├── sort_data.py           # Excel generation
│       │   ├── listings_pdf.py        # PDF generation
│       │   ├── visual_data.py         # Charts & visualization
│       │   └── email_results.py       # Email notifications
│       ├── models.py          # PropertyListing model
│       ├── views.py           # Form handling & pipeline
│       └── urls.py            # URL routing
├── home_finder/
│   ├── settings.py            # Django & Celery config
│   └── celery.py              # Celery app setup
├── templates/
│   └── WebScraper/
│       └── web-scraper.html   # Search form template
├── .env                       # Environment variables
├── requirements.txt           # Python dependencies
└── docs/
    └── SESSION_NOTES.md       # This file
```

---

## Troubleshooting

### Port Already in Use
```bash
# Find and kill process on port 8000
lsof -i :8000
kill -9 <PID>
```

### Redis Connection Failed
```bash
# Check if Redis is running
redis-cli ping  # Should return PONG

# Start Redis
sudo service redis-server start
```

### Chrome/Selenium Errors
```bash
# Verify Chrome for Testing is installed
~/.chrome-for-testing/chrome-linux64/chrome --version

# Test headless mode
~/.chrome-for-testing/chrome-linux64/chrome --headless --no-sandbox --dump-dom https://google.com
```

### Celery Tasks Not Running
```bash
# Check if worker is connected
venv/bin/python -m celery -A home_finder inspect active

# Check Redis has tasks
redis-cli LLEN celery
```
