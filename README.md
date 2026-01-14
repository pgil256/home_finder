# Pinellas Property Finder - County Property Data Aggregator

A Django-based web application that aggregates property data from Pinellas County official sources to help home buyers, real estate agents, and investors find properties.

## Features

- **Dual-Source Data Collection**: Combines data from Property Appraiser and Tax Collector
- **Advanced Search**: Filter by city, ZIP code, property type, and value range
- **Consolidated Records**: Merges property details with tax information
- **Async Processing**: Handles large datasets with Celery task queue
- **Export Options**: Generate reports in Excel and PDF formats

## Data Sources

1. **Pinellas County Property Appraiser (PCPAO)**
   - Property details, valuations, building information
   - URL: https://www.pcpao.org/

2. **Pinellas County Tax Collector**
   - Tax amounts, payment status, delinquency information
   - URL: https://taxcollect.com/

## Setup

### Prerequisites

- Python 3.12+
- Redis server (for Celery)
- Chrome browser (for Selenium)

### Installation

1. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables in `.env`:
```
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
EXCEL_PATH=/path/to/excel/output
PDF_PATH=/path/to/pdf/output
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Load Pinellas County data:
```bash
python manage.py load_pinellas_data
```

## Usage

### Start the services:

1. Redis server:
```bash
redis-server
```

2. Celery worker:
```bash
celery -A home_finder worker --loglevel=info
```

3. Django development server:
```bash
python manage.py runserver
```

Access the application at http://localhost:8000

## Project Structure

```
home_finder/
├── apps/
│   ├── WebScraper/         # Main scraping app
│   │   ├── tasks/
│   │   │   ├── pcpao_scraper.py      # Property Appraiser scraper
│   │   │   ├── tax_collector_scraper.py  # Tax Collector scraper
│   │   │   └── scrape_data.py        # Main scraping orchestration
│   │   └── models.py       # PropertyListing model
│   └── KeywordSelection/   # Search criteria management
├── requirements.txt        # Python dependencies
└── manage.py              # Django management script
```

## License

This project is for educational and demonstration purposes.