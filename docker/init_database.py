#!/usr/bin/env python3
"""
Database initialization script for Waskita Docker container
This script handles database schema creation and admin user setup
"""

import os
import sys
import time
import psycopg2
from werkzeug.security import generate_password_hash

def wait_for_database():
    """Wait for PostgreSQL database to be ready"""
    
    max_attempts = 30
    attempt = 0
    
    while attempt < max_attempts:
        try:
            # Get database connection from environment variables
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                return False
            
            # Try to connect to database
            conn = psycopg2.connect(db_url)
            conn.close()
            return True
            
        except Exception as e:
            attempt += 1
            time.sleep(2)
    
    return False

def check_table_exists(conn, table_name):
    """Check if a table exists in the database"""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);",
            (table_name,)
        )
        exists = cursor.fetchone()[0]
        cursor.close()
        return exists
    except Exception as e:
        return False

def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = %s AND column_name = %s);",
            (table_name, column_name)
        )
        exists = cursor.fetchone()[0]
        cursor.close()
        return exists
    except Exception as e:
        return False

def add_missing_columns(conn):
    """Add missing columns to existing tables"""
    try:
        # Check if first_login column exists in users table
        if not check_column_exists(conn, 'users', 'first_login'):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE users ADD COLUMN first_login BOOLEAN DEFAULT TRUE")
            conn.commit()
            cursor.close()
        
        return True
        
    except Exception as e:
        return False

def create_database_schema(conn):
    """Create database schema if it doesn't exist"""
    try:
        # Check if users table already exists
        if check_table_exists(conn, 'users'):
            # Add any missing columns to existing schema
            if not add_missing_columns(conn):
                return False
            return True
        
        # Read and execute the schema file
        try:
            with open('/app/database_schema.sql', 'r') as f:
                schema_sql = f.read()
        except FileNotFoundError:
            print("❌ File database_schema.sql not found at /app/database_schema.sql")
            print("Current working directory:", os.getcwd())
            print("Files in /app/:")
            import subprocess
            result = subprocess.run(['ls', '-la', '/app/'], capture_output=True, text=True)
            print(result.stdout)
            return False
        
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        cursor.close()
        
        return True
        
    except Exception as e:
        print("❌ Error creating database schema:", str(e))
        import traceback
        traceback.print_exc()
        return False

def create_admin_user(conn):
    """Create default admin user in the database"""
    try:
        # Default admin credentials - use environment variable or fallback to placeholder
        admin_username = "admin"
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@waskita.com')
        admin_password = "admin123"  # Default password, should be changed in production
        admin_fullname = "Administrator Waskita"
        
        # Hash password
        password_hash = generate_password_hash(admin_password)
        
        # Insert admin user with ON CONFLICT to update password and email if user already exists
        insert_admin_sql = """
        INSERT INTO users (username, email, password_hash, role, full_name, is_active, theme_preference, first_login) 
        VALUES (%s, %s, %s, 'admin', %s, TRUE, 'dark', TRUE)
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            email = EXCLUDED.email,
            updated_at = CURRENT_TIMESTAMP,
            first_login = TRUE;
        """
        
        cursor = conn.cursor()
        cursor.execute(insert_admin_sql, (admin_username, admin_email, password_hash, admin_fullname))
        conn.commit()
        cursor.close()
        
        return True
        
    except Exception as e:
        return False

def update_admin_otp_setting(conn):
    """Enforce admin to require OTP on first login in Docker"""
    try:
        cursor = conn.cursor()
        
        # Ensure admin requires OTP on first login
        update_sql = """
        UPDATE users 
        SET first_login = TRUE, 
            updated_at = CURRENT_TIMESTAMP
        WHERE username = 'admin' AND first_login = FALSE;
        """
        
        cursor.execute(update_sql)
        conn.commit()
        
        cursor.close()
        return True
        
    except Exception as e:
        return False

def main():
    """Main initialization function"""
    
    # Prioritize DATABASE_URL_DOCKER for Docker environment, fallback to DATABASE_URL
    # If neither is set, construct from individual environment variables
    database_url = os.environ.get('DATABASE_URL_DOCKER') or os.environ.get('DATABASE_URL')
    
    if not database_url:
        # Construct database URL from individual environment variables
        db_user = os.environ.get('DATABASE_USER', 'postgres')
        db_password = os.environ.get('DATABASE_PASSWORD', 'admin12345')
        db_host = os.environ.get('DATABASE_HOST', 'db')
        db_port = os.environ.get('DATABASE_PORT', '5432')
        db_name = os.environ.get('DATABASE_NAME', 'waskita_db')
        
        database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        print(f"ℹ️  Constructed database URL from environment variables: {database_url}")
    
    print(f"🔗 Using database URL: {database_url}")
    
    # Wait for database to be ready
    if not wait_for_database():
        print("❌ Database connection failed after multiple attempts")
        sys.exit(1)
    
    # Database is ready, proceed with initialization
    try:
        # Parse database URL to get connection parameters
        from urllib.parse import urlparse
        parsed_url = urlparse(database_url)
        dbname = parsed_url.path[1:]  # Remove leading slash
        
        # Connect to PostgreSQL server
        conn = psycopg2.connect(
            host=parsed_url.hostname,
            port=parsed_url.port,
            user=parsed_url.username,
            password=parsed_url.password,
            dbname='postgres'  # Connect to default database first
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if cursor.fetchone():
            print(f"✅ Database '{dbname}' already exists")
        else:
            # Create database
            cursor.execute(f"CREATE DATABASE {dbname}")
            print(f"✅ Database '{dbname}' created successfully")
        
        cursor.close()
        conn.close()
        
        # Now connect to the specific database to create tables
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Read and execute schema SQL
        with open('/app/database_schema.sql', 'r') as f:
            schema_sql = f.read()
        
        cursor.execute(schema_sql)
        print("✅ Database schema created successfully")
        
        # Create or update admin user with consistent schema and OTP requirement
        hashed_password = generate_password_hash('admin123', method='scrypt')
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, full_name, is_active, theme_preference, first_login)
            VALUES (%s, %s, %s, 'admin', %s, TRUE, 'dark', TRUE)
            ON CONFLICT (username) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                updated_at = CURRENT_TIMESTAMP,
                first_login = TRUE
            """,
            ('admin', 'admin@waskita.com', hashed_password, 'Administrator Waskita')
        )
        print("✅ Admin user ensured with first_login=TRUE (OTP required)")
        
        cursor.close()
        conn.close()
        
        print("🎉 Database initialization completed successfully!")
        sys.exit(0)
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()