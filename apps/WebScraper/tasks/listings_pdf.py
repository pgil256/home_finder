import logging
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
from reportlab.lib.units import inch
from celery import shared_task
from django.conf import settings
from celery_progress.backend import ProgressRecorder

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

REPORTS_DIR = os.path.join(settings.MEDIA_ROOT, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

# Professional color palette
COLORS = {
    'primary': colors.HexColor("#1e3a5f"),      # Navy blue
    'secondary': colors.HexColor("#2c5282"),    # Medium blue
    'accent': colors.HexColor("#38a169"),       # Green for positive
    'warning': colors.HexColor("#dd6b20"),      # Orange for warnings
    'danger': colors.HexColor("#c53030"),       # Red for alerts
    'text': colors.HexColor("#2d3748"),         # Dark gray text
    'text_light': colors.HexColor("#718096"),   # Light gray text
    'bg_light': colors.HexColor("#f7fafc"),     # Light background
    'border': colors.HexColor("#e2e8f0"),       # Border color
    'white': colors.white,
}

# Fields to hide from display
HIDDEN_FIELDS = {
    'id', 'appraiser_url', 'tax_collector_url', 'created_at',
    'last_scraped', 'image_of_property', 'garage'
}

# Field display names and formatting
FIELD_CONFIG = {
    'address': {'label': 'Address', 'section': 'location'},
    'city': {'label': 'City', 'section': 'location'},
    'zip_code': {'label': 'ZIP Code', 'section': 'location'},
    'parcel_id': {'label': 'Parcel ID', 'section': 'location'},
    'property_type': {'label': 'Property Type', 'section': 'property'},
    'bedrooms': {'label': 'Bedrooms', 'section': 'property'},
    'bathrooms': {'label': 'Bathrooms', 'section': 'property'},
    'building_sqft': {'label': 'Building Size', 'section': 'property', 'format': 'sqft'},
    'lot_sqft': {'label': 'Lot Size', 'section': 'property', 'format': 'sqft'},
    'land_size': {'label': 'Land (Acres)', 'section': 'property', 'format': 'acres'},
    'year_built': {'label': 'Year Built', 'section': 'property'},
    'stories': {'label': 'Stories', 'section': 'property'},
    'owner_name': {'label': 'Owner', 'section': 'property'},
    'market_value': {'label': 'Market Value', 'section': 'financial', 'format': 'currency'},
    'assessed_value': {'label': 'Assessed Value', 'section': 'financial', 'format': 'currency'},
    'tax_amount': {'label': 'Annual Tax', 'section': 'tax', 'format': 'currency'},
    'tax_status': {'label': 'Tax Status', 'section': 'tax'},
    'tax_year': {'label': 'Tax Year', 'section': 'tax'},
    'delinquent': {'label': 'Delinquent', 'section': 'tax', 'format': 'boolean'},
}


def format_value(value, format_type=None):
    """Format a value for display."""
    if value is None or value == 'None' or value == '':
        return '-'

    if format_type == 'currency':
        try:
            return f"${float(value):,.0f}"
        except (ValueError, TypeError):
            return str(value)
    elif format_type == 'sqft':
        try:
            return f"{int(float(value)):,} sq ft"
        except (ValueError, TypeError):
            return str(value)
    elif format_type == 'acres':
        try:
            return f"{float(value):.2f} acres"
        except (ValueError, TypeError):
            return str(value)
    elif format_type == 'boolean':
        if value is True or str(value).lower() == 'true':
            return 'Yes'
        return 'No'

    return str(value)


def get_styles():
    """Create professional styles for the PDF."""
    return {
        'cover_title': ParagraphStyle(
            name='cover_title',
            fontSize=36,
            leading=44,
            alignment=TA_CENTER,
            textColor=COLORS['primary'],
            fontName='Helvetica-Bold',
            spaceAfter=20,
        ),
        'cover_subtitle': ParagraphStyle(
            name='cover_subtitle',
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            textColor=COLORS['text_light'],
            fontName='Helvetica',
            spaceAfter=40,
        ),
        'section_header': ParagraphStyle(
            name='section_header',
            fontSize=11,
            leading=14,
            textColor=COLORS['primary'],
            fontName='Helvetica-Bold',
            spaceBefore=12,
            spaceAfter=6,
        ),
        'property_title': ParagraphStyle(
            name='property_title',
            fontSize=18,
            leading=24,
            textColor=COLORS['primary'],
            fontName='Helvetica-Bold',
            spaceAfter=4,
        ),
        'property_subtitle': ParagraphStyle(
            name='property_subtitle',
            fontSize=12,
            leading=16,
            textColor=COLORS['text_light'],
            fontName='Helvetica',
            spaceAfter=16,
        ),
        'price_large': ParagraphStyle(
            name='price_large',
            fontSize=28,
            leading=34,
            textColor=COLORS['accent'],
            fontName='Helvetica-Bold',
            alignment=TA_RIGHT,
        ),
        'label': ParagraphStyle(
            name='label',
            fontSize=9,
            leading=12,
            textColor=COLORS['text_light'],
            fontName='Helvetica',
        ),
        'value': ParagraphStyle(
            name='value',
            fontSize=11,
            leading=14,
            textColor=COLORS['text'],
            fontName='Helvetica-Bold',
        ),
        'footer': ParagraphStyle(
            name='footer',
            fontSize=8,
            leading=10,
            textColor=COLORS['text_light'],
            fontName='Helvetica',
            alignment=TA_CENTER,
        ),
    }


def create_cover_page(story, styles, property_count, search_criteria=None):
    """Create a professional cover page."""
    story.append(Spacer(1, 2*inch))

    story.append(Paragraph("PROPERTY REPORT", styles['cover_title']))
    story.append(Paragraph("Pinellas County, Florida", styles['cover_subtitle']))

    story.append(Spacer(1, 0.5*inch))

    # Report summary box
    summary_data = [
        ['Report Generated', datetime.now().strftime('%B %d, %Y')],
        ['Properties Included', str(property_count)],
    ]

    if search_criteria:
        if search_criteria.get('city'):
            summary_data.append(['City', search_criteria['city']])
        if search_criteria.get('property_type'):
            ptype = search_criteria['property_type']
            if isinstance(ptype, list):
                ptype = ', '.join(ptype)
            summary_data.append(['Property Type', ptype])

    summary_table = Table(summary_data, colWidths=[2*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), COLORS['text_light']),
        ('TEXTCOLOR', (1, 0), (1, -1), COLORS['text']),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)

    story.append(Spacer(1, 1*inch))

    # Disclaimer
    disclaimer = Paragraph(
        "Data sourced from Pinellas County Property Appraiser and Tax Collector. "
        "Information is believed to be accurate but should be independently verified.",
        ParagraphStyle(
            name='disclaimer',
            fontSize=9,
            leading=12,
            textColor=COLORS['text_light'],
            alignment=TA_CENTER,
        )
    )
    story.append(disclaimer)

    story.append(PageBreak())


def create_property_page(story, styles, property_dict, index, total):
    """Create a professional property listing page."""
    # Header with property number
    header_data = [[
        Paragraph(f"Property {index} of {total}", styles['label']),
    ]]
    header_table = Table(header_data, colWidths=[6.5*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
    ]))
    story.append(header_table)

    story.append(Spacer(1, 0.1*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=COLORS['border']))
    story.append(Spacer(1, 0.2*inch))

    # Main header with address and price
    address = property_dict.get('address', 'Address Not Available')
    city = property_dict.get('city', '')
    zip_code = property_dict.get('zip_code', '')
    location_line = f"{city}, FL {zip_code}" if city else ""

    market_value = property_dict.get('market_value')
    price_display = format_value(market_value, 'currency') if market_value else '-'

    header_left = [
        Paragraph(str(address), styles['property_title']),
        Paragraph(location_line, styles['property_subtitle']),
    ]

    # Property type badge
    prop_type = property_dict.get('property_type', '-')

    main_header = Table(
        [[header_left, Paragraph(price_display, styles['price_large'])]],
        colWidths=[4*inch, 2.5*inch]
    )
    main_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(main_header)

    story.append(Spacer(1, 0.1*inch))

    # Quick stats row
    bedrooms = property_dict.get('bedrooms', '-')
    bathrooms = property_dict.get('bathrooms', '-')
    sqft = property_dict.get('building_sqft')
    year = property_dict.get('year_built', '-')

    sqft_display = format_value(sqft, 'sqft') if sqft else '-'

    quick_stats = [
        [
            create_stat_cell('Beds', str(bedrooms) if bedrooms else '-'),
            create_stat_cell('Baths', str(bathrooms) if bathrooms else '-'),
            create_stat_cell('Sq Ft', sqft_display.replace(' sq ft', '') if sqft else '-'),
            create_stat_cell('Built', str(year) if year else '-'),
            create_stat_cell('Type', str(prop_type)[:15] if prop_type else '-'),
        ]
    ]

    stats_table = Table(quick_stats, colWidths=[1.3*inch]*5)
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLORS['bg_light']),
        ('BOX', (0, 0), (-1, -1), 1, COLORS['border']),
        ('INNERGRID', (0, 0), (-1, -1), 1, COLORS['border']),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(stats_table)

    story.append(Spacer(1, 0.3*inch))

    # Two-column detail sections
    left_sections = create_section_table(property_dict, ['financial', 'tax'], styles)
    right_sections = create_section_table(property_dict, ['property', 'location'], styles)

    detail_table = Table(
        [[left_sections, right_sections]],
        colWidths=[3.25*inch, 3.25*inch]
    )
    detail_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(detail_table)

    story.append(PageBreak())


def create_stat_cell(label, value):
    """Create a stat cell with label and value."""
    return [
        Paragraph(f'<font size="9" color="#{COLORS["text_light"].hexval()[2:]}">{label}</font>',
                  ParagraphStyle(name='stat_label', alignment=TA_CENTER)),
        Paragraph(f'<font size="12"><b>{value}</b></font>',
                  ParagraphStyle(name='stat_value', alignment=TA_CENTER, textColor=COLORS['text'])),
    ]


def create_section_table(property_dict, sections, styles):
    """Create a table with multiple sections."""
    section_names = {
        'location': 'Location Details',
        'property': 'Property Details',
        'financial': 'Valuation',
        'tax': 'Tax Information',
    }

    elements = []

    for section in sections:
        # Section header
        elements.append(Paragraph(section_names.get(section, section.title()), styles['section_header']))

        # Get fields for this section
        rows = []
        for field, config in FIELD_CONFIG.items():
            if config.get('section') == section and field in property_dict:
                value = property_dict.get(field)
                formatted = format_value(value, config.get('format'))

                # Special styling for tax status
                if field == 'tax_status':
                    status = str(value).lower() if value else ''
                    if status == 'paid':
                        formatted = f'<font color="#{COLORS["accent"].hexval()[2:]}">{formatted}</font>'
                    elif status == 'unpaid':
                        formatted = f'<font color="#{COLORS["danger"].hexval()[2:]}">{formatted}</font>'
                    elif status == 'partial':
                        formatted = f'<font color="#{COLORS["warning"].hexval()[2:]}">{formatted}</font>'

                # Special styling for delinquent
                if field == 'delinquent' and (value is True or str(value).lower() == 'true'):
                    formatted = f'<font color="#{COLORS["danger"].hexval()[2:]}"><b>Yes</b></font>'

                rows.append([config['label'], Paragraph(formatted, styles['value'])])

        if rows:
            section_table = Table(rows, colWidths=[1.2*inch, 1.8*inch])
            section_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (0, -1), 9),
                ('TEXTCOLOR', (0, 0), (0, -1), COLORS['text_light']),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(section_table)

        elements.append(Spacer(1, 0.15*inch))

    # Combine into single table cell
    wrapper = Table([[e] for e in elements], colWidths=[3.1*inch])
    wrapper.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    return wrapper


def add_page_footer(canvas, doc):
    """Add footer to each page."""
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(COLORS['text_light'])

    # Page number
    page_num = canvas.getPageNumber()
    canvas.drawCentredString(letter[0]/2, 0.5*inch, f"Page {page_num}")

    # Footer text
    canvas.drawCentredString(letter[0]/2, 0.35*inch, "Home Finder - Pinellas County Property Report")

    canvas.restoreState()


@shared_task(bind=True)
def generate_listing_pdf(self, sort_result):
    logger.info("Generating PDF for property listings")

    sorted_properties = sort_result.get('sorted_properties', [])
    columns = sort_result.get('columns', [])
    excel_path = sort_result.get('excel_path', 'PropertyListings.xlsx')
    search_criteria = sort_result.get('search_criteria', {})

    filename = "Real_Estate_Listings.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )

    story = []
    styles = get_styles()

    progress_recorder = ProgressRecorder(self)
    total_properties = len(sorted_properties)

    logger.debug(f"Total properties to process: {total_properties}")

    # Create cover page
    create_cover_page(story, styles, total_properties, search_criteria)

    # Process each property
    for count, property_tuple in enumerate(sorted_properties, start=1):
        property_dict = dict(zip([col[0] for col in columns], property_tuple))

        if not isinstance(property_dict, dict):
            logger.error(f"Invalid property format at index {count}: {property_tuple}")
            continue

        logger.debug(f"Processing property {count}")

        # Create property page
        create_property_page(story, styles, property_dict, count, total_properties)

        progress = 50 + int((count / total_properties) * 25)
        progress_recorder.set_progress(progress, 100, description="Generating listing PDF")

    try:
        doc.build(story, onFirstPage=add_page_footer, onLaterPages=add_page_footer)
        progress_recorder.set_progress(75, 100, description="Listing PDF generated")
        logger.info(f"PDF generated successfully at {filepath}")
        return {
            "status": "PDF generated successfully",
            "pdf_path": filepath,
            "excel_path": excel_path,
            "search_criteria": search_criteria,
        }
    except Exception as e:
        logger.error(f"Failed to generate PDF: {str(e)}")
        return {
            "status": f"Failed to generate PDF: {str(e)}",
            "pdf_path": None,
            "excel_path": excel_path
        }
