#!/bin/bash
set -e

# Docker entrypoint script for Waskita application
# Handles database initialization, environment setup, and application startup

echo "🚀 Starting Waskita Docker Entrypoint"

# Function to setup environment file
auto_setup_env() {
    echo "🔧 Auto-setting up environment configuration..."
    
    # Load environment variables from .env.docker file if it exists
    if [ -f "/app/.env.docker" ]; then
        echo "📝 Loading environment variables from .env.docker file"
        # Export all variables from .env.docker file
        export $(grep -v '^#' /app/.env.docker | xargs)
        echo "✅ Environment variables loaded from .env.docker"
    else
        echo "⚠️  .env.docker file not found, using default environment variables"
    fi
    
    # If .env doesn't exist, create complete .env file for Docker using environment variables
    if [ ! -f "/app/.env" ]; then
        echo "📝 Creating complete .env file for Docker environment"
        
        # Get database configuration from environment variables only
        DB_USER=${DATABASE_USER}
        DB_PASSWORD=${DATABASE_PASSWORD}
        DB_NAME=${DATABASE_NAME}
        DB_HOST=${DATABASE_HOST}
        DB_PORT=${DATABASE_PORT}
        
        # Get email configuration from environment variables
        MAIL_SERVER=${MAIL_SERVER:-smtp.gmail.com}
        MAIL_PORT=${MAIL_PORT:-587}
        MAIL_USE_TLS=${MAIL_USE_TLS:-true}
        MAIL_USE_SSL=${MAIL_USE_SSL:-false}
        MAIL_USERNAME=${MAIL_USERNAME:-}
        MAIL_PASSWORD=${MAIL_PASSWORD:-}
        MAIL_DEFAULT_SENDER=${MAIL_DEFAULT_SENDER:-}
        ADMIN_EMAIL=${ADMIN_EMAIL:-}
        ADMIN_EMAILS=${ADMIN_EMAILS:-}
        
        # Get Apify configuration from environment variables
        APIFY_API_TOKEN=${APIFY_API_TOKEN:-}
        APIFY_BASE_URL=${APIFY_BASE_URL:-https://api.apify.com/v2}
        APIFY_TWITTER_ACTOR=${APIFY_TWITTER_ACTOR:-kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest}
        APIFY_FACEBOOK_ACTOR=${APIFY_FACEBOOK_ACTOR:-apify/facebook-scraper}
        APIFY_INSTAGRAM_ACTOR=${APIFY_INSTAGRAM_ACTOR:-apify/instagram-scraper}
        APIFY_TIKTOK_ACTOR=${APIFY_TIKTOK_ACTOR:-clockworks/free-tiktok-scraper}
        APIFY_TIMEOUT=${APIFY_TIMEOUT:-30}
        APIFY_MAX_RETRIES=${APIFY_MAX_RETRIES:-3}
        APIFY_RETRY_DELAY=${APIFY_RETRY_DELAY:-5}
        
        # Create minimal .env file for Docker environment
        cat > /app/.env << EOF
# Minimal .env file for Docker environment
# Database configuration comes from Docker environment variables

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

# Email configuration from environment variables
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

# Apify API Configuration from environment variables
APIFY_API_TOKEN=${APIFY_API_TOKEN}
APIFY_BASE_URL=${APIFY_BASE_URL}
APIFY_TWITTER_ACTOR=${APIFY_TWITTER_ACTOR}
APIFY_FACEBOOK_ACTOR=${APIFY_FACEBOOK_ACTOR}
APIFY_INSTAGRAM_ACTOR=${APIFY_INSTAGRAM_ACTOR}
APIFY_TIKTOK_ACTOR=${APIFY_TIKTOK_ACTOR}
APIFY_TIMEOUT=${APIFY_TIMEOUT}
APIFY_MAX_RETRIES=${APIFY_MAX_RETRIES}
APIFY_RETRY_DELAY=${APIFY_RETRY_DELAY}

# NOTE: Database configuration comes from Docker environment variables
# DATABASE_URL, DATABASE_USER, DATABASE_PASSWORD, etc. from Docker Compose
EOF
        
        echo "✅ Complete .env file created successfully for Docker using environment variables"
        echo "📧 Email configuration included: MAIL_USERNAME=${MAIL_USERNAME}"
    else
        echo "✅ .env file already exists"
        
        # Ensure we have the latest environment variables from .env.docker
        if [ -f "/app/.env.docker" ]; then
            echo "📝 Updating environment variables from .env.docker"
            export $(grep -v '^#' /app/.env.docker | xargs)
            echo "✅ Environment variables updated from .env.docker"
        fi
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
    # Get database connection parameters from environment variables
    # Use POSTGRES_* variables for database connection (as set in docker-compose)
    db_user = os.environ.get('POSTGRES_USER') or os.environ.get('DATABASE_USER')
    db_password = os.environ.get('POSTGRES_PASSWORD') or os.environ.get('DATABASE_PASSWORD')
    db_host = os.environ.get('DATABASE_HOST')
    db_port = os.environ.get('DATABASE_PORT')
    db_name = os.environ.get('POSTGRES_DB') or os.environ.get('DATABASE_NAME')
    
    # Construct database URL
    db_url = 'postgresql://{}:{}@{}:{}/{}'.format(db_user, db_password, db_host, db_port, db_name)
    
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
        print('❌ Database operational error: ' + str(e))
        sys.exit(1)
except Exception as e:
    print('❌ Unexpected error: ' + str(e))
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