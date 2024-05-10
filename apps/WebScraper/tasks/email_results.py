from django.core.mail import EmailMessage
from django.conf import settings
from celery import shared_task
import logging

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

email_host_user = settings.EMAIL_HOST_USER


@shared_task
def send_results_via_email(email, pdf_path, excel_path):
    logger.info(f"Preparing to send results via email to {email}")
    subject = "Your Real Estate Analysis Results"
    body = "Attached are your requested real estate analysis results."
    email_message = EmailMessage(subject, body, email_host_user, [email])  # To email

    # Attach files
    try:
        with open(pdf_path, "rb") as pdf_file:
            email_message.attach(
                "Real_Estate_Listings.pdf", pdf_file.read(), "application/pdf"
            )
            logger.debug("PDF attached successfully.")

        with open(excel_path, "rb") as excel_file:
            email_message.attach(
                "PropertyListings.xlsx", excel_file.read(), "application/vnd.ms-excel"
            )
            logger.debug("Excel file attached successfully.")

        # Send email
        email_message.send()
        logger.info("Email sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        raise
