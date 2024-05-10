from django.contrib import admin
from .models import PropertyListing

class PropertyListingAdmin(admin.ModelAdmin):
    # Fields to display in the admin list view
    list_display = (
        'address', 'price', 'bedrooms', 'bathrooms', 'home_size', 'lot_size',
        'property_type', 'garage', 'year_built', 'time_on_market'
    )

    # Fields to use as filter options
    list_filter = ('property_type', 'bedrooms', 'bathrooms', 'stories', 'garage', 'year_built')

    # Fields to add to the search functionality
    search_fields = ('address', 'description', 'property_type')

    # Settings for how many items per page
    list_per_page = 25

    # Settings to specify fields that should be editable in the list view
    list_editable = ('price', 'time_on_market')

admin.site.register(PropertyListing, PropertyListingAdmin)
