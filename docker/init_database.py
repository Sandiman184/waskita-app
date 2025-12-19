#!/usr/bin/env python3
"""
Database initialization script for Waskita Docker container
This script handles database schema creation and admin user setup
"""

import os
import sys
import time
import json
import psycopg2
import subprocess
from werkzeug.security import generate_password_hash

def wait_for_database():
    """Wait for PostgreSQL database to be ready"""
    
    max_attempts = 30
    attempt = 0
    
    while attempt < max_attempts:
        try:
            # Get database connection parameters from environment variables
            db_user = os.environ.get('DATABASE_USER')
            db_password = os.environ.get('DATABASE_PASSWORD')
            db_host = os.environ.get('DATABASE_HOST')
            db_port = os.environ.get('DATABASE_PORT')
            db_name = os.environ.get('DATABASE_NAME')  # Connect to default database
            
            # Try to connect to database with explicit parameters
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name,
                connect_timeout=5
            )
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

def run_flask_migration(command):
    """Run flask db command via subprocess"""
    try:
        print(f"🔄 Running: flask db {command}")
        # Ensure we are in the correct directory where app.py is located
        # The Dockerfile sets WORKDIR to /app/src/backend, so we should be good.
        result = subprocess.run(
            ['flask', 'db'] + command.split(),
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running flask db {command}:")
        print(e.stdout)
        print(e.stderr)
        return False

def create_database_schema(conn):
    """Create database schema using Flask-Migrate (Alembic)"""
    try:
        # Check if alembic_version table exists
        alembic_exists = check_table_exists(conn, 'alembic_version')
        users_exists = check_table_exists(conn, 'users')

        if not alembic_exists:
            if users_exists:
                print("⚠️  Tables exist but alembic_version is missing. Stamping head...")
                # The DB has tables (maybe from SQL dump) but no version.
                # Stamp it as current to avoid 'DuplicateTable' errors.
                if run_flask_migration('stamp head'):
                    print("✅ Database stamped as head.")
                    return True
                return False
            else:
                print("🆕 Empty database detected. Running migrations...")
                # Fresh DB, run upgrades
                if run_flask_migration('upgrade'):
                    print("✅ Database migrations applied.")
                    return True
                return False
        else:
            print("🔄 Database versioned. checking for updates...")
            if run_flask_migration('upgrade'):
                print("✅ Database updated.")
                return True
            return False

    except Exception as e:
        print("❌ Error managing database schema:", str(e))
        import traceback
        traceback.print_exc()
        return False

def create_admin_user(conn):
    """Create default admin user in the database"""
    try:
        # Default admin credentials - use environment variables only
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        admin_fullname = os.environ.get('ADMIN_FULLNAME', 'Administrator Waskita')
        
        if not admin_password:
             # Fallback if ADMIN_PASSWORD is not set
             print("⚠️  ADMIN_PASSWORD not set, using default 'admin12345'")
             admin_password = 'admin12345'

        # Hash password
        password_hash = generate_password_hash(admin_password)
        
        # Admin preferences (dark mode by default)
        admin_prefs = json.dumps({
            "dark_mode": True, 
            "language": "id",
            "timezone": "Asia/Jakarta"
        })
        
        # Insert admin user with ON CONFLICT to update password and email if user already exists
        # Updated to use preferences JSON column instead of deprecated theme_preference
        insert_admin_sql = """
        INSERT INTO users (username, email, password_hash, role, full_name, is_active, preferences, first_login) 
        VALUES (%s, %s, %s, 'admin', %s, TRUE, %s, TRUE)
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            email = EXCLUDED.email,
            preferences = EXCLUDED.preferences,
            updated_at = CURRENT_TIMESTAMP,
            first_login = TRUE;
        """
        
        cursor = conn.cursor()
        cursor.execute(insert_admin_sql, (admin_username, admin_email, password_hash, admin_fullname, admin_prefs))
        conn.commit()
        cursor.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
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
        db_user = os.environ.get('DATABASE_USER')
        db_password = os.environ.get('DATABASE_PASSWORD')
        db_host = os.environ.get('DATABASE_HOST')
        db_port = os.environ.get('DATABASE_PORT')
        db_name = os.environ.get('DATABASE_NAME')
        
        database_url = "postgresql://{}:{}@{}:{}/{}".format(db_user, db_password, db_host, db_port, db_name)
        print("ℹ️  Constructed database URL from environment variables: " + database_url)
    
    print("🔗 Using database URL: " + database_url)
    
    print("⏳ Waiting for database...")
    if not wait_for_database():
        print("❌ Could not connect to database")
        sys.exit(1)
        
    try:
        conn = psycopg2.connect(database_url)
        
        print("📊 Checking database schema...")
        if create_database_schema(conn):
            print("✅ Database schema initialized")
        else:
            print("❌ Failed to initialize database schema")
            sys.exit(1)
            
        print("👤 Creating admin user...")
        if create_admin_user(conn):
            print("✅ Admin user created/updated")
        else:
            print("❌ Failed to create admin user")
            
        print("🔐 Updating security settings...")
        update_admin_otp_setting(conn)
            
        conn.close()
        print("🚀 Database initialization completed successfully")
        
    except Exception as e:
        print("❌ Unexpected error:", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()