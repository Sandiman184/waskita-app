# Dockerfile untuk aplikasi Waskita
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Create non-root user
RUN groupadd -r waskita && useradd -r -g waskita waskita

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        python3-dev \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Make initialization scripts executable
RUN chmod +x init_admin.sh docker-entrypoint.sh

# Create necessary directories with proper permissions
RUN mkdir -p uploads logs static/uploads data \
    && chown -R waskita:waskita /app \
    && chmod -R 755 /app \
    && chmod -R 777 uploads logs static/uploads data

# Switch to non-root user
USER waskita

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run the application
CMD ["python", "app.py"]