from django.urls import path
from . import views

urlpatterns = [
    path("scraper/", views.web_scraper_view, name="scraper"),
    path("submit-form/", views.submit_form, name="submit-form"),
    path("scraping-progress/<str:task_id>/", views.scraping_progress, name="scraping-progress"),
    path("submit-email", views.submit_email, name="submit_email"),
]
