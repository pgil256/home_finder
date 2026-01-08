from django.urls import path
from . import views

urlpatterns = [
    path("scraper/", views.web_scraper_view, name="scraper"),
    path("scraping-progress/<str:task_id>/", views.scraping_progress, name="scraping-progress"),
    path("task-status/<str:task_id>/", views.get_task_status, name="task-status"),
]
