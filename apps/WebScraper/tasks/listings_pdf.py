import logging
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    KeepTogether,
    PageBreak,
)
from reportlab.lib.units import inch
from celery import shared_task
from celery_progress.backend import ProgressRecorder

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def get_custom_styles():
    logger.debug("Configuring custom styles for the PDF")
    styles = {
        "title": ParagraphStyle(
            name="title",
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor("#333333"),
        ),
        "heading": ParagraphStyle(
            name="heading",
            fontSize=14,
            leading=18,
            spaceAfter=6,
            textColor=colors.HexColor("#666666"),
        ),
        "body": ParagraphStyle(
            name="body",
            fontSize=12,
            leading=14,
            spaceAfter=12,
            textColor=colors.darkblue,
        ),
        "link": ParagraphStyle(
            name="link", fontSize=12, leading=14, textColor=colors.blue
        ),
    }
    return styles


@shared_task(bind=True)
def generate_listing_pdf(self, sort_result):
    logger.info("Generating PDF for property listings")

    # Extract data from chain result
    sorted_properties = sort_result.get('sorted_properties', [])
    columns = sort_result.get('columns', [])
    excel_path = sort_result.get('excel_path', 'PropertyListings.xlsx')

    filename = "Real_Estate_Listings.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    story = []
    styles = get_custom_styles()

    progress_recorder = ProgressRecorder(self)
    total_properties = len(sorted_properties)
    completed_properties = 0
    logger.debug(f"Total properties to process: {total_properties}")

    for count, property_tuple in enumerate(sorted_properties, start=1):
        property_dict = dict(zip([col[0] for col in columns], property_tuple))

        if not isinstance(property_dict, dict):
            logger.error(f"Invalid property format at index {count}: {property_tuple}")
            continue

        logger.debug(f"Processing property {count}")

        # Image handling
        if "image_of_property" in property_dict:
            try:
                img = Image(property_dict["image_of_property"])
                img.drawHeight = 2 * inch
                img.drawWidth = 3 * inch
                img.hAlign = "CENTER"
                story.append(KeepTogether([img]))
            except Exception as e:
                logger.error(f"Failed to add image for property {count}: {str(e)}")
                story.append(Paragraph("No image available", styles["body"]))

        # Constructing the details section directly from the property dictionary
        details = f"<para style='title'>Property Listing</para>"
        details += "".join(
            f"<para style='heading'>{key.replace('_', ' ').title()}:</para> <para style='body'>{value}</para>"
            for key, value in property_dict.items()
            if key != "image_of_property"
        )
        details += f"<para style='link'><link href='{property_dict.get('link', '#')}' color='blue'>More Details</link></para>"
        story.append(Paragraph(details, styles["body"]))
        story.append(Spacer(1, 12))
        story.append(PageBreak())
        
        completed_properties += 1
        progress = 50 + int((completed_properties / total_properties) * 25)
        progress_recorder.set_progress(progress, 100, description="Generating listing PDF")

    try:
        doc.build(story)
        progress_recorder.set_progress(75, 100, description="Listing PDF generated")
        logger.info(f"PDF generated successfully at {filename}")
        return {
            "status": "PDF generated successfully",
            "pdf_path": filename,
            "excel_path": excel_path
        }
    except Exception as e:
        logger.error(f"Failed to generate PDF: {str(e)}")
        return {
            "status": f"Failed to generate PDF: {str(e)}",
            "pdf_path": None,
            "excel_path": excel_path
        }
