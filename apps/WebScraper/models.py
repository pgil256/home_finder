from django.db import models

class PropertyListing(models.Model):
    link = models.URLField()
    address = models.CharField(max_length=255)
    image_of_property = models.URLField()
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    bedrooms = models.IntegerField(null=True)
    bathrooms = models.DecimalField(max_digits=4, decimal_places=2, null=True)
    stories = models.IntegerField(null=True)
    home_size = models.IntegerField(null=True)  # in square feet
    lot_size = models.IntegerField(null=True)  # in square feet
    property_type = models.CharField(max_length=100)
    price_per_sqft = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    garage = models.CharField(max_length=50, null=True)
    year_built = models.IntegerField(null=True)
    time_on_market = models.IntegerField(null=True)  # in days
    estimated_monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    home_insurance = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    hoa_fees = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    mortgage_insurance = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    property_tax = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    def __str__(self):
        return self.address
