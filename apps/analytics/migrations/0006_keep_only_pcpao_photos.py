from urllib.parse import urlsplit

from django.db import migrations


def _is_pcpao_photo(value):
    if not value:
        return False
    try:
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or '').lower().rstrip('.')
        port = parsed.port
    except (AttributeError, ValueError):
        return False
    return (
        parsed.scheme.lower() == 'https'
        and (hostname == 'pcpao.gov' or hostname.endswith('.pcpao.gov'))
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


def keep_only_pcpao_photos(apps, schema_editor):
    PropertyListing = apps.get_model('WebScraper', 'PropertyListing')
    stale_ids = []
    images = PropertyListing.objects.exclude(image_url__isnull=True).exclude(image_url='')

    for listing_id, image_url in images.values_list('pk', 'image_url').iterator(chunk_size=2000):
        if _is_pcpao_photo(image_url):
            continue
        stale_ids.append(listing_id)
        if len(stale_ids) == 2000:
            PropertyListing.objects.filter(pk__in=stale_ids).update(image_url=None)
            stale_ids.clear()

    if stale_ids:
        PropertyListing.objects.filter(pk__in=stale_ids).update(image_url=None)


class Migration(migrations.Migration):
    dependencies = [
        ('WebScraper', '0005_scrub_street_view_urls'),
    ]

    operations = [
        migrations.RunPython(keep_only_pcpao_photos, migrations.RunPython.noop),
    ]
