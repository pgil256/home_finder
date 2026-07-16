from django.db import migrations


def scrub_street_view_urls(apps, schema_editor):
    PropertyListing = apps.get_model('WebScraper', 'PropertyListing')
    PropertyListing.objects.filter(image_url__icontains='maps.googleapis.com/maps/api/streetview').update(image_url=None)


class Migration(migrations.Migration):
    dependencies = [
        ('WebScraper', '0004_alter_propertylisting_address_and_more'),
    ]

    operations = [
        migrations.RunPython(scrub_street_view_urls, migrations.RunPython.noop),
    ]
