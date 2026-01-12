import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PyPDF2 import PdfMerger, PdfReader
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

    def has_columns(df, *cols):
        """Check if dataframe has all required columns with non-null data."""
        for col in cols:
            if col not in df.columns:
                return False
            if df[col].dropna().empty:
                return False
        return True

    with PdfPages(pdf_filename) as pdf:
        # Plot 1: Histogram of Listing Prices
        if has_columns(dataframe, "Listing Price"):
            plt.figure(figsize=(10, 6))
            plt.hist(
                dataframe["Listing Price"].dropna(), bins=30, color="skyblue", edgecolor="black"
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
        else:
            logger.warning("Skipping Plot 1: Missing 'Listing Price' column")

        # Plot 2: Scatter Plot of Home Size vs. Listing Price
        if has_columns(dataframe, "Home Size", "Listing Price"):
            plt.figure(figsize=(10, 6))
            plot_df = dataframe[["Home Size", "Listing Price"]].dropna()
            plt.scatter(
                plot_df["Home Size"],
                plot_df["Listing Price"],
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
        else:
            logger.warning("Skipping Plot 2: Missing 'Home Size' or 'Listing Price' column")

        # Plot 3: Bar Chart of Property Types
        if has_columns(dataframe, "Property Type"):
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
        else:
            logger.warning("Skipping Plot 3: Missing 'Property Type' column")

        # Plot 4: Box Plot for Prices by Property Type
        if has_columns(dataframe, "Listing Price", "Property Type"):
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
        else:
            logger.warning("Skipping Plot 4: Missing 'Listing Price' or 'Property Type' column")

        # Plot 5: Scatter Plot of Year Built vs. Listing Price (replacing Time on Market)
        if has_columns(dataframe, "Year Built", "Listing Price"):
            plt.figure(figsize=(10, 6))
            plot_df = dataframe[["Year Built", "Listing Price"]].dropna()
            plt.scatter(
                plot_df["Year Built"],
                plot_df["Listing Price"],
                color="orange",
                alpha=0.5,
            )
            plt.title("Year Built vs. Listing Price")
            plt.xlabel("Year Built")
            plt.ylabel("Listing Price ($)")
            plt.grid(True)
            plt.tight_layout()
            pdf.savefig()
            plt.close()
            current_count += 1
            logger.debug(f"Plot 5 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 5: Missing 'Year Built' or 'Listing Price' column")

        # Plot 6: Bar Chart of Average Price per Square Foot by Property Type
        if has_columns(dataframe, "Property Type", "Price Per Sqft"):
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
        else:
            logger.warning("Skipping Plot 6: Missing 'Property Type' or 'Price Per Sqft' column")

        # Plot 7: Histogram of Year Built
        if has_columns(dataframe, "Year Built"):
            plt.figure(figsize=(10, 6))
            plt.hist(dataframe["Year Built"].dropna(), bins=30, color="teal", edgecolor="black")
            plt.title("Distribution of Year Built")
            plt.xlabel("Year")
            plt.ylabel("Number of Properties")
            plt.grid(True)
            plt.tight_layout()
            pdf.savefig()
            plt.close()
            current_count += 1
            logger.debug(f"Plot 7 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 7: Missing 'Year Built' column")

        # Plot 8: Bar Chart of Average Estimated Monthly Payment by Property Type
        if has_columns(dataframe, "Property Type", "Estimated Monthly Payment"):
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
        else:
            logger.warning("Skipping Plot 8: Missing 'Property Type' or 'Estimated Monthly Payment' column")

    logger.info(f"Generated {current_count} plots and saved to {pdf_filename}")
    return pdf_filename


# Column mapping from model field names to display names for visualization
COLUMN_MAPPING = {
    'market_value': 'Listing Price',
    'building_sqft': 'Home Size',
    'property_type': 'Property Type',
    'last_scraped': 'Time on Market',
    'year_built': 'Year Built',
    'tax_amount': 'Tax Amount',
    'assessed_value': 'Assessed Value',
    'land_size': 'Land Size',
    'bedrooms': 'Bedrooms',
    'bathrooms': 'Bathrooms',
    'city': 'City',
    'zip_code': 'ZIP Code',
}


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
    df = pd.read_excel(excel_path, sheet_name=0)  # Use first sheet (default name varies)

    # Rename columns from model field names to display names
    df = df.rename(columns=COLUMN_MAPPING)

    # Calculate Price Per Sqft if we have the required columns
    if 'Listing Price' in df.columns and 'Home Size' in df.columns:
        df['Price Per Sqft'] = df.apply(
            lambda row: row['Listing Price'] / row['Home Size']
            if pd.notna(row['Home Size']) and row['Home Size'] > 0 else None,
            axis=1
        )

    # Estimate monthly payment (rough estimate: price * 0.006 for mortgage + taxes + insurance)
    if 'Listing Price' in df.columns:
        df['Estimated Monthly Payment'] = df['Listing Price'].apply(
            lambda x: x * 0.006 if pd.notna(x) else None
        )

    total_plots = 8  # Increased the total number of plots
    current_plot = 0
    logger.debug("Starting to generate plots for data analysis")
    analysis_pdf = generate_plots_and_pdf(df, current_plot)
    final_pdf = concatenate_pdfs("Real_Estate_Listings.pdf", analysis_pdf)
    progress_recorder = ProgressRecorder(self)

    # Increment progress from 75 to 100
    for i in range(75, 101):
        progress_recorder.set_progress(
            current_plot, 100, description=f"Generating visual data ({i}%)"
        )

    # Get the property count from database
    from apps.WebScraper.models import PropertyListing
    property_count = PropertyListing.objects.count()

    return {
        'pdf': f'/static/reports/{final_pdf}' if final_pdf else None,
        'excel': f'/static/reports/{excel_path}' if excel_path else None,
        'pdf_path': final_pdf,
        'excel_path': excel_path,
        'count': property_count,
        'status': 'Analysis complete'
    }


def concatenate_pdfs(base_pdf, analysis_pdf):
    logger.info("Concatenating base PDF and analysis PDF into a single document")
    output_pdf = "Real_Estate_Report.pdf"
    merger = PdfMerger()

    # Check if base PDF exists and has pages
    try:
        base_reader = PdfReader(base_pdf)
        if len(base_reader.pages) > 0:
            merger.append(base_pdf)
            logger.debug(f"Added base PDF with {len(base_reader.pages)} pages")
        else:
            logger.warning("Base PDF has no pages, skipping")
    except Exception as e:
        logger.warning(f"Could not read base PDF: {e}")

    # Check if analysis PDF exists and has pages
    try:
        analysis_reader = PdfReader(analysis_pdf)
        if len(analysis_reader.pages) > 0:
            merger.append(analysis_pdf)
            logger.debug(f"Added analysis PDF with {len(analysis_reader.pages)} pages")
        else:
            logger.warning("Analysis PDF has no pages, skipping")
    except Exception as e:
        logger.warning(f"Could not read analysis PDF: {e}")

    # Only write if we have pages to write
    if len(merger.pages) > 0:
        merger.write(output_pdf)
        merger.close()
        logger.info(f"Final PDF report generated at {output_pdf}")
        return output_pdf
    else:
        merger.close()
        logger.warning("No pages to merge, returning base PDF path")
        return base_pdf
