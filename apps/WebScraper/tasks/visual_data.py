import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
from PyPDF2 import PdfMerger, PdfReader
from django.conf import settings
import logging
from celery import shared_task
from celery_progress.backend import ProgressRecorder


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

REPORTS_DIR = os.path.join(settings.MEDIA_ROOT, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

# Professional color palette matching the PDF
COLORS = {
    'primary': '#1e3a5f',
    'secondary': '#2c5282',
    'accent': '#38a169',
    'warning': '#dd6b20',
    'danger': '#c53030',
    'text': '#2d3748',
    'text_light': '#718096',
    'bg_light': '#f7fafc',
    'border': '#e2e8f0',
}

# Chart color palette
CHART_COLORS = [
    '#1e3a5f',  # Navy
    '#38a169',  # Green
    '#dd6b20',  # Orange
    '#2c5282',  # Medium blue
    '#805ad5',  # Purple
    '#d69e2e',  # Gold
    '#319795',  # Teal
    '#c53030',  # Red
]


def setup_plot_style():
    """Configure matplotlib with professional styling."""
    plt.style.use('seaborn-v0_8-whitegrid')

    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
        'font.size': 10,
        'axes.titlesize': 14,
        'axes.titleweight': 'bold',
        'axes.titlecolor': COLORS['primary'],
        'axes.labelsize': 11,
        'axes.labelcolor': COLORS['text'],
        'axes.edgecolor': COLORS['border'],
        'axes.linewidth': 1,
        'axes.grid': True,
        'axes.facecolor': 'white',
        'grid.color': COLORS['border'],
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
        'grid.alpha': 0.7,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'xtick.color': COLORS['text_light'],
        'ytick.color': COLORS['text_light'],
        'legend.fontsize': 9,
        'legend.frameon': True,
        'legend.framealpha': 0.9,
        'legend.edgecolor': COLORS['border'],
        'figure.facecolor': 'white',
        'figure.titlesize': 16,
        'figure.titleweight': 'bold',
    })


def format_currency_axis(ax, axis='y'):
    """Format axis with currency labels."""
    from matplotlib.ticker import FuncFormatter
    formatter = FuncFormatter(lambda x, p: f'${x/1000:.0f}K' if x >= 1000 else f'${x:.0f}')
    if axis == 'y':
        ax.yaxis.set_major_formatter(formatter)
    else:
        ax.xaxis.set_major_formatter(formatter)


def add_value_labels(ax, bars, format_type='number'):
    """Add value labels on top of bars."""
    for bar in bars:
        height = bar.get_height()
        if format_type == 'currency':
            label = f'${height/1000:.0f}K' if height >= 1000 else f'${height:.0f}'
        else:
            label = f'{int(height)}'
        ax.annotate(label,
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom',
                    fontsize=8, color=COLORS['text_light'])


def generate_plots_and_pdf(dataframe, current_count):
    pdf_filename = "Data_Analysis.pdf"
    pdf_filepath = os.path.join(REPORTS_DIR, pdf_filename)
    current_count = 0

    setup_plot_style()
    logger.info("Starting to generate plots and save them to a PDF")

    def has_columns(df, *cols):
        """Check if dataframe has all required columns with non-null data."""
        for col in cols:
            if col not in df.columns:
                return False
            if df[col].dropna().empty:
                return False
        return True

    with PdfPages(pdf_filepath) as pdf:
        # Title page for analysis section
        fig = plt.figure(figsize=(10, 6))
        fig.text(0.5, 0.6, 'Market Analysis', ha='center', va='center',
                 fontsize=32, fontweight='bold', color=COLORS['primary'])
        fig.text(0.5, 0.45, 'Property Data Visualizations', ha='center', va='center',
                 fontsize=16, color=COLORS['text_light'])
        fig.text(0.5, 0.25, 'The following charts provide insights into\nproperty values, distributions, and market trends.',
                 ha='center', va='center', fontsize=11, color=COLORS['text_light'])
        plt.axis('off')
        pdf.savefig(fig, facecolor='white')
        plt.close()

        # Plot 1: Histogram of Listing Prices
        if has_columns(dataframe, "Listing Price"):
            fig, ax = plt.subplots(figsize=(10, 6))
            prices = dataframe["Listing Price"].dropna()
            n, bins, patches = ax.hist(prices, bins=20, color=COLORS['primary'],
                                        edgecolor='white', linewidth=1, alpha=0.85)

            ax.set_title('Distribution of Listing Prices', pad=20)
            ax.set_xlabel('Price')
            ax.set_ylabel('Number of Properties')
            format_currency_axis(ax, 'x')

            # Add mean line
            mean_price = prices.mean()
            ax.axvline(mean_price, color=COLORS['accent'], linestyle='--', linewidth=2, label=f'Mean: ${mean_price:,.0f}')
            ax.legend(loc='upper right')

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 1 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 1: Missing 'Listing Price' column")

        # Plot 2: Scatter Plot of Home Size vs. Listing Price
        if has_columns(dataframe, "Home Size", "Listing Price"):
            fig, ax = plt.subplots(figsize=(10, 6))
            plot_df = dataframe[["Home Size", "Listing Price"]].dropna()

            scatter = ax.scatter(
                plot_df["Home Size"],
                plot_df["Listing Price"],
                c=COLORS['secondary'],
                alpha=0.6,
                s=80,
                edgecolors='white',
                linewidth=0.5,
            )

            ax.set_title('Home Size vs. Listing Price', pad=20)
            ax.set_xlabel('Home Size (sq ft)')
            ax.set_ylabel('Listing Price')
            format_currency_axis(ax, 'y')

            # Add trend line if enough data
            if len(plot_df) > 2:
                import numpy as np
                z = np.polyfit(plot_df["Home Size"], plot_df["Listing Price"], 1)
                p = np.poly1d(z)
                x_line = np.linspace(plot_df["Home Size"].min(), plot_df["Home Size"].max(), 100)
                ax.plot(x_line, p(x_line), color=COLORS['accent'], linestyle='--',
                       linewidth=2, label='Trend Line', alpha=0.8)
                ax.legend(loc='upper left')

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 2 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 2: Missing 'Home Size' or 'Listing Price' column")

        # Plot 3: Bar Chart of Property Types
        if has_columns(dataframe, "Property Type"):
            fig, ax = plt.subplots(figsize=(10, 6))
            property_types = dataframe["Property Type"].value_counts()

            bars = ax.bar(range(len(property_types)), property_types.values,
                         color=[CHART_COLORS[i % len(CHART_COLORS)] for i in range(len(property_types))],
                         edgecolor='white', linewidth=1)

            ax.set_title('Number of Listings by Property Type', pad=20)
            ax.set_xlabel('Property Type')
            ax.set_ylabel('Number of Listings')
            ax.set_xticks(range(len(property_types)))
            ax.set_xticklabels(property_types.index, rotation=45, ha='right')

            add_value_labels(ax, bars)

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 3 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 3: Missing 'Property Type' column")

        # Plot 4: Box Plot for Prices by Property Type
        if has_columns(dataframe, "Listing Price", "Property Type"):
            fig, ax = plt.subplots(figsize=(12, 7))

            property_types = dataframe["Property Type"].unique()
            data_to_plot = [dataframe[dataframe["Property Type"] == pt]["Listing Price"].dropna()
                          for pt in property_types]
            data_to_plot = [d for d in data_to_plot if len(d) > 0]
            labels = [pt for pt, d in zip(property_types, [dataframe[dataframe["Property Type"] == pt]["Listing Price"].dropna() for pt in property_types]) if len(d) > 0]

            if data_to_plot:
                bp = ax.boxplot(data_to_plot, patch_artist=True, labels=labels)

                for i, box in enumerate(bp['boxes']):
                    box.set_facecolor(CHART_COLORS[i % len(CHART_COLORS)])
                    box.set_alpha(0.7)
                for whisker in bp['whiskers']:
                    whisker.set_color(COLORS['text_light'])
                for cap in bp['caps']:
                    cap.set_color(COLORS['text_light'])
                for median in bp['medians']:
                    median.set_color('white')
                    median.set_linewidth(2)

                ax.set_title('Listing Prices by Property Type', pad=20)
                ax.set_xlabel('Property Type')
                ax.set_ylabel('Listing Price')
                format_currency_axis(ax, 'y')
                plt.xticks(rotation=45, ha='right')

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 4 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 4: Missing 'Listing Price' or 'Property Type' column")

        # Plot 5: Year Built vs. Listing Price
        if has_columns(dataframe, "Year Built", "Listing Price"):
            fig, ax = plt.subplots(figsize=(10, 6))
            plot_df = dataframe[["Year Built", "Listing Price"]].dropna()

            scatter = ax.scatter(
                plot_df["Year Built"],
                plot_df["Listing Price"],
                c=COLORS['warning'],
                alpha=0.6,
                s=80,
                edgecolors='white',
                linewidth=0.5,
            )

            ax.set_title('Year Built vs. Listing Price', pad=20)
            ax.set_xlabel('Year Built')
            ax.set_ylabel('Listing Price')
            format_currency_axis(ax, 'y')

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 5 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 5: Missing 'Year Built' or 'Listing Price' column")

        # Plot 6: Average Price per Sqft by Property Type
        if has_columns(dataframe, "Property Type", "Price Per Sqft"):
            fig, ax = plt.subplots(figsize=(12, 7))
            avg_price_per_sqft = dataframe.groupby("Property Type")["Price Per Sqft"].mean().sort_values(ascending=False)

            bars = ax.bar(range(len(avg_price_per_sqft)), avg_price_per_sqft.values,
                         color=COLORS['accent'], edgecolor='white', linewidth=1, alpha=0.85)

            ax.set_title('Average Price per Square Foot by Property Type', pad=20)
            ax.set_xlabel('Property Type')
            ax.set_ylabel('Average Price per Sq Ft')
            ax.set_xticks(range(len(avg_price_per_sqft)))
            ax.set_xticklabels(avg_price_per_sqft.index, rotation=45, ha='right')

            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.annotate(f'${height:.0f}',
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom',
                           fontsize=9, fontweight='bold', color=COLORS['text'])

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 6 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 6: Missing 'Property Type' or 'Price Per Sqft' column")

        # Plot 7: Year Built Distribution
        if has_columns(dataframe, "Year Built"):
            fig, ax = plt.subplots(figsize=(10, 6))
            years = dataframe["Year Built"].dropna()

            n, bins, patches = ax.hist(years, bins=15, color=COLORS['secondary'],
                                        edgecolor='white', linewidth=1, alpha=0.85)

            ax.set_title('Distribution of Year Built', pad=20)
            ax.set_xlabel('Year')
            ax.set_ylabel('Number of Properties')

            # Highlight decades
            for i, patch in enumerate(patches):
                decade_start = int(bins[i] // 10 * 10)
                color_idx = (decade_start - 1960) // 10 % len(CHART_COLORS)
                patch.set_facecolor(CHART_COLORS[abs(color_idx)])
                patch.set_alpha(0.8)

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 7 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 7: Missing 'Year Built' column")

        # Plot 8: Monthly Payment by Property Type
        if has_columns(dataframe, "Property Type", "Estimated Monthly Payment"):
            fig, ax = plt.subplots(figsize=(12, 7))
            avg_monthly = dataframe.groupby("Property Type")["Estimated Monthly Payment"].mean().sort_values(ascending=False)

            bars = ax.bar(range(len(avg_monthly)), avg_monthly.values,
                         color=COLORS['primary'], edgecolor='white', linewidth=1, alpha=0.85)

            ax.set_title('Average Estimated Monthly Payment by Property Type', pad=20)
            ax.set_xlabel('Property Type')
            ax.set_ylabel('Estimated Monthly Payment')
            ax.set_xticks(range(len(avg_monthly)))
            ax.set_xticklabels(avg_monthly.index, rotation=45, ha='right')
            format_currency_axis(ax, 'y')

            add_value_labels(ax, bars, 'currency')

            plt.tight_layout()
            pdf.savefig(fig, facecolor='white')
            plt.close()
            current_count += 1
            logger.debug(f"Plot 8 saved, current count: {current_count}")
        else:
            logger.warning("Skipping Plot 8: Missing 'Property Type' or 'Estimated Monthly Payment' column")

    logger.info(f"Generated {current_count} plots and saved to {pdf_filepath}")
    return pdf_filepath


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
    pdf_path = pdf_result.get('pdf_path') if isinstance(pdf_result, dict) else None
    excel_path = pdf_result.get('excel_path') if isinstance(pdf_result, dict) else None

    if not excel_path:
        excel_path = os.path.join(REPORTS_DIR, 'PropertyListings.xlsx')

    if not pdf_path:
        logger.warning("No PDF path provided, skipping visualization")
        excel_filename = os.path.basename(excel_path)
        return {
            'pdf_path': pdf_path,
            'excel_path': excel_path,
            'pdf': None,
            'excel': f'/media/reports/{excel_filename}' if os.path.exists(excel_path) else None,
            'status': 'Skipped visualization - no PDF available'
        }

    logger.info(f"Loading data from Excel for analysis: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name=0)

    df = df.rename(columns=COLUMN_MAPPING)

    if 'Listing Price' in df.columns and 'Home Size' in df.columns:
        df['Price Per Sqft'] = df.apply(
            lambda row: row['Listing Price'] / row['Home Size']
            if pd.notna(row['Home Size']) and row['Home Size'] > 0 else None,
            axis=1
        )

    if 'Listing Price' in df.columns:
        df['Estimated Monthly Payment'] = df['Listing Price'].apply(
            lambda x: x * 0.006 if pd.notna(x) else None
        )

    total_plots = 8
    current_plot = 0
    logger.debug("Starting to generate plots for data analysis")
    analysis_pdf = generate_plots_and_pdf(df, current_plot)
    final_pdf = concatenate_pdfs(pdf_path, analysis_pdf)
    progress_recorder = ProgressRecorder(self)

    for i in range(75, 101):
        progress_recorder.set_progress(
            current_plot, 100, description=f"Generating visual data ({i}%)"
        )

    from apps.WebScraper.models import PropertyListing
    property_count = PropertyListing.objects.count()

    pdf_filename = os.path.basename(final_pdf) if final_pdf else None
    excel_filename = os.path.basename(excel_path) if excel_path else None

    return {
        'pdf': f'/media/reports/{pdf_filename}' if pdf_filename else None,
        'excel': f'/media/reports/{excel_filename}' if excel_filename else None,
        'pdf_path': final_pdf,
        'excel_path': excel_path,
        'count': property_count,
        'status': 'Analysis complete'
    }


def concatenate_pdfs(base_pdf, analysis_pdf):
    logger.info("Concatenating base PDF and analysis PDF into a single document")
    output_filename = "Real_Estate_Report.pdf"
    output_filepath = os.path.join(REPORTS_DIR, output_filename)
    merger = PdfMerger()

    try:
        base_reader = PdfReader(base_pdf)
        if len(base_reader.pages) > 0:
            merger.append(base_pdf)
            logger.debug(f"Added base PDF with {len(base_reader.pages)} pages")
        else:
            logger.warning("Base PDF has no pages, skipping")
    except Exception as e:
        logger.warning(f"Could not read base PDF: {e}")

    try:
        analysis_reader = PdfReader(analysis_pdf)
        if len(analysis_reader.pages) > 0:
            merger.append(analysis_pdf)
            logger.debug(f"Added analysis PDF with {len(analysis_reader.pages)} pages")
        else:
            logger.warning("Analysis PDF has no pages, skipping")
    except Exception as e:
        logger.warning(f"Could not read analysis PDF: {e}")

    if len(merger.pages) > 0:
        merger.write(output_filepath)
        merger.close()
        logger.info(f"Final PDF report generated at {output_filepath}")
        return output_filepath
    else:
        merger.close()
        logger.warning("No pages to merge, returning base PDF path")
        return base_pdf
