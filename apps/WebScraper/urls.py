from django.urls import path
from . import views

urlpatterns = [
    path("", views.web_scraper_view, name="scraper"),
    path("dashboard/", views.property_dashboard, name="dashboard"),
    path("property/<str:parcel_id>/", views.property_detail, name="property-detail"),
    path("progress/<str:task_id>/", views.scraping_progress, name="scraping-progress"),
    path("status/<str:task_id>/", views.get_task_status, name="task-status"),
]
