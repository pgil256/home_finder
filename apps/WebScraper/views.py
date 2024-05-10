import json
import re
import logging
import time
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.db.models import Q
from apps.KeywordSelection.models import Keyword
from celery.result import AsyncResult
from celery import chain, shared_task
from celery_progress.backend import ProgressRecorder
from .tasks.scrape_data import scrape_website
from .tasks.sort_data import generate_sorted_properties
from .tasks.listings_pdf import generate_listing_pdf
from .tasks.visual_data import analyze_data
from .tasks.email_results import send_results_via_email
from decimal import Decimal, InvalidOperation

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@shared_task(bind=True)
def start_processing_pipeline(self, scrape_config, user_email=None):
    progress_recorder = ProgressRecorder(self)
    progress_recorder.set_progress(
        0, 100, description="Preparing to gather listings..."
    )

    tasks = [
        (scrape_website.s(scrape_config), "Gathering listings...", 25),
        (generate_sorted_properties.s(), "Generating spreadsheet...", 50),
        (generate_listing_pdf.s(), "Generating listing PDF...", 75),
        (analyze_data.s(), "Generating visual data...", 100),
    ]

    chain_tasks = chain(
        *[
            task[0] | update_progress.s(self.request.id, int(task[2]), task[1])
            for task in tasks
        ],
        send_download_links_to_frontend.s(user_email),
        retrieve_and_send_download_links.s(self.request.id),
    )

    result = chain_tasks.apply_async()
    return result.id


@shared_task
def update_progress(task_id, progress, description, result):
    """Update the progress using the task ID."""
    task = AsyncResult(task_id)
    progress_recorder = ProgressRecorder(task)

    try:
        # Ensure progress is a valid numeric value
        current_progress = Decimal(str(progress))
        total = Decimal(100)

        # Update the progress
        progress_recorder.set_progress(current_progress, total, description=description)
    except InvalidOperation as e:
        logger.error(f"InvalidOperation error while converting progress to Decimal: {e}")
        progress_recorder.set_progress(0, Decimal(100), description="Error: Invalid progress value.")
    except TypeError as e:
        logger.error(f"TypeError while updating progress: {e}")
        progress_recorder.set_progress(0, Decimal(100), description="Error: Progress update failed.")

    return result

@shared_task
def send_download_links_to_frontend(result, user_email=None):
    excel_path = settings.EXCEL_PATH
    pdf_path = settings.PDF_PATH

    download_links = {
        "excel": f"https://yourdomain.com/download/{os.path.basename(excel_path)}",
        "pdf": f"https://yourdomain.com/download/{os.path.basename(pdf_path)}",
    }

    logger.info(
        f"Download links generated: Excel: {download_links['excel']}, PDF: {download_links['pdf']}"
    )

    # Store download links (e.g., in a database or cache)
    store_download_links(download_links)
    

    if user_email:
        send_results_via_email.apply_async((user_email, download_links))

    return {"status": "Links sent to frontend", "download_links": download_links}


def store_download_links(links):
    cache.set("download_links", links, timeout=None)


def retrieve_download_links():
    return cache.get("download_links")


def scraping_progress(request, task_id):
    context = {
        "task_id": task_id,
    }

    if request.method == "GET" and "download_links" in request.GET:
        download_links = json.loads(request.GET["download_links"])
        context["download_links"] = download_links

    return render(request, "WebScraper/scraping-progress.html", context)


def web_scraper_view(request):
    logger.debug("Web scraper view accessed")

    ordered_keywords = Keyword.objects.filter(
        Q(priority__gt=0) | Q(name="Location")
    ).order_by("priority")

    keyword_dicts = [
        {
            "name": kw.name,
            "type": kw.data_type,
            "priority": kw.priority,
            "help_text": kw.help_text,
            "extra_json": (
                json.loads(kw.extra_json) if isinstance(kw.extra_json, str) else {}
            ),
        }
        for kw in ordered_keywords
    ]

    location_keywords = [
        kw
        for kw in keyword_dicts
        if kw["name"].lower() == "location"
        and "extra_json" in kw
        and isinstance(kw["extra_json"], dict)
    ]
    if location_keywords and "choices" in location_keywords[0]["extra_json"]:
        state_options = location_keywords[0]["extra_json"]["choices"]
    else:
        state_options = (
            []
        )  # Default to an empty list if no suitable location keyword is found

    form_fields = load_keyword_data(keyword_dicts)

    return render(
        request,
        "WebScraper/web-scraper.html",
        {"form_context": {"fields": form_fields, "state_options": state_options}},
    )


def load_keyword_data(keyword_dicts):
    logger.debug("Loading keyword data for form fields")
    form_fields = []

    for keyword in keyword_dicts:
        if keyword["name"].lower() == "location":
            continue
        if keyword["priority"] <= 0:
            continue
        field_data = create_field_data(keyword)
        if field_data:
            form_fields.append(field_data)

    return form_fields


def create_field_data(keyword):
    logger.debug(f"Creating field data for keyword: {keyword['name']}")
    field_data = {
        "name": keyword.get("name", "Unknown name"),
        "type": keyword.get("type", "text"),
        "help_text": keyword.get("help_text", ""),
        "priority": keyword.get("priority", 0),
    }

    extra_data = keyword.get("extra_json", {})
    if field_data["type"] == "select":
        if "choices" in extra_data:
            field_data["options"] = extra_data["choices"]
        elif "range" in extra_data:
            field_data["options"] = sorted(
                extra_data["range"],
                key=lambda x: float(re.sub(r"[^\d.]+", "", x).strip() or 0),
            )
            field_data["type"] = "range_select"

    return field_data


@csrf_exempt
def submit_form(request):
    logger.debug("Submit form accessed via POST")

    if request.method != "POST":
        logger.warning("Attempt to access submit_form with non-POST method")
        return JsonResponse(
            {"success": False, "error": "HTTP method not allowed"}, status=405
        )

    # Hardcoded form data for debugging
    form_data = {
        "City": "Avoca",
        "State": "PA",
        "Property Type": "House",
        "Listing Price_min": "$100,000",
        "Listing Price_max": "$400,000",
        "Home Size_min": "500 sqft.",
        "Home Size_max": "3500 sqft.",
        "Lot Size_min": "500 sqft.",
        "Lot Size_max": "4500 sqft.",
        "Bedroom Count_min": "0",
        "Bedroom Count_max": "6",
        "Bathroom Count_min": "0",
        "Bathroom Count_max": "6",
        "Garage_min": "1",
        "Garage_max": "3+",
        "Year Built": "2020-present",
        "Time on Market": "10",
        "Monthly Payment_min": "$500",
        "Monthly Payment_max": "$5000+",
        "Stories": "3",
        "Price Per Sqft": "$150/sqft",
        "Monthly Home Insurance": "$400/month",
        "HOA Fees": "$300/month",
        "Mortgage Insurance": "$250/month",
        "Property Taxes": "$700/month",
    }

    logger.info(f"Form data received: {form_data}")

    city = form_data.get("City", "").title().replace(" ", "-")
    state = form_data.get("State", "")
    location = f"{city}_{state}" if city and state else None

    if not location:
        logger.warning("Invalid city and state received")
        return JsonResponse(
            {"success": False, "error": "Invalid city and state"}, status=400
        )

    form_data["Location"] = location
    scrape_config = {
        key: value
        for key, value in form_data.items()
        if key not in ["csrfmiddlewaretoken", "City", "State"]
    }
    logger.debug(f"Scraping configuration: {scrape_config}")

    if not isinstance(scrape_config, dict):
        logger.error(f"Invalid scraping configuration: {scrape_config}")
        return JsonResponse(
            {"success": False, "error": "Invalid scraping configuration"}, status=400
        )

    try:
        task = start_processing_pipeline.apply_async(args=[scrape_config])
        logger.info(f"Task {task.id} initiated")
        return redirect("scraping-progress", task_id=task.id)
    except Exception as e:
        logger.error(f"Error initiating the task: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "Internal server error"}, status=500
        )


@shared_task
def retrieve_and_send_download_links(task_id):
    download_links = retrieve_download_links()
    if download_links:
        # Send the download links to the scraping_progress view
        scraping_progress_url = reverse("scraping-progress", args=[task_id])
        return JsonResponse({"download_links": download_links}, status=200, safe=False)
    else:
        logger.warning("No download links found")
        return None


@csrf_protect
def submit_email(request):
    logger.debug("Email submission endpoint accessed")
    if request.method == "POST":
        email_address = request.POST.get("email", "").strip()
        if not email_address:
            logger.error("Invalid or empty email address received")
            return HttpResponse("Invalid email", status=400)

        task_id = start_processing_pipeline(request.POST.dict(), email_address)
        logger.info(f"Email pipeline task initiated: {task_id}")
        return HttpResponse(f"Task initiated: {task_id}", status=200)
    else:
        logger.error("Invalid HTTP method for email submission")
        return HttpResponse("Invalid request", status=405)
