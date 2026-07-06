from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.analytics'
    # Keep the original 'WebScraper' app label so existing migrations,
    # database tables (WebScraper_propertylisting), and content types stay
    # intact — renaming the Python package needs no schema migration.
    label = 'WebScraper'
