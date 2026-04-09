from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from django.http import HttpResponse

from ..models import PropertyListing

logger = logging.getLogger(__name__)

EXCEL_FIELDS = (
    'parcel_id', 'address', 'city', 'zip_code', 'property_type',
    'market_value', 'assessed_value', 'bedrooms', 'bathrooms',
    'building_sqft', 'year_built', 'lot_sqft', 'tax_amount', 'tax_status',
)

EXCEL_HEADERS = [
    'Parcel ID', 'Address', 'City', 'ZIP', 'Property Type',
    'Market Value', 'Assessed Value', 'Bedrooms', 'Bathrooms',
    'Sq Ft', 'Year Built', 'Lot Sq Ft', 'Tax Amount', 'Tax Status',
]

MAX_PDF_PROPERTIES = 200


def generate_excel_response() -> HttpResponse:
    """Generate and return an Excel file of all properties."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    properties = PropertyListing.objects.only(*EXCEL_FIELDS).order_by('-market_value')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Property Listings"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    for col, header in enumerate(EXCEL_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = border

    for row_num, prop in enumerate(properties, 2):
        values = [
            prop.parcel_id, prop.address, prop.city, prop.zip_code,
            prop.property_type,
            float(prop.market_value) if prop.market_value else None,
            float(prop.assessed_value) if prop.assessed_value else None,
            prop.bedrooms,
            float(prop.bathrooms) if prop.bathrooms else None,
            prop.building_sqft, prop.year_built, prop.lot_sqft,
            float(prop.tax_amount) if prop.tax_amount else None,
            prop.tax_status,
        ]
        for col, value in enumerate(values, 1):
            ws.cell(row=row_num, column=col, value=value)

    for col in ws.columns:
        max_len = max((len(str(cell.value or '')) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="PropertyListings.xlsx"'
    return response


def generate_pdf_response() -> HttpResponse:
    """Generate a PDF report with property listings and market analysis charts."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np
    import pandas as pd
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
    )
    from reportlab.lib.units import inch

    properties = PropertyListing.objects.only(
        'parcel_id', 'address', 'city', 'property_type', 'market_value',
        'assessed_value', 'bedrooms', 'bathrooms', 'building_sqft',
        'year_built', 'tax_amount',
    ).order_by('-market_value')[:MAX_PDF_PROPERTIES]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    story: list[Any] = []
    title_style = ParagraphStyle('Title', fontSize=20, alignment=TA_CENTER, spaceAfter=10)
    subtitle_style = ParagraphStyle(
        'Subtitle', fontSize=11, alignment=TA_CENTER,
        textColor=rl_colors.grey, spaceAfter=30,
    )

    story.append(Paragraph("Pinellas County Property Report", title_style))
    story.append(Paragraph(
        f"{properties.count()} properties &bull; Market Analysis", subtitle_style,
    ))

    # Property table
    header = ['Address', 'City', 'Type', 'Market Value', 'Beds', 'Baths', 'Sq Ft', 'Year', 'Tax']
    data = [header]
    for prop in properties:
        data.append([
            (prop.address or '')[:30],
            prop.city or '',
            (prop.property_type or '')[:20],
            f"${prop.market_value:,.0f}" if prop.market_value else 'N/A',
            str(prop.bedrooms or ''),
            str(prop.bathrooms or ''),
            f"{prop.building_sqft:,}" if prop.building_sqft else '',
            str(prop.year_built or ''),
            f"${prop.tax_amount:,.0f}" if prop.tax_amount else '',
        ])

    col_widths = [
        2 * inch, 1.2 * inch, 1.3 * inch, 1.1 * inch,
        0.5 * inch, 0.5 * inch, 0.8 * inch, 0.6 * inch, 0.9 * inch,
    ]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor("#1e3a5f")),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#e2e8f0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f7fafc")]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    # Build DataFrame for charts
    raw = list(properties.values(
        'market_value', 'assessed_value', 'building_sqft', 'property_type',
        'year_built', 'tax_amount', 'city', 'bedrooms', 'bathrooms',
    ))
    df = pd.DataFrame(raw)
    for col in ['market_value', 'assessed_value', 'tax_amount', 'bathrooms']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    chart_colors = [
        '#1e3a5f', '#2c5282', '#38a169', '#dd6b20', '#c53030',
        '#805ad5', '#d69e2e', '#319795', '#e53e3e', '#3182ce',
    ]

    def _add_chart(fig: Any) -> None:
        img_buf = BytesIO()
        fig.savefig(img_buf, format='png', dpi=120, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        img_buf.seek(0)
        story.append(PageBreak())
        story.append(Image(img_buf, width=9 * inch, height=5.5 * inch))

    # Chart 1: Distribution of Market Values
    prices = df['market_value'].dropna()
    if len(prices) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(prices, bins=20, color=chart_colors[0], edgecolor='white', alpha=0.85)
        mean_price = prices.mean()
        ax.axvline(mean_price, color=chart_colors[2], linestyle='--', linewidth=2,
                   label=f'Mean: ${mean_price:,.0f}')
        ax.set_title('Distribution of Market Values', fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel('Market Value')
        ax.set_ylabel('Number of Properties')
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax.legend()
        plt.tight_layout()
        _add_chart(fig)

    # Chart 2: Home Size vs Market Value
    plot_df = df[['building_sqft', 'market_value']].dropna()
    if len(plot_df) > 2:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(plot_df['building_sqft'], plot_df['market_value'],
                   c=chart_colors[1], alpha=0.6, s=80, edgecolors='white')
        z = np.polyfit(plot_df['building_sqft'], plot_df['market_value'], 1)
        p = np.poly1d(z)
        x_line = np.linspace(plot_df['building_sqft'].min(), plot_df['building_sqft'].max(), 100)
        ax.plot(x_line, p(x_line), color=chart_colors[2], linestyle='--', linewidth=2, label='Trend')
        ax.set_title('Home Size vs. Market Value', fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel('Square Footage')
        ax.set_ylabel('Market Value')
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax.legend()
        plt.tight_layout()
        _add_chart(fig)

    # Chart 3: Property Types
    type_counts = df['property_type'].value_counts().head(10)
    if len(type_counts) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(range(len(type_counts)), type_counts.values,
                      color=[chart_colors[i % len(chart_colors)] for i in range(len(type_counts))],
                      edgecolor='white')
        ax.set_title('Listings by Property Type', fontsize=14, fontweight='bold', pad=15)
        ax.set_xticks(range(len(type_counts)))
        ax.set_xticklabels(type_counts.index, rotation=45, ha='right', fontsize=8)
        ax.set_ylabel('Count')
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                    str(int(bar.get_height())), ha='center', va='bottom', fontsize=9)
        plt.tight_layout()
        _add_chart(fig)

    # Chart 4: Year Built Distribution
    years = df['year_built'].dropna()
    if len(years) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(years, bins=15, color=chart_colors[3], edgecolor='white', alpha=0.85)
        ax.set_title('Distribution of Year Built', fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel('Year Built')
        ax.set_ylabel('Number of Properties')
        plt.tight_layout()
        _add_chart(fig)

    # Chart 5: Market Value vs Assessed Value
    val_df = df[['market_value', 'assessed_value']].dropna()
    val_df = val_df[(val_df['market_value'] > 0) & (val_df['assessed_value'] > 0)]
    if len(val_df) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(val_df['assessed_value'], val_df['market_value'],
                   c=chart_colors[1], alpha=0.6, s=80, edgecolors='white')
        max_val = max(val_df['market_value'].max(), val_df['assessed_value'].max())
        min_val = min(val_df['market_value'].min(), val_df['assessed_value'].min())
        ax.plot([min_val, max_val], [min_val, max_val], color='grey',
                linestyle='--', linewidth=1.5, label='Equal Value', alpha=0.7)
        ax.set_title('Market Value vs. Assessed Value', fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel('Assessed Value')
        ax.set_ylabel('Market Value')
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax.legend()
        plt.tight_layout()
        _add_chart(fig)

    # Chart 6: Average Price by City
    city_stats = df.groupby('city')['market_value'].agg(['mean', 'count']).dropna()
    city_stats = city_stats[city_stats['count'] >= 1].sort_values('mean', ascending=False).head(10)
    if len(city_stats) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(range(len(city_stats)), city_stats['mean'].values,
                      color=[chart_colors[i % len(chart_colors)] for i in range(len(city_stats))],
                      edgecolor='white')
        ax.set_title('Average Market Value by City', fontsize=14, fontweight='bold', pad=15)
        ax.set_xticks(range(len(city_stats)))
        ax.set_xticklabels(city_stats.index, rotation=45, ha='right')
        ax.set_ylabel('Average Market Value')
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        for i, bar in enumerate(bars):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f'n={int(city_stats["count"].iloc[i])}', ha='center', va='bottom', fontsize=8)
        plt.tight_layout()
        _add_chart(fig)

    # Chart 7: Tax Burden Analysis
    tax_df = df[['market_value', 'tax_amount']].dropna()
    tax_df = tax_df[(tax_df['market_value'] > 0) & (tax_df['tax_amount'] > 0)]
    if len(tax_df) > 0:
        tax_df['tax_rate'] = (tax_df['tax_amount'] / tax_df['market_value']) * 100
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(tax_df['market_value'], tax_df['tax_rate'],
                   c=chart_colors[3], alpha=0.6, s=80, edgecolors='white')
        avg_rate = tax_df['tax_rate'].mean()
        ax.axhline(avg_rate, color=chart_colors[4], linestyle='--', linewidth=2,
                   label=f'Avg: {avg_rate:.2f}%')
        ax.axhline(1.8, color=chart_colors[2], linestyle=':', linewidth=1.5,
                   label='FL Avg: 1.8%', alpha=0.7)
        ax.set_title('Tax Burden Analysis', fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel('Market Value')
        ax.set_ylabel('Effective Tax Rate (%)')
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax.legend()
        plt.tight_layout()
        _add_chart(fig)

    doc.build(story)
    buf.seek(0)

    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="PropertyReport.pdf"'
    return response
