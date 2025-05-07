# Use a modern, slim Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements.txt first to leverage Docker caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m botuser

# Copy bot code and all necessary files
COPY . .

# Create logs directory and set ownership/permissions for logs and /app
RUN mkdir -p logs && \
    chown -R botuser:botuser /app && \
    chmod -R 775 /app

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER botuser

# Expose no ports (Discord bots are outbound only)
CMD ["python", "link_mover_direct_channel.py"]
