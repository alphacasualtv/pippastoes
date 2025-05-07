# Use a modern, slim Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements.txt first to leverage Docker caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code and all necessary files
COPY . .

# Create logs directory and ensure permissions (important for volume mounts)
RUN mkdir -p logs && chmod -R 755 logs

# Copy .env file (optional, if not using Docker environment variables)
COPY .env .env

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Run as non-root user for security
RUN useradd -m botuser
USER botuser

# Expose no ports (Discord bots are outbound only)

# Default command
CMD ["python", "link_mover_direct_channel.py"]