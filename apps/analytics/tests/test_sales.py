import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import DatabaseError
from django.urls import reverse

from apps.analytics.models import PropertyListing, Sale
from apps.analytics.services import comps as comps_service
from apps.analytics.services.comps import build_sales_outlook, comp_type_bucket
from apps.analytics.services.sales_importer import import_sales, read_qualified_sales

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures'
SAMPLE_PROPERTIES = FIXTURES / 'sample_pcpao_data.csv'
SAMPLE_SALES = FIXTURES / 'sample_sales.csv'

SUBJECT = '15-29-16-00000-000-0001'
TODAY = date(2026, 10, 8)

SALES_COLUMNS = [
    'STRAP',
    'PARCEL_NUMBER',
    'SALE_DATE',
    'BOOK_PAGE',
    'SALE_ID',
    'PRICE',
    'QUALIFIED_FLG',
    'VACANT_IMPROVED',
    'MONTH_REAL',
    'DAY_REAL',
    'GRANTEE',
    'GRANTOR',
    'MULTI_SALES_YN',
]


def _sales_csv(tmp_path, *rows):
    """An RP_SALES file. Each row overrides a qualified, improved, single-parcel sale."""
    defaults = {
        'PARCEL_NUMBER': SUBJECT,
        'SALE_DATE': '2025-03-14 00:00:00',
        'SALE_ID': '1',
        'PRICE': '300000',
        'QUALIFIED_FLG': 'Q',
        'VACANT_IMPROVED': 'I',
        'MONTH_REAL': 'Y',
        'DAY_REAL': 'Y',
        'GRANTEE': 'BUYER NAME',
        'GRANTOR': 'SELLER NAME',
        'MULTI_SALES_YN': 'N',
    }
    path = tmp_path / 'RP_SALES.csv'
    with path.open('w', encoding='cp1252', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=SALES_COLUMNS, quoting=csv.QUOTE_ALL, restval='')
        writer.writeheader()
        writer.writerows({**defaults, **row} for row in rows)
    return str(path)


def _home(parcel_id, **fields):
    defaults = {
        'address': f'{parcel_id[-4:]} OAK ST',
        'city': 'Clearwater',
        'zip_code': '33755',
        'property_type': 'Single Family Home',
        'market_value': Decimal('300000'),
        'building_sqft': 1500,
        'neighborhood_code': '2104.00',
    }
    return PropertyListing.objects.create(parcel_id=parcel_id, **{**defaults, **fields})


def _neighbor_sale(n, price, sale_date=date(2026, 3, 1), **fields):
    """A neighbor of SUBJECT and one sale of it."""
    home = _home(f'15-29-16-00000-000-01{n:02d}', **fields)
    Sale.objects.create(parcel_id=home.parcel_id, sale_date=sale_date, price=price)
    return home


class TestReadQualifiedSales:
    def test_keeps_only_qualified_single_parcel_sales_of_improved_parcels(self, tmp_path):
        path = _sales_csv(
            tmp_path,
            {'PARCEL_NUMBER': 'KEPT'},
            {'PARCEL_NUMBER': 'UNQUALIFIED', 'QUALIFIED_FLG': 'U'},
            {'PARCEL_NUMBER': 'MULTI-PARCEL', 'QUALIFIED_FLG': 'M'},
            {'PARCEL_NUMBER': 'VACANT', 'VACANT_IMPROVED': 'V'},
            {'PARCEL_NUMBER': 'PRICE-COVERS-SEVERAL', 'MULTI_SALES_YN': 'Y'},
            {'PARCEL_NUMBER': 'NO-PRICE', 'PRICE': ''},
            {'PARCEL_NUMBER': 'BAD-DATE', 'SALE_DATE': ''},
        )

        sales = read_qualified_sales(path)

        assert [(s.parcel_id, s.sale_date, s.price) for s in sales] == [('KEPT', date(2025, 3, 14), 300000)]

    def test_same_day_deeds_keep_the_later_one(self, tmp_path):
        path = _sales_csv(
            tmp_path,
            {'SALE_ID': '3', 'PRICE': '451300'},
            {'SALE_ID': '2', 'PRICE': '430000'},
        )

        assert [s.price for s in read_qualified_sales(path)] == [451300]

    def test_sample_fixture(self):
        sales = read_qualified_sales(str(SAMPLE_SALES))

        # 25 rows in the file, three of them unqualified.
        assert len(sales) == 22
        assert {s.parcel_id for s in sales if s.price == 900000} == {'03-29-15-68094-002-0070'}


class TestImportSales:
    def test_replaces_what_was_loaded_before(self, tmp_path):
        Sale.objects.create(parcel_id='GONE', sale_date=date(2022, 1, 1), price=1)

        loaded = import_sales(_sales_csv(tmp_path, {}, {'SALE_DATE': '2023-06-01 00:00:00', 'PRICE': '250000'}))

        assert loaded == 2
        assert list(Sale.objects.order_by('sale_date').values_list('parcel_id', 'price')) == [
            (SUBJECT, 250000),
            (SUBJECT, 300000),
        ]

    def test_file_with_no_qualified_sales_keeps_the_table(self, tmp_path):
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2022, 1, 1), price=200000)

        with pytest.raises(RuntimeError, match='No qualified sales'):
            import_sales(_sales_csv(tmp_path, {'QUALIFIED_FLG': 'Qualified'}))

        assert Sale.objects.count() == 1

    def test_renamed_column_fails_before_touching_the_table(self, tmp_path):
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2022, 1, 1), price=200000)
        path = tmp_path / 'RP_SALES.csv'
        path.write_text('"PARCEL_NUMBER","SALE_DATE","PRICE"\n"X","2025-01-01 00:00:00","1"\n', encoding='cp1252')

        with pytest.raises(KeyError):
            import_sales(str(path))

        assert Sale.objects.count() == 1


class TestImportCommand:
    def test_sales_file_is_loaded_with_the_properties(self):
        call_command('import_pcpao_data', file=str(SAMPLE_PROPERTIES), sales_file=str(SAMPLE_SALES), quiet=True)

        assert Sale.objects.count() == 22
        assert Sale.objects.filter(parcel_id='14-29-15-50454-000-0030').count() == 2

    def test_without_a_sales_file_existing_sales_are_kept(self):
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2022, 1, 1), price=200000)

        call_command('import_pcpao_data', file=str(SAMPLE_PROPERTIES), quiet=True)

        assert Sale.objects.count() == 1

    def test_download_fetches_sales_after_properties(self, tmp_path):
        files = {
            'RP_MILLAGE_RATES': str(FIXTURES / 'sample_millage_rates.csv'),
            'RP_PROPERTY_INFO': str(SAMPLE_PROPERTIES),
            'RP_SALES': str(SAMPLE_SALES),
        }
        with patch(
            'apps.analytics.management.commands.import_pcpao_data.download_pcpao_file',
            side_effect=lambda name, _dir: files[name],
        ) as download:
            call_command('import_pcpao_data', quiet=True)

        assert [call.args[0] for call in download.call_args_list] == [
            'RP_MILLAGE_RATES',
            'RP_PROPERTY_INFO',
            'RP_SALES',
        ]
        assert Sale.objects.count() == 22


class TestCompTypeBucket:
    @pytest.mark.parametrize(
        ('property_type', 'bucket'),
        [
            ('Single Family Home', 'Single Family'),
            ('Single Family - more than one house per parcel', 'Single Family'),
            ('Planned Unit Development', 'Single Family'),
            ('Condominium (land lease)', 'Condo'),
            ('Condo Conversion  - Apartments to Platted Condo (Predominately Owner-Occupied)', 'Condo'),
            ('Manufactured Home (Condo or Land Lease)', 'Mobile Home'),
            ('Duplex-Triplex-Fourplex', 'Multi-Family'),
            ('Restaurant, Cafeteria', None),
            ('Vacant Residential', None),
            (None, None),
        ],
    )
    def test_buckets(self, property_type, bucket):
        assert comp_type_bucket(property_type) == bucket


class TestSalesHistory:
    def test_no_sales_and_no_comps_is_none(self):
        assert build_sales_outlook(_home(SUBJECT), TODAY) is None

    def test_history_is_newest_first(self):
        home = _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2021, 5, 6), price=250000)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2025, 4, 10), price=400000)

        outlook = build_sales_outlook(home, TODAY)

        assert [s.price for s in outlook.history] == [400000, 250000]
        assert outlook.last_sale.sale_date == date(2025, 4, 10)
        assert outlook.flip is None
        assert outlook.comps is None

    @pytest.mark.parametrize(
        ('earlier', 'later', 'resold'),
        [
            (date(2024, 9, 5), date(2025, 12, 30), 'after 15 months'),
            (date(2024, 9, 5), date(2026, 9, 5), 'after 24 months'),
            (date(2025, 1, 31), date(2025, 2, 28), 'within a month'),
            (date(2025, 1, 15), date(2025, 2, 20), 'after 1 month'),
        ],
    )
    def test_resale_within_two_years_is_a_flip(self, earlier, later, resold):
        home = _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=earlier, price=439000)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=later, price=600500)

        flip = build_sales_outlook(home, TODAY).flip

        assert (flip.earlier.price, flip.later.price, flip.resold) == (439000, 600500, resold)

    def test_resale_after_more_than_two_years_is_not_a_flip(self):
        home = _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2022, 9, 4), price=439000)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2024, 9, 5), price=600500)

        assert build_sales_outlook(home, TODAY).flip is None

    def test_only_the_two_most_recent_sales_count(self):
        home = _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2021, 4, 1), price=375000)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2021, 9, 28), price=425000)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2026, 1, 15), price=610000)

        assert build_sales_outlook(home, TODAY).flip is None

    def test_missing_table_is_none(self):
        home = _home(SUBJECT)
        with patch.object(comps_service.Sale.objects, 'filter', side_effect=DatabaseError('no such table')):
            assert build_sales_outlook(home, TODAY) is None


class TestComparableSales:
    def test_median_price_per_sqft_with_count_and_range(self):
        home = _home(SUBJECT, building_sqft=1500)
        _neighbor_sale(1, 300000, building_sqft=1500)  # $200/sqft
        _neighbor_sale(2, 448000, building_sqft=1600)  # $280/sqft
        _neighbor_sale(3, 350000, building_sqft=1400)  # $250/sqft

        comps = build_sales_outlook(home, TODAY).comps

        assert comps.count == 3
        assert comps.median_per_sqft == pytest.approx(250)
        assert (comps.low_per_sqft, comps.high_per_sqft) == (pytest.approx(200), pytest.approx(280))
        assert comps.indicated_value == 375000
        assert comps.subject_sqft == 1500

    def test_indicated_value_is_rounded_to_the_nearest_thousand(self):
        home = _home(SUBJECT, building_sqft=1437)
        for n, price in enumerate((301000, 305500, 312250), start=1):
            _neighbor_sale(n, price, building_sqft=1437)

        assert build_sales_outlook(home, TODAY).comps.indicated_value == 306000

    def test_fewer_than_three_is_hidden(self):
        home = _home(SUBJECT)
        _neighbor_sale(1, 300000)
        _neighbor_sale(2, 320000)

        assert build_sales_outlook(home, TODAY) is None

    def test_leaves_out_homes_that_are_not_comparable(self):
        home = _home(SUBJECT, building_sqft=1600)
        _neighbor_sale(1, 300000)
        _neighbor_sale(2, 320000)
        _neighbor_sale(3, 900000, neighborhood_code='2105.00')
        _neighbor_sale(4, 900000, property_type='Condominium')
        _neighbor_sale(5, 900000, building_sqft=1199)  # just under 75% of 1,600
        _neighbor_sale(6, 900000, building_sqft=2001)  # just over 125%
        _neighbor_sale(7, 900000, sale_date=date(2025, 10, 7))  # a day too old
        # The subject's own sale is its history, not a comp.
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2026, 5, 1), price=900000)

        outlook = build_sales_outlook(home, TODAY)
        assert outlook.comps is None

        _neighbor_sale(8, 340000, building_sqft=1200, sale_date=date(2025, 10, 8))
        comps = build_sales_outlook(home, TODAY).comps
        assert sorted(comp.price for comp in comps.shown) == [300000, 320000, 340000]

    def test_a_home_sold_twice_counts_once_at_its_latest_price(self):
        home = _home(SUBJECT)
        twice = _neighbor_sale(1, 250000, sale_date=date(2025, 11, 1))
        Sale.objects.create(parcel_id=twice.parcel_id, sale_date=date(2026, 6, 1), price=390000)
        _neighbor_sale(2, 300000)
        _neighbor_sale(3, 330000)

        comps = build_sales_outlook(home, TODAY).comps

        assert comps.count == 3
        assert sorted(comp.price for comp in comps.shown) == [300000, 330000, 390000]

    def test_shows_the_most_recent_five(self):
        home = _home(SUBJECT)
        for n in range(1, 8):
            _neighbor_sale(n, 300000 + n * 1000, sale_date=date(2026, n, 1))

        comps = build_sales_outlook(home, TODAY).comps

        assert comps.count == 7
        assert [comp.sale_date.month for comp in comps.shown] == [7, 6, 5, 4, 3]

    @pytest.mark.parametrize(
        'fields',
        [{'neighborhood_code': None}, {'building_sqft': None}, {'building_sqft': 0}, {'property_type': 'Office'}],
    )
    def test_no_comps_without_a_neighborhood_size_or_home_type(self, fields):
        for n in range(1, 4):
            _neighbor_sale(n, 300000)
        home = _home(SUBJECT, **fields)

        assert build_sales_outlook(home, TODAY) is None


class TestParcelPage:
    # The view uses the real date, so comps here sold a month before the test runs.
    RECENT = date.today() - timedelta(days=30)

    def _get(self, client):
        return client.get(reverse('property-detail', args=[SUBJECT]))

    def test_shows_last_sale_flip_and_comps(self, client):
        _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2024, 9, 5), price=439000)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2025, 12, 30), price=600500)
        neighbor = _neighbor_sale(1, 300000, sale_date=self.RECENT)
        _neighbor_sale(2, 330000, sale_date=self.RECENT)
        _neighbor_sale(3, 360000, sale_date=self.RECENT)

        html = self._get(client).content.decode()

        assert 'id="sales"' in html
        assert '$600,500' in html
        assert 'December 2025' in html
        assert 'Resold after 15 months:' in html
        assert 'often follows a renovation' in html
        assert '$220<span' in html  # 330,000 / 1,500 sqft
        assert 'The middle of 3 sales' in html
        assert 'that is about $330,000' in html
        assert reverse('property-detail', args=[neighbor.parcel_id]) in html

    def test_resale_at_a_lower_price_does_not_suggest_a_renovation(self, client):
        _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2024, 9, 5), price=600500)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2025, 12, 30), price=530000)

        html = self._get(client).content.decode()

        assert 'Resold after 15 months:' in html
        assert 'renovation' not in html
        assert 'Ask why the last owner left so soon' in html

    def test_says_so_when_there_are_too_few_comps(self, client):
        _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2022, 5, 12), price=350000)

        html = self._get(client).content.decode()

        assert '$350,000' in html
        assert 'Too few sales' in html
        assert 'Resold' not in html

    def test_says_so_when_the_home_has_not_sold(self, client):
        _home(SUBJECT)
        for n in range(1, 4):
            _neighbor_sale(n, 300000, sale_date=self.RECENT)

        html = self._get(client).content.decode()

        assert 'No recent sale' in html
        assert 'The middle of 3 sales' in html

    def test_no_card_without_sales_or_comps(self, client):
        _home(SUBJECT)

        response = self._get(client)

        assert response.status_code == 200
        assert 'id="sales"' not in response.content.decode()

    def test_page_stays_cacheable(self, client):
        _home(SUBJECT)
        Sale.objects.create(parcel_id=SUBJECT, sale_date=date(2022, 5, 12), price=350000)

        response = self._get(client)

        assert 's-maxage' in response['Cache-Control']
        assert not response.cookies
