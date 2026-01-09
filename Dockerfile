FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    wget \
    curl \
    unzip \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome for Testing (includes matching chromedriver)
RUN CHROME_VERSION=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json | jq -r '.channels.Stable.version') \
    && echo "Installing Chrome for Testing version: $CHROME_VERSION" \
    && mkdir -p /opt/chrome-for-testing \
    && wget -q -O /tmp/chrome.zip "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && unzip -q /tmp/chrome.zip -d /opt/chrome-for-testing \
    && wget -q -O /tmp/chromedriver.zip "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip -q /tmp/chromedriver.zip -d /opt/chrome-for-testing \
    && chmod +x /opt/chrome-for-testing/chrome-linux64/chrome \
    && chmod +x /opt/chrome-for-testing/chromedriver-linux64/chromedriver \
    && rm /tmp/chrome.zip /tmp/chromedriver.zip

# Install Chrome dependencies
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Chrome paths
ENV CHROME_BIN=/opt/chrome-for-testing/chrome-linux64/chrome
ENV CHROMEDRIVER_PATH=/opt/chrome-for-testing/chromedriver-linux64/chromedriver

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Make startup script executable
RUN chmod +x /app/start.sh

# Run startup script
CMD ["/app/start.sh"]
