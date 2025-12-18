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
        if check_table_exists(conn, 'users') and not check_column_exists(conn, 'users', 'first_login'):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE users ADD COLUMN first_login BOOLEAN DEFAULT TRUE")
            conn.commit()
            cursor.close()
            print("🔧 Added first_login column to users table")
            
        # Add new columns to datasets table
        if check_table_exists(conn, 'datasets'):
            if not check_column_exists(conn, 'datasets', 'file_path'):
                cursor = conn.cursor()
                print("🔧 Adding file_path column to datasets...")
                cursor.execute("ALTER TABLE datasets ADD COLUMN file_path TEXT")
                conn.commit()
                cursor.close()
                
            if not check_column_exists(conn, 'datasets', 'external_id'):
                cursor = conn.cursor()
                print("🔧 Adding external_id column to datasets...")
                cursor.execute("ALTER TABLE datasets ADD COLUMN external_id VARCHAR(100)")
                conn.commit()
                cursor.close()
                
        return True
    except Exception as e:
        print(f"❌ Error adding missing columns: {e}")
        return False

def init_db():
    if not wait_for_database():
        sys.exit(1)
        
    # Get database URL
    db_url = os.getenv('DATABASE_URL_DOCKER') or os.getenv('DATABASE_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        
        # Check and update schema
        add_missing_columns(conn)
        
        conn.close()
        print("✅ Database initialization completed successfully")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 Starting database initialization...")
    init_db()
