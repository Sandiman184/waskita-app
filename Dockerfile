# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies to a temporary location
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Final
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV DOTENV_OVERRIDE=True
# Add backend directory to PYTHONPATH
ENV PYTHONPATH=/app/src/backend

# Model paths
ENV WORD2VEC_MODEL_PATH=/app/models/embeddings/word2vec_model.joblib

# Create non-root user
RUN groupadd -r waskita && useradd -r -g waskita waskita

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq5 \
    curl \
    bash \
    ca-certificates \
    openssl \
    && rm -rf /var/lib/apt/lists/*
    
# Update CA certificates
RUN update-ca-certificates

# Copy installed python packages from builder
COPY --from=builder /install /usr/local

# Copy source code
COPY src/ src/
COPY docker/init_database.py ./init_database.py
COPY docker-entrypoint.sh .
COPY database_schema.sql .

# Create directories and set permissions
RUN mkdir -p logs uploads static/uploads data models/embeddings models/classifiers models/label_encoder models/indobert \
    && chown -R waskita:waskita /app \
    && chmod -R 755 /app \
    && chmod -R 775 uploads logs static/uploads data models \
    && chmod -R 775 /app/logs \
    && chmod +x docker-entrypoint.sh

# Switch to backend directory
WORKDIR /app/src/backend

USER waskita

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]

CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
