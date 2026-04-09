from __future__ import annotations

import logging
import time
from typing import Any, Optional

from celery import chain
from celery.result import AsyncResult
from django.core.cache import cache
from django.http import JsonResponse

from ..tasks.scrape_data import scrape_pinellas_properties, scrape_tax_data
from ..tasks.sort_data import generate_sorted_properties
from ..tasks.listings_pdf import generate_listing_pdf
from ..tasks.visual_data import analyze_data
from ..tasks.email_results import send_results_via_email

logger = logging.getLogger(__name__)

SCRAPE_RATE_LIMIT_SECONDS = 60


def build_processing_pipeline(
    search_criteria: dict[str, Any],
    limit: int = 10,
    user_email: Optional[str] = None,
) -> AsyncResult:
    """Build and launch the property data pipeline. Returns the first task's AsyncResult."""
    task_chain = chain(
        scrape_pinellas_properties.s(search_criteria, limit),
        scrape_tax_data.s(),
        generate_sorted_properties.s(),
        generate_listing_pdf.s(),
        analyze_data.s(),
    )

    if user_email:
        task_chain |= send_results_via_email.s(user_email)

    frozen_chain = task_chain.freeze()

    task_ids: list[str] = []
    current = frozen_chain
    while current:
        task_ids.append(current.id)
        current = getattr(current, 'parent', None)
    task_ids.reverse()

    first_task_id = task_ids[0]
    cache.set(f'chain:{first_task_id}', {
        'task_ids': task_ids,
        'total_tasks': len(task_ids),
    }, timeout=3600)

    task_chain.apply_async()
    return AsyncResult(first_task_id)


def get_client_ip(request) -> str:
    """Extract client IP from request, accounting for proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def check_rate_limit(client_ip: str) -> Optional[int]:
    """Check if client is rate-limited. Returns seconds to wait, or None if allowed."""
    rate_key = f'scrape_rate:{client_ip}'
    last_submission = cache.get(rate_key)
    if last_submission:
        wait_seconds = SCRAPE_RATE_LIMIT_SECONDS - (time.time() - last_submission)
        if wait_seconds > 0:
            return int(wait_seconds)
    cache.set(rate_key, time.time(), timeout=SCRAPE_RATE_LIMIT_SECONDS)
    return None


def get_task_status_response(task_id: str) -> JsonResponse:
    """Get task status as a JsonResponse, handling both chain and single tasks."""
    chain_info = cache.get(f'chain:{task_id}')
    if chain_info:
        return _get_chain_status(task_id, chain_info)
    return _get_single_task_status(task_id)


def _get_single_task_status(task_id: str) -> JsonResponse:
    """Get status for a single task."""
    task = AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {'state': task.state, 'current': 0, 'total': 100, 'status': 'Pending...'}
    elif task.state != 'FAILURE':
        info = task.info if isinstance(task.info, dict) else {}
        response = {
            'state': task.state,
            'current': info.get('current', 0),
            'total': info.get('total', 100),
            'status': info.get('status', ''),
        }
        if task.state == 'SUCCESS':
            response['result'] = task.result
    else:
        response = {'state': task.state, 'current': 100, 'total': 100, 'status': str(task.info)}

    return JsonResponse(response)


def _get_chain_status(first_task_id: str, chain_info: dict) -> JsonResponse:
    """Get aggregated status across all tasks in a chain."""
    task_ids = chain_info['task_ids']
    total_tasks = chain_info['total_tasks']

    completed_tasks = 0
    active_task = None
    active_task_index = 0
    last_result = None

    for i, tid in enumerate(task_ids):
        task = AsyncResult(tid)

        if task.state == 'FAILURE':
            return JsonResponse({
                'state': 'FAILURE', 'current': 100, 'total': 100, 'status': str(task.info),
            })
        elif task.state == 'SUCCESS':
            completed_tasks += 1
            last_result = task.result
        elif task.state in ('PENDING', 'STARTED', 'PROGRESS'):
            active_task = task
            active_task_index = i
            break

    if completed_tasks == total_tasks:
        return JsonResponse({
            'state': 'SUCCESS', 'current': 100, 'total': 100,
            'status': 'All tasks completed', 'result': last_result,
        })

    task_weight = 100 / total_tasks
    base_progress = completed_tasks * task_weight
    task_progress = 0
    status = 'Processing...'

    if active_task:
        if active_task.state == 'PENDING':
            status = f'Waiting for task {active_task_index + 1}/{total_tasks}...'
        else:
            info = active_task.info if isinstance(active_task.info, dict) else {}
            task_progress = info.get('current', 0) / 100 * task_weight
            status = info.get('status', f'Running task {active_task_index + 1}/{total_tasks}...')

    return JsonResponse({
        'state': 'PROGRESS',
        'current': int(base_progress + task_progress),
        'total': 100,
        'status': status,
        'step': active_task_index + 1,
        'total_steps': total_tasks,
    })
