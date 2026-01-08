from django.db import models
from django.db.models import JSONField  

class Keyword(models.Model):
    name = models.CharField(max_length=255, unique=True)
    data_type = models.CharField(max_length=50, default='text')
    help_text = models.TextField(blank=True)
    priority = models.IntegerField(default=0)  # Default priority set to 0
    is_active = models.BooleanField(default=True)
    extra_json = JSONField(blank=True, default=dict)  # Uses the standard JSONField
    listing_field = models.CharField(max_length=255, blank=True, null=True)  # Corresponding field in PropertyListing

    def __str__(self):
        return f"{self.name} ({self.priority})"
