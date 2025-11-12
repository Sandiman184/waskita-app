# Dockerfile untuk aplikasi Waskita
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV DOTENV_OVERRIDE=True
# Model paths for container
ENV WORD2VEC_MODEL_PATH=/app/models/embeddings/wiki_word2vec_csv_updated.model
ENV NAIVE_BAYES_MODEL1_PATH=/app/models/navesbayes/naive_bayes_model1.pkl
ENV NAIVE_BAYES_MODEL2_PATH=/app/models/navesbayes/naive_bayes_model2.pkl
ENV NAIVE_BAYES_MODEL3_PATH=/app/models/navesbayes/naive_bayes_model3.pkl

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
        bash \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY app.py .
COPY security_middleware.py .
COPY security_logger.py .
COPY requirements.txt .
COPY init_database.py .
COPY database_schema.sql .
COPY docker-entrypoint.sh .
COPY static/ static/
COPY templates/ templates/
COPY models/ models/
COPY utils.py .
COPY routes.py .
COPY config.py .
COPY models.py .
COPY models_otp.py .
COPY otp_routes.py .
COPY scheduler.py .
COPY email_service.py .
COPY security_utils.py .

# Normalize Windows line-endings and make entrypoint executable
# Guard init_admin.sh to avoid build failure if the file is omitted
RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh


# Create necessary directories with proper permissions
RUN mkdir -p uploads logs static/uploads data \
    && chown -R waskita:waskita /app \
    && chmod -R 755 /app \
    && chmod -R 775 uploads logs static/uploads data

# Switch to non-root user
USER waskita

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1


# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run the application
CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]