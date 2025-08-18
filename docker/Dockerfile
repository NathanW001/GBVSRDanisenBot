FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements_headless.txt .
RUN pip install --no-cache-dir -r requirements_headless.txt

# Copy source code and create config directory
COPY src/ ./src/
RUN mkdir -p config

# Environment variables
ENV BOT_TOKEN=""
ENV CONFIG_PATH=/app/config/config.json
ENV DB_PATH=/app/config/danisen.db
ENV PORT=8080

# Volume for persistent data
VOLUME ["/app/config"]

# Run in headless mode
CMD ["python", "src/main.py", "--headless"]