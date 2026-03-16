FROM python:3.12-slim

# Install ffmpeg + aria2c (parallel download accelerator)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg aria2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (Docker cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure yt-dlp is latest (YouTube breaks old versions fast)
RUN pip install --no-cache-dir --upgrade yt-dlp

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

# Run bot with optimized Python flags
CMD ["python", "-u", "-O", "bot.py"]
