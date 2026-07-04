# Use a modern, slim Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Create non-root user
RUN groupadd --system botgroup && \
    useradd --system --gid botgroup --create-home --shell /bin/false botuser

# Copy requirements first (better layer caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs dir and set ownership
RUN mkdir -p logs && chown -R botuser:botgroup /app

# Python settings
ENV PYTHONUNBUFFERED=1

# Run as non-root user
USER botuser

# Start the bot
CMD ["python", "link_mover_direct_channel.py"]
