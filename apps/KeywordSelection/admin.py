from django.contrib import admin
from .models import Keyword


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ('name', 'data_type', 'help_text_short', 'priority', 'extra_json_display')
    list_filter = ('data_type',)
    search_fields = ('name',)

    def help_text_short(self, obj):
        """Shortens help text to the first 50 characters."""
        return obj.help_text[:50] + '...' if len(obj.help_text) > 50 else obj.help_text

    def extra_json_display(self, obj):
        """Creates a display for the JSON data that avoids trying to decode an already decoded JSON."""
        import json
        if isinstance(obj.extra_json, dict):  # Check if extra_json is already a dict
            # Convert dict to a pretty-printed string to display in the admin
            return json.dumps(obj.extra_json, indent=4, sort_keys=True)
        return "Not a valid JSON"
    extra_json_display.short_description = 'Extra JSON'
