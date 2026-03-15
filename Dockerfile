FROM python:3.12-slim

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (Docker cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source
COPY . .

# Create temp directory
RUN mkdir -p temp_downloads

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD pgrep -f "python bot.py" || exit 1

# Non-root user
RUN adduser --disabled-password --no-create-home botuser && \
    chown -R botuser:botuser /app
USER botuser

# Run bot
CMD ["python", "-u", "bot.py"]
