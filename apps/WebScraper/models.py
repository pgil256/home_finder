from django.db import models

class PropertyListing(models.Model):
    # Property Appraiser Data
    parcel_id = models.CharField(max_length=50, unique=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10)
    owner_name = models.CharField(max_length=255, null=True, blank=True)

    # Valuation Data
    market_value = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    assessed_value = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    # Building Information
    building_sqft = models.IntegerField(null=True)
    year_built = models.IntegerField(null=True)
    bedrooms = models.IntegerField(null=True)
    bathrooms = models.DecimalField(max_digits=4, decimal_places=2, null=True)
    stories = models.IntegerField(null=True)
    property_type = models.CharField(max_length=100)
    garage = models.CharField(max_length=50, null=True, blank=True)

    # Land Information
    land_size = models.DecimalField(max_digits=10, decimal_places=4, null=True)  # in acres
    lot_sqft = models.IntegerField(null=True)  # in square feet

    # Tax Collector Data
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    tax_status = models.CharField(max_length=50, default='Unknown')  # Paid, Unpaid, Delinquent
    delinquent = models.BooleanField(default=False)
    tax_year = models.IntegerField(null=True)

    # Metadata
    last_scraped = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # URLs for reference
    appraiser_url = models.URLField(null=True, blank=True)
    tax_collector_url = models.URLField(null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.parcel_id} - {self.address}"

    @property
    def price_per_sqft(self):
        if self.market_value and self.building_sqft and self.building_sqft > 0:
            return self.market_value / self.building_sqft
        return None
