from django.db import migrations

TRIGRAM_INDEX = 'idx_street_name_trgm'


def compact_trigram_index(apps, schema_editor):
    """Stop the trigram index growing a pending list, and empty the table.

    The first fill of this table came to 4.5 MB for 11,859 rows, most of it
    the GIN index's pending list from row-by-row inserts. With fastupdate off
    entries go straight into the index. The rows are dropped so the next
    "Database guard" run (or import) refills the table through the rebuild,
    which now truncates and reindexes; lookup works without them in the
    meantime, minus the spelling correction.
    """
    if schema_editor.connection.vendor != 'postgresql':
        return
    table = schema_editor.quote_name(apps.get_model('WebScraper', 'StreetName')._meta.db_table)
    schema_editor.execute(f'ALTER INDEX {TRIGRAM_INDEX} SET (fastupdate = off)')
    schema_editor.execute(f'TRUNCATE {table}')


class Migration(migrations.Migration):
    dependencies = [
        ('WebScraper', '0015_street_names'),
    ]

    operations = [
        # Nothing but the rebuild writes this table, and its GROUP BY already
        # gives one row per name and city. The index cost more than the rows.
        migrations.RemoveConstraint(
            model_name='streetname',
            name='uniq_street_name_city',
        ),
        migrations.RunPython(compact_trigram_index, migrations.RunPython.noop),
    ]
