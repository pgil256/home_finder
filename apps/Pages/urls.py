from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('robots.txt', views.robots_txt, name='robots-txt'),
    path('about/', views.about, name='about'),
    path('help', views.help, name='help'),
    path('health/', views.health_check, name='health'),
    path('api/status/', views.api_status, name='api-status'),
]
