# Use a modern, slim Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code and all necessary files
COPY . .

# Create logs directory and ensure permissions
RUN mkdir -p logs

# Expose no ports (Discord bots are outbound only)

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "link_mover_direct_channel.py"] 