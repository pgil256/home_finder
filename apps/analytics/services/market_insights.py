from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, FloatField, Max, Min, Sum
from django.db.models.functions import Cast
from django.urls import reverse

from ..models import PropertyListing
from .filtering import apply_filters
from .palette import (
    ACCENT,
    ACCENT_DARK,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_FILL_MEDIUM,
    PRIMARY_FILL_SOFT,
)

MAX_ANALYSIS_ROWS = 50_000
MAX_OUTLIERS = 12
MAX_SAMPLE_PARCELS = 25
MIN_TREND_GROUPS = 3

ANALYSIS_FIELDS = (
    'parcel_id',
    'address',
    'city',
    'zip_code',
    'property_type',
    'market_value',
    'assessed_value',
    'building_sqft',
    'year_built',
    'tax_amount',
)


def filtered_queryset(request=None):
    if request is None:
        return PropertyListing.objects.all()
    qs, _, _ = apply_filters(request)
    return qs


def summarize_filters(request) -> list[tuple[str, str]]:
    if request is None:
        return [('Scope', 'All Pinellas County parcels')]

    out: list[tuple[str, str]] = []
    g = request.GET
    if g.get('q'):
        out.append(('Keyword', g['q']))
    if g.get('city'):
        out.append(('City', g['city']))
    if g.get('zip_code'):
        out.append(('ZIP', g['zip_code']))
    types = g.getlist('property_type')
    if types:
        out.append(('Property type', ', '.join(types)))
    if g.get('min_price') or g.get('max_price'):
        out.append(('Market value', _range_summary(g.get('min_price'), g.get('max_price'), '$')))
    if g.get('year_built'):
        out.append(('Built after', g['year_built']))
    if g.get('min_sqft') or g.get('max_sqft'):
        out.append(('Building sqft', _range_summary(g.get('min_sqft'), g.get('max_sqft'))))
    if g.get('min_lot_sqft') or g.get('max_lot_sqft'):
        out.append(('Lot sqft', _range_summary(g.get('min_lot_sqft'), g.get('max_lot_sqft'))))
    if g.get('min_tax_amount') or g.get('max_tax_amount'):
        out.append(('Annual tax', _range_summary(g.get('min_tax_amount'), g.get('max_tax_amount'), '$')))
    if not out:
        out.append(('Scope', 'All Pinellas County parcels'))
    return out


def build_market_insights(request=None) -> dict[str, Any]:
    qs = filtered_queryset(request)
    exact = _exact_kpis(qs)
    df, source_count = _analysis_frame(qs)

    percentiles = _percentiles(df)
    city_segments = _segments(df, 'city', limit=12)
    type_segments = _segments(df, 'property_type', limit=12)
    outliers = _outliers(df)
    sample_parcels = _sample_parcels(df)
    charts = _charts(df, source_count)

    return {
        'brand': 'Pinellas Market Lens',
        'generated_at': datetime.now(UTC),
        'filters': summarize_filters(request),
        'exact': exact,
        'kpis': _kpi_cards(exact),
        'percentiles': percentiles,
        'city_segments': city_segments,
        'type_segments': type_segments,
        'outliers': outliers,
        'sample_parcels': sample_parcels,
        'charts': charts,
        'takeaways': _takeaways(exact, percentiles, city_segments, type_segments, outliers),
        'methodology': _methodology(source_count, exact['parcel_count']),
        'analysis_row_count': int(source_count),
        'analysis_row_cap': MAX_ANALYSIS_ROWS,
    }


def _exact_kpis(qs) -> dict[str, Any]:
    base = qs.aggregate(
        parcel_count=Count('id'),
        mean_market_value=Avg('market_value'),
        min_market_value=Min('market_value'),
        max_market_value=Max('market_value'),
        total_market_value=Sum('market_value'),
    )

    gap_expr = ExpressionWrapper(
        F('market_value') - F('assessed_value'),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    gap_pct_expr = ExpressionWrapper(
        ((Cast('market_value', FloatField()) - Cast('assessed_value', FloatField())) * 100.0)
        / Cast('market_value', FloatField()),
        output_field=FloatField(),
    )
    gap = qs.filter(market_value__gt=0, assessed_value__isnull=False).aggregate(
        avg_assessed_gap=Avg(gap_expr),
        avg_assessed_gap_pct=Avg(gap_pct_expr),
    )

    price_per_sqft_expr = ExpressionWrapper(
        Cast('market_value', FloatField()) / Cast('building_sqft', FloatField()),
        output_field=FloatField(),
    )
    tax_rate_expr = ExpressionWrapper(
        (Cast('tax_amount', FloatField()) * 100.0) / Cast('market_value', FloatField()),
        output_field=FloatField(),
    )

    return {
        **base,
        **gap,
        'median_market_value': _median_field(qs.exclude(market_value__isnull=True).order_by('market_value'), 'market_value'),
        'median_price_per_sqft': _median_annotation(
            qs.filter(market_value__gt=0, building_sqft__gt=0),
            'price_per_sqft',
            price_per_sqft_expr,
        ),
        'median_tax_rate': _median_annotation(
            qs.filter(market_value__gt=0, tax_amount__gt=0),
            'tax_rate',
            tax_rate_expr,
        ),
    }


def _median_field(ordered_qs, field_name: str):
    count = ordered_qs.count()
    if count == 0:
        return None
    offset = (count - 1) // 2
    limit = 2 if count % 2 == 0 else 1
    values = list(ordered_qs.values_list(field_name, flat=True)[offset : offset + limit])
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return sum(float(v) for v in values) / 2


def _median_annotation(qs, annotation_name: str, annotation):
    ordered = qs.annotate(**{annotation_name: annotation}).order_by(annotation_name)
    return _median_field(ordered, annotation_name)


def _analysis_frame(qs) -> tuple[pd.DataFrame, int]:
    rows = list(qs.order_by('id').values(*ANALYSIS_FIELDS)[:MAX_ANALYSIS_ROWS])
    df = pd.DataFrame(rows)
    if df.empty:
        return _empty_frame(), 0

    for col in ('market_value', 'assessed_value', 'building_sqft', 'year_built', 'tax_amount'):
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['city'] = df['city'].fillna('Unknown').replace('', 'Unknown')
    df['property_type'] = df['property_type'].fillna('Unknown').replace('', 'Unknown')
    df['price_per_sqft'] = np.where(
        (df['market_value'] > 0) & (df['building_sqft'] > 0),
        df['market_value'] / df['building_sqft'],
        np.nan,
    )
    df['assessed_gap'] = np.where(
        (df['market_value'] > 0) & (df['assessed_value'] > 0),
        df['market_value'] - df['assessed_value'],
        np.nan,
    )
    df['assessed_gap_pct'] = np.where(
        (df['market_value'] > 0) & (df['assessed_value'] > 0),
        (df['market_value'] - df['assessed_value']) / df['market_value'] * 100,
        np.nan,
    )
    df['tax_rate'] = np.where(
        (df['market_value'] > 0) & (df['tax_amount'] > 0),
        df['tax_amount'] / df['market_value'] * 100,
        np.nan,
    )
    return df, len(df)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[*ANALYSIS_FIELDS, 'price_per_sqft', 'assessed_gap', 'assessed_gap_pct', 'tax_rate'])


def _percentiles(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    return {
        'market_value': _percentile_rows(df['market_value'] if 'market_value' in df else pd.Series(dtype='float64')),
        'price_per_sqft': _percentile_rows(
            df['price_per_sqft'] if 'price_per_sqft' in df else pd.Series(dtype='float64')
        ),
    }


def _percentile_rows(series: pd.Series) -> list[dict[str, Any]]:
    clean = series.dropna()
    clean = clean[clean > 0]
    if clean.empty:
        return []
    values = np.percentile(clean, [10, 25, 50, 75, 90])
    return [{'label': f'P{p}', 'value': _clean_number(v)} for p, v in zip([10, 25, 50, 75, 90], values, strict=False)]


def _segments(df: pd.DataFrame, field: str, limit: int) -> list[dict[str, Any]]:
    if df.empty or field not in df:
        return []
    grouped = (
        df.groupby(field, dropna=False)
        .agg(
            count=('parcel_id', 'count'),
            median_value=('market_value', 'median'),
            mean_value=('market_value', 'mean'),
            median_price_per_sqft=('price_per_sqft', 'median'),
            median_tax_rate=('tax_rate', 'median'),
            mean_assessed_gap_pct=('assessed_gap_pct', 'mean'),
        )
        .reset_index()
        .sort_values(['count', 'median_value'], ascending=[False, False])
        .head(limit)
    )
    rows: list[dict[str, Any]] = []
    for row in grouped.to_dict('records'):
        rows.append(
            {
                'name': row[field] or 'Unknown',
                'count': int(row['count']),
                'median_value': _none_if_nan(row['median_value']),
                'mean_value': _none_if_nan(row['mean_value']),
                'median_price_per_sqft': _none_if_nan(row['median_price_per_sqft']),
                'median_tax_rate': _none_if_nan(row['median_tax_rate']),
                'mean_assessed_gap_pct': _none_if_nan(row['mean_assessed_gap_pct']),
            }
        )
    return rows


def _charts(df: pd.DataFrame, sample_size: int) -> dict[str, dict[str, Any]]:
    return {
        'valueDistribution': _histogram_payload(
            df['market_value'] if 'market_value' in df else pd.Series(dtype='float64'),
            'Market value distribution',
            sample_size,
            currency=True,
        ),
        'pricePerSqftDistribution': _histogram_payload(
            df['price_per_sqft'] if 'price_per_sqft' in df else pd.Series(dtype='float64'),
            'Price per sqft distribution',
            sample_size,
            currency=True,
        ),
        'citySegments': _segment_chart_payload(_segments(df, 'city', 10), 'Median market value by city'),
        'typeSegments': _segment_chart_payload(_segments(df, 'property_type', 10), 'Median market value by property type'),
        'yearTrend': _year_trend_payload(df),
        'valueGapScatter': _value_gap_scatter_payload(df),
    }


def _histogram_payload(series: pd.Series, label: str, sample_size: int, currency: bool) -> dict[str, Any]:
    clean = series.dropna()
    clean = clean[clean > 0]
    omitted = int(sample_size - len(clean))
    if len(clean) < 2:
        return _empty_chart(label, sample_size, omitted, 'Need at least two numeric values to draw a distribution.')

    cap = clean.quantile(0.99)
    plotted = clean[clean <= cap]
    bins = min(12, max(3, len(plotted.unique())))
    counts, edges = np.histogram(plotted, bins=bins)
    labels = [_format_range(edges[i], edges[i + 1], currency=currency) for i in range(len(edges) - 1)]
    cap_note = None
    if len(plotted) != len(clean):
        cap_note = f'Top 1% trimmed at {_money(cap)} for readability.'
    return {
        'labels': labels,
        'datasets': [
            {
                'label': label,
                'data': [int(v) for v in counts],
                'backgroundColor': PRIMARY,
                'borderColor': PRIMARY_DARK,
            }
        ],
        'meta': {
            'sample_size': int(sample_size),
            'chart_sample_size': int(len(plotted)),
            'omitted_nulls': omitted,
            'note': cap_note,
        },
    }


def _segment_chart_payload(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if not rows:
        return _empty_chart(label, 0, 0, 'No segment rows available.')
    return {
        'labels': [r['name'] for r in rows],
        'datasets': [
            {
                'label': label,
                'data': [_clean_number(r['median_value']) for r in rows],
                'backgroundColor': PRIMARY,
                'borderColor': PRIMARY_DARK,
            },
            {
                'label': 'Parcel count',
                'data': [r['count'] for r in rows],
                'backgroundColor': ACCENT,
                'borderColor': ACCENT_DARK,
            },
        ],
        'meta': {'sample_size': sum(r['count'] for r in rows), 'omitted_nulls': 0, 'note': None},
    }


def _year_trend_payload(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or 'year_built' not in df:
        return _empty_chart('Median value by build decade', 0, 0, 'No build-year data available.')
    trend = df.dropna(subset=['year_built', 'market_value']).copy()
    current_year = datetime.now(UTC).year
    trend = trend[(trend['year_built'] >= 1900) & (trend['year_built'] <= current_year) & (trend['market_value'] > 0)]
    if trend.empty:
        return _empty_chart('Median value by build decade', len(df), len(df), 'No usable build-year rows available.')
    trend['decade'] = (trend['year_built'] // 10 * 10).astype(int)
    grouped = (
        trend.groupby('decade')
        .agg(median_value=('market_value', 'median'), count=('parcel_id', 'count'))
        .query('count >= 2')
        .reset_index()
        .sort_values('decade')
    )
    if len(grouped) < MIN_TREND_GROUPS:
        return _empty_chart(
            'Median value by build decade',
            len(trend),
            len(df) - len(trend),
            'Need at least three decade groups with two parcels each.',
        )
    return {
        'labels': [f'{int(r.decade)}s' for r in grouped.itertuples()],
        'datasets': [
            {
                'label': 'Median market value',
                'data': [_clean_number(r.median_value) for r in grouped.itertuples()],
                'borderColor': PRIMARY,
                'backgroundColor': PRIMARY_FILL_SOFT,
                'tension': 0.25,
            }
        ],
        'meta': {'sample_size': int(len(trend)), 'omitted_nulls': int(len(df) - len(trend)), 'note': None},
    }


def _value_gap_scatter_payload(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return _empty_chart('Market vs assessed value', 0, 0, 'No data available.')
    clean = df.dropna(subset=['market_value', 'assessed_value'])
    clean = clean[(clean['market_value'] > 0) & (clean['assessed_value'] > 0)]
    if len(clean) < 2:
        return _empty_chart('Market vs assessed value', len(df), len(df) - len(clean), 'Need at least two value pairs.')
    if len(clean) > 400:
        clean = clean.sample(400, random_state=7)
        note = 'Scatterplot uses a deterministic 400-row sample for responsiveness.'
    else:
        note = None
    points = [{'x': _clean_number(row.assessed_value), 'y': _clean_number(row.market_value)} for row in clean.itertuples()]
    return {
        'labels': [],
        'datasets': [
            {
                'label': 'Parcel values',
                'data': points,
                'backgroundColor': PRIMARY_FILL_MEDIUM,
                'borderColor': PRIMARY_DARK,
            }
        ],
        'meta': {
            'sample_size': int(len(clean)),
            'omitted_nulls': int(len(df) - len(clean)),
            'note': note,
        },
    }


def _empty_chart(label: str, sample_size: int, omitted: int, note: str) -> dict[str, Any]:
    return {
        'labels': [],
        'datasets': [{'label': label, 'data': []}],
        'meta': {'sample_size': int(sample_size), 'omitted_nulls': int(omitted), 'note': note},
    }


def _outliers(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if df.empty:
        return {'market_value': [], 'assessed_gap': [], 'tax_rate': []}
    return {
        'market_value': _iqr_outlier_rows(df, 'market_value'),
        'assessed_gap': _top_metric_rows(df, 'assessed_gap_pct', ascending=False),
        'tax_rate': _top_metric_rows(df, 'tax_rate', ascending=False),
    }


def _iqr_outlier_rows(df: pd.DataFrame, field: str) -> list[dict[str, Any]]:
    clean = df.dropna(subset=[field])
    clean = clean[clean[field] > 0]
    if len(clean) < 4:
        return []
    q1, q3 = np.percentile(clean[field], [25, 75])
    threshold = q3 + 1.5 * (q3 - q1)
    rows = clean[clean[field] > threshold].sort_values(field, ascending=False).head(MAX_OUTLIERS)
    return [_parcel_row(row, metric_label='Market value', metric_value=getattr(row, field)) for row in rows.itertuples()]


def _top_metric_rows(df: pd.DataFrame, field: str, ascending: bool) -> list[dict[str, Any]]:
    clean = df.dropna(subset=[field])
    clean = clean[np.isfinite(clean[field])]
    if len(clean) < 3:
        return []
    rows = clean.sort_values(field, ascending=ascending).head(MAX_OUTLIERS)
    label = 'Assessed gap' if field == 'assessed_gap_pct' else 'Tax rate'
    return [_parcel_row(row, metric_label=label, metric_value=getattr(row, field)) for row in rows.itertuples()]


def _sample_parcels(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    clean = df.sort_values('market_value', ascending=False, na_position='last').head(MAX_SAMPLE_PARCELS)
    return [_parcel_row(row, metric_label='Market value', metric_value=row.market_value) for row in clean.itertuples()]


def _parcel_row(row, metric_label: str, metric_value: Any) -> dict[str, Any]:
    parcel_id = str(row.parcel_id)
    return {
        'parcel_id': parcel_id,
        'address': row.address or 'Unknown address',
        'city': row.city or 'Unknown',
        'zip_code': row.zip_code or '',
        'property_type': row.property_type or 'Unknown',
        'market_value': _none_if_nan(row.market_value),
        'assessed_value': _none_if_nan(row.assessed_value),
        'price_per_sqft': _none_if_nan(row.price_per_sqft),
        'tax_rate': _none_if_nan(row.tax_rate),
        'assessed_gap_pct': _none_if_nan(row.assessed_gap_pct),
        'metric_label': metric_label,
        'metric_value': _none_if_nan(metric_value),
        'detail_url': reverse('property-detail', args=[parcel_id]),
    }


def _kpi_cards(exact: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            'label': 'Parcels analyzed',
            'value': _count(exact['parcel_count']),
            'note': 'Exact filtered count',
        },
        {
            'label': 'Median market value',
            'value': _money(exact['median_market_value']),
            'note': 'Exact median over non-null values',
        },
        {
            'label': 'Mean market value',
            'value': _money(exact['mean_market_value']),
            'note': 'Exact database average',
        },
        {
            'label': 'Median price per sqft',
            'value': _money(exact['median_price_per_sqft']),
            'note': 'Exact median where sqft exists',
        },
        {
            'label': 'Total market value',
            'value': _money(exact['total_market_value']),
            'note': 'Exact filtered sum',
        },
        {
            'label': 'Median tax rate',
            'value': _percent(exact['median_tax_rate']),
            'note': 'Annual tax divided by market value',
        },
        {
            'label': 'Avg assessed gap',
            'value': _money(exact['avg_assessed_gap']),
            'note': 'Market value minus assessed value',
        },
        {
            'label': 'Avg assessed gap %',
            'value': _percent(exact['avg_assessed_gap_pct']),
            'note': 'Average gap as share of market value',
        },
    ]


def _takeaways(
    exact: dict[str, Any],
    percentiles: dict[str, list[dict[str, Any]]],
    city_segments: list[dict[str, Any]],
    type_segments: list[dict[str, Any]],
    outliers: dict[str, list[dict[str, Any]]],
) -> list[str]:
    if exact['parcel_count'] == 0:
        return ['No parcels match the current filters. Broaden the scope to generate market signals.']

    parcel_count = exact['parcel_count']
    parcel_label = 'parcel' if parcel_count == 1 else 'parcels'
    takeaways = [
        f'The current slice contains {_count(parcel_count)} {parcel_label} with a median market value of {_money(exact["median_market_value"])}.',
    ]
    market_percentiles = percentiles.get('market_value') or []
    p25 = _percentile_lookup(market_percentiles, 'P25')
    p75 = _percentile_lookup(market_percentiles, 'P75')
    if p25 is not None and p75 is not None:
        takeaways.append(f'The middle 50% of recorded market values spans {_money(p25)} to {_money(p75)}.')
    if city_segments:
        leader = city_segments[0]
        leader_label = 'parcel' if leader['count'] == 1 else 'parcels'
        takeaways.append(
            f'{leader["name"]} is the largest city segment in this slice with {_count(leader["count"])} {leader_label}.'
        )
    if type_segments:
        leader = type_segments[0]
        takeaways.append(
            f'{leader["name"]} is the most common property type represented in the filtered data.'
        )
    if outliers.get('market_value'):
        takeaways.append('High-value IQR outliers are exposed as drilldowns so the analysis stays auditable.')
    takeaways.append('These are exploratory public-record signals, not predictions or investment advice.')
    return takeaways


def _methodology(sample_size: int, total_count: int) -> list[str]:
    notes = [
        'Source: Pinellas County Property Appraiser parcel records loaded into the app database.',
        'Headline KPIs use exact database aggregates and ordered medians against the filtered queryset.',
        'EDA charts and segment tables use pandas/numpy transformations over the analysis frame.',
        'Outliers use IQR or top-metric rankings and link back to parcel drilldowns for auditability.',
        'No predictive model is used in this version because the public dataset lacks MLS sale prices and reliable beds/baths coverage.',
    ]
    if total_count > sample_size:
        notes.append(f'Interactive EDA is capped at {_count(MAX_ANALYSIS_ROWS)} rows for responsiveness.')
    return notes


def _percentile_lookup(rows: list[dict[str, Any]], label: str):
    for row in rows:
        if row['label'] == label:
            return row['value']
    return None


def _range_summary(low: str | None, high: str | None, unit: str = '') -> str:
    low_label = _format_filter_number(low, unit)
    high_label = _format_filter_number(high, unit)
    if low_label and high_label:
        return f'{low_label} - {high_label}'
    if low_label:
        return f'{low_label}+'
    return f'up to {high_label}'


def _format_filter_number(value: str | None, unit: str = '') -> str | None:
    if not value:
        return None
    try:
        return f'{unit}{int(float(value)):,}'
    except (TypeError, ValueError):
        return value


def _format_range(low: float, high: float, *, currency: bool) -> str:
    if currency:
        return f'{_money(low)}-{_money(high)}'
    return f'{low:,.0f}-{high:,.0f}'


def _clean_number(value: Any):
    value = _none_if_nan(value)
    if value is None:
        return None
    return float(value)


def _none_if_nan(value: Any):
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        return value
    return value


def _money(value: Any) -> str:
    value = _none_if_nan(value)
    if value is None:
        return '-'
    try:
        return f'${float(value):,.0f}'
    except (TypeError, ValueError):
        return '-'


def _percent(value: Any) -> str:
    value = _none_if_nan(value)
    if value is None:
        return '-'
    try:
        return f'{float(value):.2f}%'
    except (TypeError, ValueError):
        return '-'


def _count(value: Any) -> str:
    value = _none_if_nan(value)
    if value is None:
        return '0'
    try:
        return f'{int(value):,}'
    except (TypeError, ValueError):
        return '0'
