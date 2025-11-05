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
        # Default admin credentials
        admin_username = "admin"
        admin_email = "admin@waskita.com"
        admin_password = "admin123"  # Default password, should be changed in production
        admin_fullname = "Administrator Waskita"
        
        # Hash password
        password_hash = generate_password_hash(admin_password)
        
        # Insert admin user with ON CONFLICT to update password if user already exists
        insert_admin_sql = """
        INSERT INTO users (username, email, password_hash, role, full_name, is_active, theme_preference, first_login) 
        VALUES (%s, %s, %s, 'admin', %s, TRUE, 'dark', FALSE)
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            updated_at = CURRENT_TIMESTAMP,
            first_login = FALSE;
        """
        
        cursor = conn.cursor()
        cursor.execute(insert_admin_sql, (admin_username, admin_email, password_hash, admin_fullname))
        conn.commit()
        cursor.close()
        
        return True
        
    except Exception as e:
        return False

def update_admin_otp_setting(conn):
    """Update admin user to disable first login OTP requirement for Docker"""
    try:
        cursor = conn.cursor()
        
        # Update admin user to disable first login OTP requirement
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
        return False

def main():
    """Main initialization function"""
    
    # Wait for database to be ready
    if not wait_for_database():
        sys.exit(1)
    
    try:
        # Connect to database
        db_url = os.getenv('DATABASE_URL')
        conn = psycopg2.connect(db_url)
        
        # Create database schema if needed
        if not create_database_schema(conn):
            conn.close()
            sys.exit(1)
        
        # Create admin user
        if not create_admin_user(conn):
            conn.close()
            sys.exit(1)
        
        # Update admin user to disable first login OTP requirement (Docker mode)
        update_admin_otp_setting(conn)
        
        conn.close()
        
        sys.exit(0)
        
    except Exception as e:
        sys.exit(1)

if __name__ == "__main__":
    main()