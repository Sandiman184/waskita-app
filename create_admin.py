#!/usr/bin/env python3
"""
Simple admin user creation script for Docker container
This script creates the default admin user when the container starts
"""

import os
import sys
import time
import psycopg2
import logging
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def create_admin_user():
    """Create default admin user in the database"""
    try:
        # Get database connection from environment variables
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            logger.error("DATABASE_URL environment variable not found")
            return False
        
        logger.info(f"Connecting to database: {db_url}")
        
        # Connect to database
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Default admin credentials
        admin_username = "admin"
        admin_email = "admin@waskita.com"
        admin_password = "admin123"  # Default password, should be changed in production
        admin_fullname = "Administrator Waskita"
        
        # Hash password
        password_hash = generate_password_hash(admin_password)
        logger.info(f"Generated password hash for admin user")
        
        # Insert admin user with ON CONFLICT to update password if user already exists
        insert_admin_sql = """
        INSERT INTO users (username, email, password_hash, role, full_name, is_active, preferences, first_login) 
        VALUES (%s, %s, %s, 'admin', %s, TRUE, '{\"theme\": \"dark\"}', FALSE)
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            email = EXCLUDED.email,
            full_name = EXCLUDED.full_name,
            preferences = EXCLUDED.preferences,
            updated_at = CURRENT_TIMESTAMP,
            first_login = FALSE;
        """
        
        cursor.execute(insert_admin_sql, (admin_username, admin_email, password_hash, admin_fullname))
        conn.commit()
        
        logger.info("Admin user created/updated successfully")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

def wait_for_database(max_attempts=30, delay=2):
    """Wait for database to be ready"""
    attempt = 0
    while attempt < max_attempts:
        try:
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                logger.warning("DATABASE_URL not set, waiting...")
                time.sleep(delay)
                attempt += 1
                continue
            
            conn = psycopg2.connect(db_url)
            conn.close()
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.warning(f"Database not ready yet (attempt {attempt + 1}/{max_attempts}): {e}")
            time.sleep(delay)
            attempt += 1
    
    logger.error("Database connection timeout")
    return False

if __name__ == "__main__":
    logger.info("Starting admin user creation script")
    
    # Wait for database to be ready
    if not wait_for_database():
        logger.error("Failed to connect to database")
        sys.exit(1)
    
    # Create admin user
    success = create_admin_user()
    if success:
        logger.info("Script completed successfully")
        sys.exit(0)
    else:
        logger.error("Script failed")
        sys.exit(1)