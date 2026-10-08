from django.db import models


class PropertyListing(models.Model):
    # Indexes cost storage on a 512 MiB Neon plan, so only columns that a
    # query can use an index for get one. Filters use city__iexact and
    # property_type__icontains, which a plain B-tree can't serve; the
    # similar-properties lookup (exact city + type, value range) uses
    # idx_city_type_value, the address lookup (address LIKE 'PREFIX%') uses
    # idx_address_prefix, and comparable sales use idx_neighborhood.

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

    # Annual tax estimates in whole dollars, precomputed at import (services/tax_estimate.py)
    est_tax_current = models.IntegerField(null=True)  # the current owner's bill
    est_tax_homestead = models.IntegerField(null=True)  # a buyer who files for homestead
    est_tax_no_homestead = models.IntegerField(null=True)  # a buyer renting it out or using it as a second home

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
            # Address lookup: prefix match on the upper-case county address.
            models.Index(fields=['address'], name='idx_address_prefix', opclasses=['varchar_pattern_ops']),
            # Comparable sales on the detail page: every home in one neighborhood.
            models.Index(fields=['neighborhood_code'], name='idx_neighborhood'),
        ]

    def __str__(self):
        return f'{self.parcel_id} - {self.address}'

    @property
    def price_per_sqft(self):
        if self.market_value and self.building_sqft and self.building_sqft > 0:
            return self.market_value / self.building_sqft
        return None


class TaxDistrictMillage(models.Model):
    """Combined millage per PCPAO tax district, from RP_MILLAGE_RATES.

    School levies are split out because homestead exemptions treat them
    differently from every other levy.
    """

    district_code = models.CharField(max_length=8)
    tax_year = models.IntegerField()
    rate_description = models.CharField(max_length=32)  # e.g. '2025 Final'
    total_mills = models.DecimalField(max_digits=7, decimal_places=4)
    school_mills = models.DecimalField(max_digits=7, decimal_places=4)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['district_code', 'tax_year'], name='uniq_millage_district_year'),
        ]

    def __str__(self):
        return f'{self.district_code} {self.rate_description}: {self.total_mills} mills'


class MortgageRate(models.Model):
    """The latest 30-year fixed average, kept as a single row (pk=1).

    Written weekly by the refresh_mortgage_rate command; the calculator falls
    back to a constant in services/lending_config.py when the row is missing.
    """

    rate = models.DecimalField(max_digits=5, decimal_places=2)  # percent, e.g. 7.40
    as_of = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.rate}% as of {self.as_of}'


class Sale(models.Model):
    """One qualified sale of an improved parcel, from PCPAO's RP_SALES.

    Reloaded whole by the monthly import (services/sales_importer.py), so
    rows are never updated in place. `parcel_id` matches
    PropertyListing.parcel_id but is not a foreign key: the county file lists
    sales for parcels the property import skips.
    """

    parcel_id = models.CharField(max_length=50)
    sale_date = models.DateField()
    price = models.IntegerField()  # whole dollars

    class Meta:
        constraints = [
            # Also the index for a parcel's sales history.
            models.UniqueConstraint(fields=['parcel_id', 'sale_date'], name='uniq_sale_parcel_date'),
        ]

    def __str__(self):
        return f'{self.parcel_id} sold {self.sale_date} for ${self.price:,}'
