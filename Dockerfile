FROM python:3.11-slim

# Set working directory
WORKDIR /app/src

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source code
COPY src/ .

# Create necessary directories
RUN mkdir -p assets/files assets/database

# Render uses PORT env var; default to 10000 for Docker
ENV PORT=10000
EXPOSE ${PORT}

# Environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

# Run the application with dynamic port
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
