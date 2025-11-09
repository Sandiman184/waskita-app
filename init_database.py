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
            # Get database connection from environment variables - prefer DATABASE_URL_DOCKER for Docker
            db_url = os.getenv('DATABASE_URL_DOCKER') or os.getenv('DATABASE_URL')
            if not db_url:
                print("❌ No database URL found in environment variables")
                return False
            
            # Try to connect to database with timeout
            conn = psycopg2.connect(db_url, connect_timeout=5)
            conn.close()
            print("✅ Database connection successful")
            return True
            
        except psycopg2.OperationalError as e:
            if 'connection timeout' in str(e) or 'Connection refused' in str(e):
                # Database not ready yet, continue waiting
                attempt += 1
                time.sleep(2)
            else:
                print(f"❌ Database operational error: {e}")
                return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            attempt += 1
            time.sleep(2)
    
    print("❌ Database connection failed after maximum attempts")
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
        # Ensure first_login column exists in users table (required for OTP)
        if not check_column_exists(conn, 'users', 'first_login'):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE users ADD COLUMN first_login BOOLEAN DEFAULT TRUE")
            conn.commit()
            cursor.close()
        
        # Fix OTP email logs schema - remove NOT NULL constraint if it exists
        cursor = conn.cursor()
        cursor.execute("""
        SELECT is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'otp_email_logs' AND column_name = 'registration_request_id'
        """)
        result = cursor.fetchone()
        
        if result and result[0] == 'NO':
            print("🔧 Removing NOT NULL constraint from registration_request_id...")
            cursor.execute("""
            ALTER TABLE otp_email_logs 
            ALTER COLUMN registration_request_id DROP NOT NULL;
            """)
            conn.commit()
            print("✅ NOT NULL constraint removed from registration_request_id")
        
        cursor.close()
        return True
        
    except Exception as e:
        print(f"⚠️ Warning while fixing schema: {e}")
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
        with open('/app/database_schema.sql', 'r') as f:
            schema_sql = f.read()
        
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        cursor.close()
        
        return True
        
    except Exception as e:
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
        # Use environment variable to determine first_login behavior
        otp_enabled = os.getenv('OTP_ENABLED', 'True').lower() == 'true'
        first_login_value = 'TRUE' if otp_enabled else 'FALSE'
        
        insert_admin_sql = f"""
        INSERT INTO users (username, email, password_hash, role, full_name, is_active, theme_preference, first_login) 
        VALUES (%s, %s, %s, 'admin', %s, TRUE, 'dark', {first_login_value})
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            email = EXCLUDED.email,
            updated_at = CURRENT_TIMESTAMP,
            first_login = {first_login_value};
        """
        
        cursor = conn.cursor()
        cursor.execute(insert_admin_sql, (admin_username, admin_email, password_hash, admin_fullname))
        conn.commit()
        cursor.close()
        
        return True
        
    except Exception as e:
        return False

def update_admin_email_from_env(conn):
    """Update admin email to always use environment variable value"""
    try:
        # Get admin email from environment variable
        admin_email_from_env = os.environ.get('ADMIN_EMAIL')
        
        if not admin_email_from_env:
            print("⚠️  ADMIN_EMAIL environment variable not set, skipping email update")
            return True
        
        cursor = conn.cursor()
        
        # Check current admin email
        cursor.execute("SELECT email FROM users WHERE username = 'admin';")
        result = cursor.fetchone()
        
        if result and result[0] != admin_email_from_env:
            print(f"📧 Updating admin email from '{result[0]}' to '{admin_email_from_env}'")
            
            # Update admin email to match environment variable
            update_sql = """
            UPDATE users 
            SET email = %s, 
                updated_at = CURRENT_TIMESTAMP
            WHERE username = 'admin';
            """
            
            cursor.execute(update_sql, (admin_email_from_env,))
            conn.commit()
            print("✅ Admin email updated successfully")
        else:
            print(f"✅ Admin email already matches environment variable: {admin_email_from_env}")
        
        cursor.close()
        return True
        
    except Exception as e:
        print(f"⚠️ Warning while updating admin email: {e}")
        return False

def update_admin_otp_setting(conn):
    """Update admin OTP settings to be consistent with local environment"""
    try:
        cursor = conn.cursor()
        
        # Check environment to determine OTP behavior
        # In Docker, respect the OTP_ENABLED environment variable
        otp_enabled = os.getenv('OTP_ENABLED', 'True').lower() == 'true'
        
        if otp_enabled:
            # OTP enabled - ensure admin requires OTP on first login
            update_sql = """
            UPDATE users 
            SET first_login = TRUE, 
                updated_at = CURRENT_TIMESTAMP
            WHERE username = 'admin' AND first_login = FALSE;
            """
        else:
            # OTP disabled - ensure admin doesn't require OTP
            update_sql = """
            UPDATE users 
            SET first_login = FALSE, 
                updated_at = CURRENT_TIMESTAMP
            WHERE username = 'admin' AND first_login = TRUE;
            """
        
        cursor.execute(update_sql)
        conn.commit()
        
        cursor.close()
        return True
        
    except Exception as e:
        print(f"⚠️ Warning while updating admin OTP settings: {e}")
        return False

def create_demo_user(conn):
    """Create demo user in the database"""
    try:
        # Demo user credentials
        demo_username = "demo_user"
        demo_email = "demo@waskita.com"
        demo_password = "demo123"  # Default password for demo
        demo_fullname = "Demo User Waskita"
        
        # Hash password
        password_hash = generate_password_hash(demo_password)
        
        # Insert demo user with ON CONFLICT to update password and email if user already exists
        # Use environment variable to determine first_login behavior
        otp_enabled = os.getenv('OTP_ENABLED', 'True').lower() == 'true'
        first_login_value = 'TRUE' if otp_enabled else 'FALSE'
        
        insert_demo_sql = f"""
        INSERT INTO users (username, email, password_hash, role, full_name, is_active, theme_preference, first_login) 
        VALUES (%s, %s, %s, 'user', %s, TRUE, 'dark', {first_login_value})
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            email = EXCLUDED.email,
            updated_at = CURRENT_TIMESTAMP,
            first_login = {first_login_value};
        """
        
        cursor = conn.cursor()
        cursor.execute(insert_demo_sql, (demo_username, demo_email, password_hash, demo_fullname))
        conn.commit()
        cursor.close()
        
        return True
        
    except Exception as e:
        print(f"⚠️ Warning while creating demo user: {e}")
        return False

def main():
    """Main initialization function"""
    
    # Wait for database to be ready
    if not wait_for_database():
        sys.exit(1)
    
    try:
        # Connect to database - prefer DATABASE_URL_DOCKER for Docker
        db_url = os.getenv('DATABASE_URL_DOCKER') or os.getenv('DATABASE_URL')
        if not db_url:
            print("❌ No database URL found in environment variables")
            sys.exit(1)
            
        conn = psycopg2.connect(db_url)
        
        # Create database schema if needed
        if not create_database_schema(conn):
            conn.close()
            sys.exit(1)
        
        # Create admin user
        if not create_admin_user(conn):
            conn.close()
            sys.exit(1)
        
        # Create demo user
        if not create_demo_user(conn):
            conn.close()
            sys.exit(1)
        
        # Always update admin email to match environment variable (critical for Docker)
        update_admin_email_from_env(conn)
        
        # Update admin user to disable first login OTP requirement (Docker mode)
        update_admin_otp_setting(conn)
        
        conn.close()
        
        print("✅ Database initialization completed successfully")
        sys.exit(0)
        
    except psycopg2.OperationalError as e:
        print(f"❌ Database operational error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error during database initialization: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()