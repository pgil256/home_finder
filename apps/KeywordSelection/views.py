from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.http import JsonResponse
from .models import Keyword
import json


def keyword_select_view(request):
    return render(request, 'KeywordSelection/keyword-selection.html')

def get_keywords(request):
    keywords = Keyword.objects.all().order_by('id')
    keyword_list = [keyword.name for keyword in keywords]
    return JsonResponse({'keywords': keyword_list})

@csrf_exempt
def submit_keyword_order(request):
    print("submit_keyword_order: POST request received.")
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            print("Data:", data)
            ordered_keywords = data.get('ordered_keywords', [])
            print("Ordered keywords:", ordered_keywords)

            if not isinstance(ordered_keywords, list) or not all(isinstance(item, dict) for item in ordered_keywords):
                raise ValueError("Invalid format for ordered_keywords")

            # Reset all priorities to 0
            Keyword.objects.all().update(priority=0)
            print("All keyword priorities have been reset to 0.")

            # Update priorities for provided keywords
            for keyword_dict in ordered_keywords:
                name = keyword_dict.get('name')
                priority = keyword_dict.get('priority')
                if not (isinstance(name, str) and isinstance(priority, int)):
                    raise ValueError("Invalid type for name or priority in ordered_keywords")

                print("Updating priority for keyword:", name, "with priority:", priority)
                keyword, created = Keyword.objects.update_or_create(
                    name=name,
                    defaults={'priority': priority}
                )
                if created:
                    print(f"Keyword '{name}' was created with priority {priority}.")
                else:
                    print("Priority updated for keyword:", name)

            print("Request processed successfully.")
            return JsonResponse({'success': True, 'redirect_url': reverse('scraper')})

        except json.JSONDecodeError as e:
            print("JSONDecodeError:", e)
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        except ValueError as e:
            print("ValueError:", e)
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    else:
        print("Invalid request method.")
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=405)
