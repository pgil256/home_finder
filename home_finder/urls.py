"""
URL configuration for home_finder project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from apps.analytics import views as analytics_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('insights/', analytics_views.insights_dashboard, name='insights'),
    path('analytics/', include('apps.analytics.urls')),
    # The app was renamed from "WebScraper" to "analytics"; keep the old
    # /scraper/ prefix working as a redirect so existing links and the
    # live-site smoke tests still resolve (sub-path and query string preserved).
    re_path(
        r'^scraper/(?P<rest>.*)$',
        RedirectView.as_view(url='/analytics/%(rest)s', query_string=True),
    ),
    path('', include('apps.Pages.urls')),
]

# Serve media files through Django (needed for dynamically generated reports)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
