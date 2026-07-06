from django.urls import path

from . import views

urlpatterns = [
    path('', views.web_scraper_view, name='scraper'),
    path('dashboard/', views.property_dashboard, name='dashboard'),
    path('property/<str:parcel_id>/', views.property_detail, name='property-detail'),
    path('property/<str:parcel_id>/refresh/', views.property_refresh, name='property-refresh'),
    path('download/excel/', views.download_excel, name='download-excel'),
    path('download/pdf/', views.download_pdf, name='download-pdf'),
]
