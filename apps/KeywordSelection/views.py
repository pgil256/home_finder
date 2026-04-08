from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse
from django.http import JsonResponse
from .models import Keyword
import json
import logging

logger = logging.getLogger(__name__)


def keyword_select_view(request):
    return render(request, 'KeywordSelection/keyword-selection.html')

@require_GET
def get_keywords(request):
    keywords = Keyword.objects.all().order_by('id')
    keyword_list = [keyword.name for keyword in keywords]
    return JsonResponse({'keywords': keyword_list})

@require_POST
def submit_keyword_order(request):
    logger.debug("submit_keyword_order: POST request received.")
    try:
        data = json.loads(request.body)
        ordered_keywords = data.get('ordered_keywords', [])

        if not isinstance(ordered_keywords, list) or not all(isinstance(item, dict) for item in ordered_keywords):
            raise ValueError("Invalid format for ordered_keywords")

        # Reset all priorities to 0
        Keyword.objects.all().update(priority=0)

        # Update priorities for provided keywords
        for keyword_dict in ordered_keywords:
            name = keyword_dict.get('name')
            priority = keyword_dict.get('priority')
            if not (isinstance(name, str) and isinstance(priority, int)):
                raise ValueError("Invalid type for name or priority in ordered_keywords")

            Keyword.objects.update_or_create(
                name=name,
                defaults={'priority': priority}
            )
            logger.debug(f"Updated priority for keyword: {name} -> {priority}")

        logger.info("Keyword order updated successfully.")
        return JsonResponse({'success': True, 'redirect_url': reverse('scraper')})

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in keyword order request: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except ValueError as e:
        logger.warning(f"Validation error in keyword order: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
