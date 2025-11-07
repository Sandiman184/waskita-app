#!/bin/bash
set -e

# Docker entrypoint script for Waskita application
# Handles database initialization, environment setup, and application startup

echo "🚀 Starting Waskita Docker Entrypoint"

# Function to setup environment file
auto_setup_env() {
    echo "🔧 Auto-setting up environment configuration..."
    
    # If .env doesn't exist, create minimal .env file for Docker using environment variables from Docker Compose
    if [ ! -f "/app/.env" ]; then
        echo "📝 Creating minimal .env file for Docker environment"
        
        # Get database configuration from Docker environment variables
        DB_USER=${DATABASE_USER:-postgres}
        DB_PASSWORD=${DATABASE_PASSWORD:-Sandiman184}
        DB_NAME=${DATABASE_NAME:-waskita_db}
        DB_HOST=${DATABASE_HOST:-db}
        DB_PORT=${DATABASE_PORT:-5432}
        
        # Create minimal .env file with only essential variables
        cat > /app/.env << EOF
# Minimal .env file for Docker environment
# Database configuration is handled by Docker Compose environment variables

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

# Other settings
CREATE_SAMPLE_DATA=false
BASE_URL=http://localhost:5000

# Database configuration from Docker environment variables
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
DATABASE_URL_DOCKER=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
EOF
        
        echo "✅ Minimal .env file created successfully for Docker using environment variables"
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
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    cursor = conn.cursor()
    cursor.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users');\")
    users_table_exists = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    sys.exit(0 if users_table_exists else 1)
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
    
    # Check if database needs initialization
    if check_database_initialized; then
        echo "📋 Database is already set up, skipping initialization"
    else
        # Initialize database
        if ! initialize_database; then
            echo "❌ Failed to initialize database"
            exit 1
        fi
    fi
    
    # Start the application
    echo "🎯 Starting Waskita application..."
    exec "$@"
}

# Run main function with all arguments
main "$@"