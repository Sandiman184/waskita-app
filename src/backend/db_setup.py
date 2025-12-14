import os
import sys
from flask_migrate import upgrade, init, migrate

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def setup_database():
    """Setup database using Flask-Migrate"""
    print("Starting database setup...")
    
    with app.app_context():
        # Check if migrations directory exists
        if not os.path.exists('migrations'):
            print("Initializing migrations folder...")
            init()
        
        print("Generating migration script...")
        try:
            migrate(message="Initial migration")
        except Exception as e:
            print(f"Migration generation warning (might be empty or already exists): {e}")
            
        print("Applying migrations...")
        try:
            upgrade()
            print("Database setup complete!")
        except Exception as e:
            print(f"Error applying migrations: {e}")
            print("Please check your database connection string.")

if __name__ == "__main__":
    setup_database()
