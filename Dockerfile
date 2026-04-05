FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright (Chromium + Firefox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install both Chromium and Firefox browsers for Playwright
# Firefox has better anti-detection properties (TLS fingerprint)
RUN playwright install chromium && playwright install firefox

# Copy application code
COPY . .

# Create directories for database and debug
RUN mkdir -p /app/db /app/debug

# Run the bot
CMD ["python", "-m", "bot.main"]
