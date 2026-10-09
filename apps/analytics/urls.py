from django.urls import path

from . import views

urlpatterns = [
    # Still named 'scraper' so old reverse() calls and bookmarks resolve.
    path('', views.retired_filter_builder, name='scraper'),
    path('dashboard/', views.property_dashboard, name='dashboard'),
    path('property/<str:parcel_id>/', views.property_detail, name='property-detail'),
    path('property/<str:parcel_id>/refresh/', views.property_refresh, name='property-refresh'),
    path('compare/', views.compare_homes, name='compare'),
    path('csrf/', views.csrf_token, name='csrf-token'),
    path('download/excel/', views.download_excel, name='download-excel'),
    path('download/pdf/', views.download_pdf, name='download-pdf'),
]
