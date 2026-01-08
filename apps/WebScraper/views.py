import json
import logging
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.core.cache import cache
from apps.KeywordSelection.models import Keyword
from celery.result import AsyncResult
from celery import chain, shared_task
from celery_progress.backend import ProgressRecorder
from .tasks.scrape_data import scrape_pinellas_properties, scrape_tax_data
from .tasks.sort_data import generate_excel_report
from .tasks.listings_pdf import generate_pdf_report
from .tasks.visual_data import create_visualizations
from .tasks.email_results import send_results_email

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def start_processing_pipeline(self, search_criteria, limit=10, user_email=None):
    """Start the complete Pinellas County property data pipeline"""
    progress_recorder = ProgressRecorder(self)
    progress_recorder.set_progress(0, 100, description="Starting property data pipeline...")

    # Build the chain: Property data -> Tax data -> Reports
    task_chain = chain(
        scrape_pinellas_properties.s(search_criteria, limit),
        scrape_tax_data.s(),
        generate_excel_report.s(),
        generate_pdf_report.s(),
        create_visualizations.s(),
    )

    # Add email task if recipient provided
    if user_email:
        task_chain |= send_results_email.s(user_email)

    result = task_chain.apply_async()
    return result.id


def web_scraper_view(request):
    """Main view for the property scraper interface"""
    if request.method == 'POST':
        # Get search criteria from the request
        search_criteria = {
            'city': request.POST.get('city'),
            'zip_code': request.POST.get('zip_code'),
            'property_type': request.POST.get('property_type'),
            'min_value': request.POST.get('min_value'),
            'max_value': request.POST.get('max_value'),
        }

        # Remove empty values
        search_criteria = {k: v for k, v in search_criteria.items() if v}

        limit = int(request.POST.get('limit', 10))
        user_email = request.POST.get('email', '')

        # Start the pipeline
        task = start_processing_pipeline.apply_async(
            args=[search_criteria, limit, user_email]
        )

        return redirect('scraping-progress', task_id=task.id)

    # GET request - show the scraping interface
    keywords = Keyword.objects.filter(is_active=True).order_by('-priority')
    context = {
        'keywords': keywords,
        'state_options': ['FL'],  # Pinellas County is in Florida
    }
    return render(request, 'WebScraper/web-scraper.html', context)


def scraping_progress(request, task_id):
    """View to track scraping progress"""
    context = {'task_id': task_id}
    return render(request, 'WebScraper/scraping-progress.html', context)


@csrf_exempt
def get_task_status(request, task_id):
    """API endpoint to get task status"""
    task = AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'current': 0,
            'total': 100,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 100),
            'status': task.info.get('status', '')
        }
        if task.state == 'SUCCESS':
            response['result'] = task.result
    else:
        response = {
            'state': task.state,
            'current': 100,
            'total': 100,
            'status': str(task.info),
        }

    return JsonResponse(response)