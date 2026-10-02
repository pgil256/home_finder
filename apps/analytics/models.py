from django.db import models


class PropertyListing(models.Model):
    # Indexes cost storage on a 512 MiB Neon plan, so only columns that a
    # query can use an index for get one. Filters use city__iexact and
    # property_type__icontains, which a plain B-tree can't serve; the
    # similar-properties lookup (exact city + type, value range) uses
    # idx_city_type_value.

    # Property Appraiser Data
    parcel_id = models.CharField(max_length=50, unique=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10, db_index=True)
    owner_name = models.CharField(max_length=255, null=True, blank=True)

    # Valuation Data
    market_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, db_index=True)
    assessed_value = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    # Building Information
    building_sqft = models.IntegerField(null=True)
    year_built = models.IntegerField(null=True, db_index=True)
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

    # Tax inputs (PCPAO RP_PROPERTY_INFO)
    roll_year = models.IntegerField(null=True)
    tax_district = models.CharField(max_length=8, null=True, blank=True)
    millage_rate = models.DecimalField(max_digits=7, decimal_places=4, null=True)
    special_assessment = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    homestead_cap = models.BooleanField(null=True)  # Save Our Homes cap applies (owner has homestead)
    sales_comp_value = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    # Location and risk (PCPAO RP_PROPERTY_INFO)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    evac_zone = models.CharField(max_length=4, null=True, blank=True)  # A-E, or NONE
    neighborhood_code = models.CharField(max_length=16, null=True, blank=True)
    frontage = models.CharField(max_length=32, null=True, blank=True)
    views = models.CharField(max_length=32, null=True, blank=True)
    waterfront = models.BooleanField(null=True)
    seawall = models.BooleanField(null=True)
    subsidence = models.BooleanField(null=True)
    contamination = models.BooleanField(null=True)
    historic_landmark = models.BooleanField(null=True)
    living_units = models.IntegerField(null=True)

    # Metadata
    last_scraped = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # URLs for reference
    appraiser_url = models.URLField(null=True, blank=True)
    tax_collector_url = models.URLField(null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    class Meta:
        indexes = [
            # Similar properties on the detail page: exact city + type, value range.
            models.Index(fields=['city', 'property_type', 'market_value'], name='idx_city_type_value'),
        ]

    def __str__(self):
        return f'{self.parcel_id} - {self.address}'

    @property
    def price_per_sqft(self):
        if self.market_value and self.building_sqft and self.building_sqft > 0:
            return self.market_value / self.building_sqft
        return None
