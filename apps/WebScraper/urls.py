from django.urls import path
from . import views

urlpatterns = [
    path("", views.web_scraper_view, name="scraper"),
    path("progress/<str:task_id>/", views.scraping_progress, name="scraping-progress"),
    path("status/<str:task_id>/", views.get_task_status, name="task-status"),
]
