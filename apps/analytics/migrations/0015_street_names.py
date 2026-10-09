from django.db import migrations, models

TRIGRAM_INDEX = 'idx_street_name_trgm'


def add_trigram_index(apps, schema_editor):
    """Only Postgres has pg_trgm. SQLite, in development and tests, ranks names in Python."""
    if schema_editor.connection.vendor != 'postgresql':
        return
    table = schema_editor.quote_name(apps.get_model('WebScraper', 'StreetName')._meta.db_table)
    schema_editor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    schema_editor.execute(f'CREATE INDEX IF NOT EXISTS {TRIGRAM_INDEX} ON {table} USING gin (name gin_trgm_ops)')


def drop_trigram_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(f'DROP INDEX IF EXISTS {TRIGRAM_INDEX}')


class Migration(migrations.Migration):
    dependencies = [
        ('WebScraper', '0014_flood_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='StreetName',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('city', models.CharField(max_length=100)),
                ('parcel_count', models.IntegerField()),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(fields=('name', 'city'), name='uniq_street_name_city'),
                ],
            },
        ),
        migrations.RunPython(add_trigram_index, drop_trigram_index),
    ]
