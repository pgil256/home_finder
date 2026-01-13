import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q
from apps.KeywordSelection.models import Keyword
from celery.result import AsyncResult
from celery import chain
from .models import PropertyListing
from .tasks.scrape_data import scrape_pinellas_properties, scrape_tax_data
from .tasks.sort_data import generate_sorted_properties
from .tasks.listings_pdf import generate_listing_pdf
from .tasks.visual_data import analyze_data
from .tasks.email_results import send_results_via_email

logger = logging.getLogger(__name__)

# Common data for views
PINELLAS_CITIES = [
    'Clearwater', 'St. Petersburg', 'Largo', 'Pinellas Park', 'Dunedin',
    'Palm Harbor', 'Tarpon Springs', 'Seminole', 'Safety Harbor', 'Oldsmar',
    'Gulfport', 'St. Pete Beach', 'Treasure Island', 'Madeira Beach',
    'Indian Rocks Beach', 'Belleair', 'Kenneth City', 'South Pasadena',
    'Indian Shores', 'Redington Beach'
]

PROPERTY_TYPES = [
    'Single Family', 'Condo', 'Townhouse', 'Multi-Family',
    'Vacant Land', 'Mobile Home', 'Commercial'
]


def build_processing_pipeline(search_criteria, limit=10, user_email=None):
    """Build and launch the complete Pinellas County property data pipeline.
    Returns the AsyncResult for the first task to enable progress tracking.
    """
    # Build the chain: Property data -> Tax data -> Reports
    task_chain = chain(
        scrape_pinellas_properties.s(search_criteria, limit),
        scrape_tax_data.s(),
        generate_sorted_properties.s(),
        generate_listing_pdf.s(),
        analyze_data.s(),
    )

    # Add email task if recipient provided
    if user_email:
        task_chain |= send_results_via_email.s(user_email)

    # Freeze the chain to assign task IDs before applying
    # This works in production (parent chain not available until execution)
    frozen_chain = task_chain.freeze()

    # Collect task IDs by traversing the frozen chain
    task_ids = []
    current = frozen_chain
    while current:
        task_ids.append(current.id)
        # For chains, the next task is in .parent (reverse order)
        current = getattr(current, 'parent', None)

    # Reverse so first task is at index 0
    task_ids.reverse()

    # Store chain info in cache BEFORE applying
    first_task_id = task_ids[0]
    cache.set(f'chain:{first_task_id}', {
        'task_ids': task_ids,
        'total_tasks': len(task_ids),
    }, timeout=3600)  # 1 hour TTL

    # Now apply the frozen chain
    task_chain.apply_async()

    return AsyncResult(first_task_id)


def web_scraper_view(request):
    """Main view for the property scraper interface"""
    if request.method == 'POST':
        # Get search criteria from the new unified search form
        property_types = request.POST.getlist('property_type')

        search_criteria = {
            'city': request.POST.get('city'),
            'zip_code': request.POST.get('zip_code'),
            'property_type': property_types[0] if len(property_types) == 1 else property_types if property_types else None,
            'min_value': request.POST.get('min_value'),
            'max_value': request.POST.get('max_value'),
            'bedrooms_min': request.POST.get('bedrooms_min'),
            'bathrooms_min': request.POST.get('bathrooms_min'),
            'year_built_after': request.POST.get('year_built_after'),
            'tax_status': request.POST.get('tax_status'),
            'sqft_min': request.POST.get('sqft_min'),
            'sqft_max': request.POST.get('sqft_max'),
        }

        # Remove empty values
        search_criteria = {k: v for k, v in search_criteria.items() if v}

        limit = int(request.POST.get('limit', 50))
        user_email = request.POST.get('email', '')

        # Start the pipeline - track the chain's first task for progress
        result = build_processing_pipeline(search_criteria, limit, user_email)

        return redirect('scraping-progress', task_id=result.id)

    # GET request - show the unified search interface
    context = {
        'cities': sorted(PINELLAS_CITIES),
        'property_types': PROPERTY_TYPES,
    }
    return render(request, 'WebScraper/search.html', context)


def scraping_progress(request, task_id):
    """View to track scraping progress"""
    context = {'task_id': task_id}
    return render(request, 'WebScraper/scraping-progress.html', context)


@csrf_exempt
def get_task_status(request, task_id):
    """API endpoint to get task status with chain progress aggregation."""
    # Check if this is part of a chain
    chain_info = cache.get(f'chain:{task_id}')

    if chain_info:
        return _get_chain_status(task_id, chain_info)

    # Single task progress (fallback)
    return _get_single_task_status(task_id)


def _get_single_task_status(task_id):
    """Get status for a single task."""
    task = AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'current': 0,
            'total': 100,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        info = task.info if isinstance(task.info, dict) else {}
        response = {
            'state': task.state,
            'current': info.get('current', 0),
            'total': info.get('total', 100),
            'status': info.get('status', '')
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


def _get_chain_status(first_task_id, chain_info):
    """Get aggregated status across all tasks in a chain."""
    task_ids = chain_info['task_ids']
    total_tasks = chain_info['total_tasks']

    # Find the currently active task and calculate overall progress
    completed_tasks = 0
    active_task = None
    active_task_index = 0
    last_result = None
    failed = False
    failure_info = None

    for i, tid in enumerate(task_ids):
        task = AsyncResult(tid)

        if task.state == 'FAILURE':
            failed = True
            failure_info = str(task.info)
            break
        elif task.state == 'SUCCESS':
            completed_tasks += 1
            last_result = task.result
        elif task.state in ('PENDING', 'STARTED', 'PROGRESS'):
            active_task = task
            active_task_index = i
            break

    if failed:
        return JsonResponse({
            'state': 'FAILURE',
            'current': 100,
            'total': 100,
            'status': failure_info,
        })

    # All tasks completed
    if completed_tasks == total_tasks:
        return JsonResponse({
            'state': 'SUCCESS',
            'current': 100,
            'total': 100,
            'status': 'All tasks completed',
            'result': last_result,
        })

    # Calculate overall progress
    # Each task contributes equally to total progress
    task_weight = 100 / total_tasks
    base_progress = completed_tasks * task_weight

    # Add progress from the active task
    task_progress = 0
    status = 'Processing...'

    if active_task:
        if active_task.state == 'PENDING':
            status = f'Waiting for task {active_task_index + 1}/{total_tasks}...'
        else:
            info = active_task.info if isinstance(active_task.info, dict) else {}
            task_progress = info.get('current', 0) / 100 * task_weight
            status = info.get('status', f'Running task {active_task_index + 1}/{total_tasks}...')

    overall_progress = int(base_progress + task_progress)

    return JsonResponse({
        'state': 'PROGRESS',
        'current': overall_progress,
        'total': 100,
        'status': status,
        'step': active_task_index + 1,
        'total_steps': total_tasks,
    })


def property_dashboard(request):
    """Property dashboard with filtering, sorting, and pagination"""
    # Start with all properties
    properties = PropertyListing.objects.all()

    # Get filter parameters
    city = request.GET.get('city')
    property_types_filter = request.GET.getlist('property_type')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    beds = request.GET.get('beds')
    baths = request.GET.get('baths')
    year_built = request.GET.get('year_built')
    tax_status = request.GET.get('tax_status')
    sort = request.GET.get('sort', '-market_value')

    # Apply filters
    if city:
        properties = properties.filter(city__iexact=city)

    if property_types_filter:
        properties = properties.filter(property_type__in=property_types_filter)

    if min_price:
        try:
            properties = properties.filter(market_value__gte=float(min_price))
        except ValueError:
            pass

    if max_price:
        try:
            properties = properties.filter(market_value__lte=float(max_price))
        except ValueError:
            pass

    if beds and beds != '0':
        try:
            properties = properties.filter(bedrooms__gte=int(beds))
        except ValueError:
            pass

    if baths and baths != '0':
        try:
            properties = properties.filter(bathrooms__gte=float(baths))
        except ValueError:
            pass

    if year_built:
        try:
            properties = properties.filter(year_built__gte=int(year_built))
        except ValueError:
            pass

    if tax_status:
        properties = properties.filter(tax_status=tax_status)

    # Apply sorting
    valid_sort_fields = [
        'market_value', '-market_value',
        'created_at', '-created_at',
        'building_sqft', '-building_sqft',
        'year_built', '-year_built'
    ]
    if sort in valid_sort_fields:
        properties = properties.order_by(sort)
    else:
        properties = properties.order_by('-market_value')

    # Get total count before pagination
    total_count = properties.count()

    # Paginate
    paginator = Paginator(properties, 12)  # 12 properties per page
    page_number = request.GET.get('page', 1)
    properties_page = paginator.get_page(page_number)

    # Build search criteria summary
    search_criteria = {}
    if city:
        search_criteria['city'] = city
    if property_types_filter:
        search_criteria['property_types'] = property_types_filter

    context = {
        'properties': properties_page,
        'total_count': total_count,
        'cities': sorted(PINELLAS_CITIES),
        'property_types': PROPERTY_TYPES,
        'selected_property_types': property_types_filter,
        'search_criteria': search_criteria,
        'sort': sort,
    }
    return render(request, 'WebScraper/dashboard.html', context)


def property_detail(request, parcel_id):
    """Single property detail view"""
    property_obj = get_object_or_404(PropertyListing, parcel_id=parcel_id)

    # Get similar properties (same city, similar price range)
    similar_properties = PropertyListing.objects.filter(
        city=property_obj.city,
        property_type=property_obj.property_type
    ).exclude(parcel_id=parcel_id)

    if property_obj.market_value:
        min_price = float(property_obj.market_value) * 0.8
        max_price = float(property_obj.market_value) * 1.2
        similar_properties = similar_properties.filter(
            market_value__gte=min_price,
            market_value__lte=max_price
        )

    similar_properties = similar_properties[:4]

    context = {
        'property': property_obj,
        'similar_properties': similar_properties,
    }
    return render(request, 'WebScraper/property-detail.html', context)