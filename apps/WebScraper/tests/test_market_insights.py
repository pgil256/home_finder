from decimal import Decimal

import pytest

from apps.WebScraper.models import PropertyListing
from apps.WebScraper.services.market_insights import build_market_insights

pytestmark = pytest.mark.django_db


def _parcel(idx: int, *, market_value: int, assessed_value: int, sqft: int = 1000, tax_amount: int = 1000):
    return PropertyListing.objects.create(
        parcel_id=f'insight-{idx:03d}',
        address=f'{idx} Analysis Ave',
        city='Clearwater' if idx % 2 else 'St. Petersburg',
        zip_code='33755' if idx % 2 else '33701',
        property_type='Single Family' if idx % 2 else 'Condo',
        market_value=Decimal(market_value),
        assessed_value=Decimal(assessed_value),
        building_sqft=sqft,
        year_built=1980 + idx,
        lot_sqft=6000 + idx,
        tax_amount=Decimal(tax_amount),
    )


def test_empty_scope_returns_empty_insight_payload():
    insights = build_market_insights()

    assert insights['exact']['parcel_count'] == 0
    assert insights['city_segments'] == []
    assert insights['outliers'] == {'market_value': [], 'assessed_gap': [], 'tax_rate': []}
    assert insights['takeaways'] == ['No parcels match the current filters. Broaden the scope to generate market signals.']


def test_exact_kpis_include_medians_and_derived_rates():
    _parcel(1, market_value=100000, assessed_value=90000, sqft=1000, tax_amount=1000)
    _parcel(2, market_value=200000, assessed_value=180000, sqft=1000, tax_amount=2000)
    _parcel(3, market_value=300000, assessed_value=270000, sqft=1000, tax_amount=3000)
    _parcel(4, market_value=1000000, assessed_value=800000, sqft=2000, tax_amount=10000)

    exact = build_market_insights()['exact']

    assert exact['parcel_count'] == 4
    assert float(exact['median_market_value']) == 250000
    assert float(exact['mean_market_value']) == 400000
    assert float(exact['total_market_value']) == 1600000
    assert float(exact['median_price_per_sqft']) == 250
    assert float(exact['median_tax_rate']) == 1
    assert round(float(exact['avg_assessed_gap_pct']), 2) == 12.50


def test_percentiles_and_segments_are_computed_from_analysis_frame():
    for idx, value in enumerate([100000, 200000, 300000, 400000, 500000], start=1):
        _parcel(idx, market_value=value, assessed_value=value - 10000, sqft=1000 + idx, tax_amount=2500)

    insights = build_market_insights()

    assert [row['label'] for row in insights['percentiles']['market_value']] == ['P10', 'P25', 'P50', 'P75', 'P90']
    assert len(insights['city_segments']) == 2
    assert len(insights['type_segments']) == 2
    assert insights['charts']['valueDistribution']['datasets'][0]['data']


def test_low_sample_charts_return_explanatory_notes(sample_property):
    insights = build_market_insights()

    payload = insights['charts']['valueDistribution']
    assert payload['datasets'][0]['data'] == []
    assert 'Need at least two numeric values' in payload['meta']['note']


def test_high_value_outlier_links_to_drilldown():
    for idx, value in enumerate([100000, 110000, 120000, 130000, 900000], start=1):
        _parcel(idx, market_value=value, assessed_value=90000, sqft=1000, tax_amount=2500)

    rows = build_market_insights()['outliers']['market_value']

    assert rows
    assert rows[0]['parcel_id'] == 'insight-005'
    assert rows[0]['detail_url'] == '/scraper/property/insight-005/'


def test_missing_sqft_and_tax_do_not_break_derived_metrics():
    PropertyListing.objects.create(
        parcel_id='missing-derived',
        address='1 Null Island',
        city='Clearwater',
        zip_code='33755',
        property_type='Single Family',
        market_value=Decimal('250000'),
        assessed_value=Decimal('200000'),
        building_sqft=None,
        tax_amount=None,
    )

    insights = build_market_insights()

    assert insights['exact']['median_price_per_sqft'] is None
    assert insights['exact']['median_tax_rate'] is None
    assert insights['sample_parcels'][0]['price_per_sqft'] is None
