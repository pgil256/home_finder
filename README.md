# Pinellas Property Finder

[![CI](https://github.com/pgil256/home_finder/actions/workflows/ci.yml/badge.svg)](https://github.com/pgil256/home_finder/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-092E20?logo=django&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?logo=tailwindcss&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)

A full-stack property data aggregation system for Pinellas County, Florida. Scrapes, consolidates, and visualizes property records from multiple official county sources to help home buyers, agents, and investors find properties.

## Key Features

- **Multi-source data pipeline** -- merges Property Appraiser valuations with Tax Collector records by parcel ID
- **Advanced search** -- filter by city, ZIP, property type, price range, bedrooms, bathrooms, year built
- **Async task processing** -- Celery chains handle scraping, report generation, and email delivery
- **On-demand exports** -- generate styled Excel spreadsheets and PDF reports with market analysis charts
- **Responsive UI** -- mobile-first design with Tailwind CSS, touch gestures, and skeleton loaders

## Architecture

```
                                 +------------------+
   Browser ──> Django Views ──>  |  Celery Chain    |
                  |              |  1. Scrape PCPAO  |
                  |              |  2. Scrape Tax    |
                  |              |  3. Excel Report  |
             Dashboard           |  4. PDF Report    |
             + Filters           |  5. Visualizations|
             + Exports           |  6. Email Results |
                                 +------------------+
                                        |
                              Redis (broker/backend)
                                        |
                                   PostgreSQL
```

**Data Sources:**
| Source | Data | Method |
|--------|------|--------|
| [PCPAO](https://www.pcpao.org/) | Parcel IDs, addresses, valuations, building details | API + Selenium |
| [Tax Collector](https://taxcollect.com/) | Tax amounts, payment status, delinquency | Selenium |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Django 5.0, Django REST Framework |
| Task Queue | Celery 5.3, Redis |
| Database | PostgreSQL (prod), SQLite (dev) |
| Frontend | Tailwind CSS 3.4, Webpack 5, vanilla JS |
| Scraping | Selenium, BeautifulSoup, Requests |
| Reports | OpenPyXL (Excel), ReportLab (PDF), Matplotlib (charts) |
| Deployment | Railway (Docker), Vercel (static) |
| CI/CD | GitHub Actions (lint, test, build) |

## Quick Start

```bash
# Clone and setup
git clone https://github.com/pgil256/home_finder.git
cd home_finder
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env   # Edit with your values

# Database
python3 manage.py migrate
python3 manage.py load_pinellas_data

# Frontend
npm install && npm run build

# Run
python3 manage.py runserver
```

For async scraping, also start Redis and Celery:

```bash
redis-server &
celery -A home_finder worker --loglevel=info
```

## Development

```bash
make help          # Show all available commands
make dev           # Start dev server + frontend watchers
make lint          # Run ruff (Python) + ESLint (JS)
make test          # Run Python tests with coverage
make test-js       # Run JavaScript tests
make check         # Run all checks
```

## Project Structure

```
home_finder/
├── apps/
│   ├── WebScraper/           # Core scraping + data pipeline
│   │   ├── models.py         # PropertyListing model (43+ fields)
│   │   ├── views.py          # Thin views delegating to services
│   │   ├── services/         # Business logic (filtering, exports, tasks)
│   │   └── tasks/            # Celery tasks (scrapers, reports, email)
│   ├── KeywordSelection/     # Search criteria management
│   └── Pages/                # Static pages + health check
├── templates/                # Django templates (Tailwind UI)
├── static/                   # CSS, JS (dev + dist), images
├── home_finder/              # Django project config
├── .github/workflows/        # CI pipeline
├── Makefile                  # Dev commands
└── pyproject.toml            # Ruff, pytest config
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page |
| `/scraper/` | GET/POST | Search form + submit |
| `/scraper/dashboard/` | GET | Property grid with filters |
| `/scraper/property/<id>/` | GET | Property detail page |
| `/scraper/download/excel/` | GET | Export properties as Excel |
| `/scraper/download/pdf/` | GET | Export properties as PDF with charts |
| `/health/` | GET | Health check (DB + cache) |
| `/api/status/` | GET | Property count + last update time |

## Key Technical Decisions

- **Service layer pattern** -- views.py delegates to `services/filtering.py`, `services/exports.py`, and `services/task_management.py` to keep views thin and testable
- **Celery chain** -- tasks are chained so each step's output feeds the next, with per-task progress tracking aggregated into overall chain progress
- **Bulk data import** -- PCPAO CSV import processes 400k+ records in 5,000-row batches to manage memory
- **Compound database indexes** -- optimized for the most common filter combinations (city+type, city+value, type+value)
- **Guest-first access** -- all features including PDF/Excel exports available without login

## License

This project is for educational and demonstration purposes.
