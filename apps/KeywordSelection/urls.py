from django.urls import path
from . import views

urlpatterns = [
    path('keyword-selection', views.keyword_select_view, name='keyword-selection'),
    path('get-keywords/', views.get_keywords, name='get-keywords'),
    path('submit-keyword-order/', views.submit_keyword_order, name='submit-keyword-order'),
]
