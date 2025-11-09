#!/bin/bash
set -e

# Docker entrypoint script for Waskita application
# Handles database initialization, environment setup, and application startup

echo "🚀 Starting Waskita Docker Entrypoint"

# Function to setup environment file
auto_setup_env() {
    echo "🔧 Auto-setting up environment configuration..."
    
    # If .env doesn't exist, create complete .env file for Docker using environment variables from Docker Compose
    if [ ! -f "/app/.env" ]; then
        echo "📝 Creating complete .env file for Docker environment"
        
        # Get database configuration from Docker environment variables
        DB_USER=${DATABASE_USER:-postgres}
        DB_PASSWORD=${DATABASE_PASSWORD:-admin12345}
        DB_NAME=${DATABASE_NAME:-waskita_db}
        DB_HOST=${DATABASE_HOST:-db}
        DB_PORT=${DATABASE_PORT:-5432}
        
        # Get email configuration from Docker environment variables
        MAIL_SERVER=${MAIL_SERVER:-smtp.gmail.com}
        MAIL_PORT=${MAIL_PORT:-587}
        MAIL_USE_TLS=${MAIL_USE_TLS:-true}
        MAIL_USE_SSL=${MAIL_USE_SSL:-false}
        MAIL_USERNAME=${MAIL_USERNAME:-}
        MAIL_PASSWORD=${MAIL_PASSWORD:-}
        MAIL_DEFAULT_SENDER=${MAIL_DEFAULT_SENDER:-}
        ADMIN_EMAIL=${ADMIN_EMAIL:-}
        ADMIN_EMAILS=${ADMIN_EMAILS:-}
        
        # Get Apify configuration from Docker environment variables
        APIFY_API_TOKEN=${APIFY_API_TOKEN:-}
        APIFY_BASE_URL=${APIFY_BASE_URL:-https://api.apify.com/v2}
        APIFY_TWITTER_ACTOR=${APIFY_TWITTER_ACTOR:-kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest}
        APIFY_FACEBOOK_ACTOR=${APIFY_FACEBOOK_ACTOR:-apify/facebook-scraper}
        APIFY_INSTAGRAM_ACTOR=${APIFY_INSTAGRAM_ACTOR:-apify/instagram-scraper}
        APIFY_TIKTOK_ACTOR=${APIFY_TIKTOK_ACTOR:-clockworks/free-tiktok-scraper}
        APIFY_TIMEOUT=${APIFY_TIMEOUT:-30}
        APIFY_MAX_RETRIES=${APIFY_MAX_RETRIES:-3}
        APIFY_RETRY_DELAY=${APIFY_RETRY_DELAY:-5}
        
        # Create complete .env file with all essential variables including email
        cat > /app/.env << EOF
# Complete .env file for Docker environment
# Configuration is handled by Docker Compose environment variables

# Security keys (auto-generated)
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
WTF_CSRF_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(16))")
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(16))")
WASKITA_API_KEY=$(python -c "import secrets; print(secrets.token_hex(16))")

# Flask configuration
FLASK_ENV=production
FLASK_DEBUG=0

# File upload configuration
UPLOAD_FOLDER=/app/uploads
MAX_CONTENT_LENGTH=16777216

# Model paths
WORD2VEC_MODEL_PATH=/app/models/embeddings/wiki_word2vec_csv_updated.model
NAIVE_BAYES_MODEL1_PATH=/app/models/navesbayes/naive_bayes_model1.pkl
NAIVE_BAYES_MODEL2_PATH=/app/models/navesbayes/naive_bayes_model2.pkl
NAIVE_BAYES_MODEL3_PATH=/app/models/navesbayes/naive_bayes_model3.pkl

# Email configuration from Docker environment variables
MAIL_SERVER=${MAIL_SERVER}
MAIL_PORT=${MAIL_PORT}
MAIL_USE_TLS=${MAIL_USE_TLS}
MAIL_USE_SSL=${MAIL_USE_SSL}
MAIL_USERNAME=${MAIL_USERNAME}
MAIL_PASSWORD=${MAIL_PASSWORD}
MAIL_DEFAULT_SENDER=${MAIL_DEFAULT_SENDER}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_EMAILS=${ADMIN_EMAILS}

# Other settings
CREATE_SAMPLE_DATA=false
BASE_URL=http://localhost:5000

# Apify API Configuration from Docker environment variables
APIFY_API_TOKEN=${APIFY_API_TOKEN}
APIFY_BASE_URL=${APIFY_BASE_URL}
APIFY_TWITTER_ACTOR=${APIFY_TWITTER_ACTOR}
APIFY_FACEBOOK_ACTOR=${APIFY_FACEBOOK_ACTOR}
APIFY_INSTAGRAM_ACTOR=${APIFY_INSTAGRAM_ACTOR}
APIFY_TIKTOK_ACTOR=${APIFY_TIKTOK_ACTOR}
APIFY_TIMEOUT=${APIFY_TIMEOUT}
APIFY_MAX_RETRIES=${APIFY_MAX_RETRIES}
APIFY_RETRY_DELAY=${APIFY_RETRY_DELAY}

# Database configuration from Docker environment variables
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
DATABASE_URL_DOCKER=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
EOF
        
        echo "✅ Complete .env file created successfully for Docker using environment variables"
        echo "📧 Email configuration included: MAIL_USERNAME=${MAIL_USERNAME}"
    else
        echo "✅ .env file already exists"
        
        # Ensure database configuration is not overridden from .env file
        echo "⚠️  Note: Database configuration should come from Docker environment variables"
    fi
}

# Function to wait for database to be ready
wait_for_database() {
    echo "⏳ Waiting for PostgreSQL database to be ready..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if python -c "
import os, psycopg2, sys
try:
    # Use DATABASE_URL_DOCKER if available, fallback to DATABASE_URL
    db_url = os.environ.get('DATABASE_URL_DOCKER') or os.environ.get('DATABASE_URL')
    if not db_url:
        print('❌ No database URL found in environment variables')
        sys.exit(1)
    
    # Try to connect to database with timeout
    conn = psycopg2.connect(db_url, connect_timeout=5)
    conn.close()
    print('✅ Database connection successful')
    sys.exit(0)
except psycopg2.OperationalError as e:
    if 'connection timeout' in str(e) or 'Connection refused' in str(e):
        # Database not ready yet, continue waiting
        sys.exit(1)
    else:
        print(f'❌ Database operational error: {e}')
        sys.exit(1)
except Exception as e:
    print(f'❌ Unexpected error: {e}')
    sys.exit(1)
        "; then
            echo "✅ Database is ready!"
            return 0
        fi
        
        echo "⏳ Database not ready yet (attempt $attempt/$max_attempts)..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ Database connection failed after $max_attempts attempts"
    return 1
}

# Function to initialize database
initialize_database() {
    echo "📊 Initializing database..."
    
    # Capture output and error from init_database.py
    output=$(python /app/init_database.py 2>&1)
    exit_code=$?
    
    # Display the output
    echo "$output"
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ Database initialized successfully"
        return 0
    else
        echo "❌ Database initialization failed with exit code $exit_code"
        return 1
    fi
}

# Function to check if database needs initialization
check_database_initialized() {
    echo "🔍 Checking if database needs initialization..."
    
    if python -c "
import os, psycopg2, sys
try:
    db_url = os.environ.get('DATABASE_URL_DOCKER') or os.environ.get('DATABASE_URL')
    if not db_url:
        sys.exit(1)
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    # Check core and OTP tables
    cursor.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users');\")
    users_table_exists = cursor.fetchone()[0]
    cursor.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'registration_requests');\")
    rr_exists = cursor.fetchone()[0]
    cursor.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'otp_email_logs');\")
    otp_logs_exists = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    # Initialized only if users and OTP tables exist
    sys.exit(0 if (users_table_exists and rr_exists and otp_logs_exists) else 1)
except Exception as e:
    sys.exit(1)
    "; then
        echo "✅ Database already initialized"
        return 0
    else
        echo "📝 Database needs initialization"
        return 1
    fi
}

# Main execution
main() {
    # Auto-setup environment configuration
    auto_setup_env
    
    # Wait for database to be ready
    if ! wait_for_database; then
        exit 1
    fi
    
    # Always run database initialization to ensure environment variables are applied
    # This is critical for Docker to ensure admin email and other settings match environment
    echo "🔧 Always running database initialization to apply environment variables..."
    if ! initialize_database; then
        echo "❌ Failed to initialize database"
        exit 1
    fi
    
    # Start the application
    echo "🎯 Starting Waskita application..."
    exec "$@"
}

# Run main function with all arguments
main "$@"