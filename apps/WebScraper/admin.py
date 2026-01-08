from django.contrib import admin
from .models import PropertyListing


class PropertyListingAdmin(admin.ModelAdmin):
    list_display = (
        'parcel_id', 'address', 'city', 'market_value', 'building_sqft',
        'bedrooms', 'bathrooms', 'land_size', 'tax_status', 'last_scraped'
    )
    list_filter = ('city', 'property_type', 'tax_status', 'delinquent', 'bedrooms')
    search_fields = ('parcel_id', 'address', 'owner_name', 'city')
    list_per_page = 25
    readonly_fields = ('last_scraped', 'created_at')


admin.site.register(PropertyListing, PropertyListingAdmin)
