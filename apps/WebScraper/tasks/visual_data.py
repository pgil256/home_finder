import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PyPDF2 import PdfFileMerger, PdfFileReader
from django.conf import settings
import logging
from celery import shared_task
from celery_progress.backend import ProgressRecorder


# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

excel_path = settings.EXCEL_PATH


def generate_plots_and_pdf(dataframe, current_count):
    pdf_filename = "Data_Analysis.pdf"
    current_count = 0
    logger.info("Starting to generate plots and save them to a PDF")

    with PdfPages(pdf_filename) as pdf:
        # Plot 1: Histogram of Listing Prices
        plt.figure(figsize=(10, 6))
        plt.hist(
            dataframe["Listing Price"], bins=30, color="skyblue", edgecolor="black"
        )
        plt.title("Distribution of Listing Prices")
        plt.xlabel("Price ($)")
        plt.ylabel("Number of Properties")
        plt.grid(True)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 1 saved, current count: {current_count}")

        # Plot 2: Scatter Plot of Home Size vs. Listing Price
        plt.figure(figsize=(10, 6))
        plt.scatter(
            dataframe["Home Size"],
            dataframe["Listing Price"],
            color="purple",
            alpha=0.5,
        )
        plt.title("Home Size vs. Listing Price")
        plt.xlabel("Home Size (sqft)")
        plt.ylabel("Listing Price ($)")
        plt.grid(True)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 2 saved, current count: {current_count}")

        # Plot 3: Bar Chart of Property Types
        plt.figure(figsize=(10, 6))
        property_types = dataframe["Property Type"].value_counts()
        property_types.plot(kind="bar", color="teal")
        plt.title("Number of Listings by Property Type")
        plt.xlabel("Property Type")
        plt.ylabel("Number of Listings")
        plt.xticks(rotation=45)
        plt.grid(axis="y", linestyle="--", alpha=0.7)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 3 saved, current count: {current_count}")

        # Plot 4: Box Plot for Prices by Property Type
        plt.figure(figsize=(12, 8))
        dataframe.boxplot(
            column="Listing Price", by="Property Type", grid=True, patch_artist=True
        )
        plt.title("Listing Prices by Property Type")
        plt.xlabel("Property Type")
        plt.ylabel("Listing Price ($)")
        plt.suptitle("")
        plt.xticks(rotation=45)
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 4 saved, current count: {current_count}")

        # Plot 5: Scatter Plot of Time on Market vs. Listing Price
        plt.figure(figsize=(10, 6))
        plt.scatter(
            dataframe["Time on Market"],
            dataframe["Listing Price"],
            color="orange",
            alpha=0.5,
        )
        plt.title("Time on Market vs. Listing Price")
        plt.xlabel("Time on Market (days)")
        plt.ylabel("Listing Price ($)")
        plt.grid(True)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 5 saved, current count: {current_count}")

        # Plot 6: Bar Chart of Average Price per Square Foot by Property Type
        plt.figure(figsize=(12, 8))
        avg_price_per_sqft = dataframe.groupby("Property Type")["Price Per Sqft"].mean()
        avg_price_per_sqft.plot(kind="bar", color="skyblue")
        plt.title("Average Price per Square Foot by Property Type")
        plt.xlabel("Property Type")
        plt.ylabel("Average Price per Square Foot ($)")
        plt.xticks(rotation=45)
        plt.grid(axis="y", linestyle="--", alpha=0.7)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 6 saved, current count: {current_count}")

        # Plot 7: Histogram of Year Built
        plt.figure(figsize=(10, 6))
        plt.hist(dataframe["Year Built"], bins=30, color="teal", edgecolor="black")
        plt.title("Distribution of Year Built")
        plt.xlabel("Year")
        plt.ylabel("Number of Properties")
        plt.grid(True)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 7 saved, current count: {current_count}")

        # Plot 8: Bar Chart of Average Estimated Monthly Payment by Property Type
        plt.figure(figsize=(12, 8))
        avg_monthly_payment = dataframe.groupby("Property Type")[
            "Estimated Monthly Payment"
        ].mean()
        avg_monthly_payment.plot(kind="bar", color="purple")
        plt.title("Average Estimated Monthly Payment by Property Type")
        plt.xlabel("Property Type")
        plt.ylabel("Average Estimated Monthly Payment ($)")
        plt.xticks(rotation=45)
        plt.grid(axis="y", linestyle="--", alpha=0.7)
        plt.tight_layout()
        pdf.savefig()
        plt.close()
        current_count += 1
        logger.debug(f"Plot 8 saved, current count: {current_count}")

    logger.info(f"All plots generated and saved to {pdf_filename}")
    return pdf_filename


@shared_task(bind=True)
def analyze_data(self, pdf_result):
    # Extract file paths from chain result
    pdf_path = pdf_result.get('pdf_path') if isinstance(pdf_result, dict) else None
    excel_path = pdf_result.get('excel_path', 'PropertyListings.xlsx') if isinstance(pdf_result, dict) else 'PropertyListings.xlsx'

    if not pdf_path:
        logger.warning("No PDF path provided, skipping visualization")
        return {
            'pdf_path': pdf_path,
            'excel_path': excel_path,
            'status': 'Skipped visualization - no PDF available'
        }

    logger.info(f"Loading data from Excel for analysis: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name="Listings")

    total_plots = 8  # Increased the total number of plots
    current_plot = 0
    logger.debug("Starting to generate plots for data analysis")
    analysis_pdf = generate_plots_and_pdf(df, self, current_plot)
    final_pdf = concatenate_pdfs("Real_Estate_Listings.pdf", analysis_pdf)
    progress_recorder = ProgressRecorder(self)

    # Increment progress from 75 to 100
    for i in range(75, 101):
        progress_recorder.set_progress(
            current_plot, 100, description=f"Generating visual data ({i}%)"
        )

    return {
        'pdf_path': final_pdf,
        'excel_path': excel_path,
        'status': 'Analysis complete'
    }


def concatenate_pdfs(base_pdf, analysis_pdf):
    logger.info("Concatenating base PDF and analysis PDF into a single document")
    merger = PdfFileMerger()
    with open(base_pdf, "rb") as base, open(analysis_pdf, "rb") as analysis:
        merger.append(PdfFileReader(base))
        merger.append(PdfFileReader(analysis))
    output_pdf = "Real_Estate_Report.pdf"
    with open(output_pdf, "wb") as outfile:
        merger.write(outfile)
    logger.info(f"Final PDF report generated at {output_pdf}")
    return output_pdf
