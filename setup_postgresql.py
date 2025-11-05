#!/usr/bin/env python3
"""
WASKITA - SETUP UTAMA SETELAH CLONING DARI GITHUB
===================================================

Script ini adalah setup utama untuk aplikasi Waskita setelah cloning dari GitHub.
Fitur yang disediakan:
1. Setup database PostgreSQL otomatis
2. Pembuatan user admin default
3. Update file .env dengan konfigurasi yang benar
4. Pengecekan dependencies dan environment
5. Panduan lengkap untuk pengguna baru

CARA PENGGUNAAN:
1. Pastikan PostgreSQL sudah terinstall dan berjalan
2. Jalankan: python setup_postgresql.py
3. Ikuti instruksi yang diberikan

Untuk bantuan lebih lanjut, lihat dokumentasi di folder docs/
"""

import os
import sys
import subprocess
import importlib.util
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from werkzeug.security import generate_password_hash
import getpass

def check_prerequisites():
    """Memeriksa prerequisites sebelum setup"""
    print("🔍 Memeriksa prerequisites...")
    
    # Deteksi environment Docker
    is_docker_env = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
    if is_docker_env:
        print("🐳 Environment Docker terdeteksi")
        print("ℹ️  Setup akan menggunakan konfigurasi khusus Docker")
    
    # Cek apakah PostgreSQL terinstall (skip di Docker)
    if not is_docker_env:
        try:
            result = subprocess.run(['pg_isready', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ PostgreSQL terdeteksi")
            else:
                print("❌ PostgreSQL tidak terdeteksi. Pastikan PostgreSQL sudah terinstall dan berjalan")
                return False
        except FileNotFoundError:
            print("❌ PostgreSQL tidak terdeteksi. Pastikan PostgreSQL sudah terinstall dan berjalan")
            return False
    else:
        print("✅ PostgreSQL diabaikan (running dalam container Docker)")
    
    # Cek dependencies Python
    required_packages = ['psycopg2', 'werkzeug', 'flask']
    missing_packages = []
    
    for package in required_packages:
        spec = importlib.util.find_spec(package)
        if spec is None:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Dependencies Python yang hilang: {', '.join(missing_packages)}")
        print("   Jalankan: pip install -r requirements.txt")
        return False
    
    print("✅ Semua prerequisites terpenuhi")
    return True

def check_database_connection(db_config):
    """
    Memeriksa apakah database sudah ada dan bisa terhubung
    
    Args:
        db_config (dict): Konfigurasi database yang berisi host, port, user, password, dan database name
        
    Returns:
        bool: True jika koneksi berhasil, False jika gagal
        
    Raises:
        psycopg2.Error: Jika terjadi error spesifik PostgreSQL
        Exception: Untuk error umum lainnya
    """
    try:
        # Coba koneksi ke database
        conn = psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['db_user'],
            password=db_config['db_password'],
            database=db_config['db_name'],
            connect_timeout=10  # Timeout 10 detik
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result and result[0] == 1:
            print(f"✅ Database '{db_config['db_name']}' sudah ada dan dapat diakses")
            return True
            
    except psycopg2.OperationalError as e:
        # Error operasional seperti koneksi ditolak, database tidak ada, dll.
        error_msg = str(e).split('\n')[0]  # Ambil hanya bagian utama error
        if "does not exist" in error_msg:
            print(f"ℹ️  Database '{db_config['db_name']}' belum ada")
        elif "connection refused" in error_msg.lower():
            print(f"❌ Koneksi ditolak ke {db_config['host']}:{db_config['port']}")
            print(f"   Pastikan PostgreSQL berjalan dan dapat diakses")
        elif "password authentication failed" in error_msg:
            print(f"❌ Autentikasi gagal untuk user '{db_config['db_user']}'")
            print(f"   Periksa username dan password database")
        else:
            print(f"❌ Error koneksi database: {error_msg}")
        
    except psycopg2.Error as e:
        # Error PostgreSQL lainnya
        print(f"❌ Error PostgreSQL: {e}")
        
    except Exception as e:
        # Error umum
        print(f"❌ Error tidak terduga: {e}")
    
    return False

def create_database_and_user():
    """Membuat database dan user PostgreSQL"""
    print("🔧 Setup Database PostgreSQL untuk Waskita")
    print("=" * 50)
    
    # Input konfigurasi database
    print("\n📋 Konfigurasi Database:")
    db_host = input("Host PostgreSQL (default: localhost): ").strip() or "localhost"
    db_port = input("Port PostgreSQL (default: 5432): ").strip() or "5432"
    
    # Kredensial admin PostgreSQL
    print("\n🔐 Kredensial Admin PostgreSQL:")
    admin_user = input("Username admin PostgreSQL (default: postgres): ").strip() or "postgres"
    admin_password = getpass.getpass("Password admin PostgreSQL: ")
    
    # Kredensial database Waskita
    print("\n🏗️ Konfigurasi Database Waskita:")
    db_name = input("Nama database (default: db_waskita): ").strip() or "db_waskita"
    db_test_name = input("Nama database test (default: db_waskitatest): ").strip() or "db_waskitatest"
    db_user = input("Username database (default: admin): ").strip() or "admin"
    db_password = getpass.getpass("Password database (default: admin12345): ") or "admin12345"
    
    # Cek apakah database sudah ada
    db_config_check = {
        'host': db_host,
        'port': db_port,
        'db_name': db_name,
        'db_user': db_user,
        'db_password': db_password
    }
    
    if check_database_connection(db_config_check):
        print(f"ℹ️  Database '{db_name}' sudah ada")
        confirm = input("Apakah Anda ingin melanjutkan setup? Database yang ada mungkin akan diupdate (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Setup dibatalkan")
            return None
    
    try:
        # Koneksi ke PostgreSQL sebagai admin
        print(f"\n🔌 Menghubungkan ke PostgreSQL di {db_host}:{db_port}...")
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=admin_user,
            password=admin_password,
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Buat user database jika belum ada
        print(f"👤 Membuat user database '{db_user}'...")
        try:
            cursor.execute(f"CREATE USER {db_user} WITH PASSWORD '{db_password}';")
            print(f"✅ User '{db_user}' berhasil dibuat")
        except psycopg2.errors.DuplicateObject:
            print(f"ℹ️ User '{db_user}' sudah ada")
        
        # Buat database development
        print(f"🗄️ Membuat database '{db_name}'...")
        try:
            cursor.execute(f"CREATE DATABASE {db_name} OWNER {db_user};")
            print(f"✅ Database '{db_name}' berhasil dibuat")
        except psycopg2.errors.DuplicateDatabase:
            print(f"ℹ️ Database '{db_name}' sudah ada")
        
        # Buat database test
        print(f"🧪 Membuat database test '{db_test_name}'...")
        try:
            cursor.execute(f"CREATE DATABASE {db_test_name} OWNER {db_user};")
            print(f"✅ Database test '{db_test_name}' berhasil dibuat")
        except psycopg2.errors.DuplicateDatabase:
            print(f"ℹ️ Database test '{db_test_name}' sudah ada")
        
        # Grant privileges
        print("🔑 Memberikan privileges...")
        cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};")
        cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_test_name} TO {db_user};")
        
        cursor.close()
        conn.close()
        
        return {
            'host': db_host,
            'port': db_port,
            'db_name': db_name,
            'db_test_name': db_test_name,
            'db_user': db_user,
            'db_password': db_password
        }
        
    except Exception as e:
        print(f"❌ Error saat setup database: {e}")
        return None

def create_tables_and_admin(db_config):
    """Membuat tabel dan user admin default"""
    try:
        # Koneksi ke database Waskita
        print(f"\n🔌 Menghubungkan ke database '{db_config['db_name']}'...")
        conn = psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['db_user'],
            password=db_config['db_password'],
            database=db_config['db_name']
        )
        cursor = conn.cursor()
        
        # Baca dan eksekusi schema SQL
        print("📋 Membuat tabel dari schema...")
        schema_path = os.path.join(os.path.dirname(__file__), 'database_schema.sql')
        
        if os.path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            # Eksekusi schema (skip jika tabel sudah ada)
            try:
                cursor.execute(schema_sql)
                print("✅ Schema database berhasil dibuat")
            except psycopg2.errors.DuplicateTable:
                print("ℹ️ Tabel sudah ada, melanjutkan...")
            except Exception as e:
                print(f"⚠️ Warning saat membuat schema: {e}")
        else:
            print("❌ File database_schema.sql tidak ditemukan")
            return False
        
        # Cek apakah user admin sudah ada
        print("\n👑 Memeriksa user admin default...")
        admin_username = "admin"
        
        cursor.execute("SELECT username, email FROM users WHERE username = %s", (admin_username,))
        existing_admin = cursor.fetchone()
        
        if existing_admin:
            print(f"ℹ️  User admin '{admin_username}' sudah ada")
            print(f"   Email: {existing_admin[1]}")
            confirm = input("Apakah Anda ingin memperbarui password admin? (y/N): ").strip().lower()
            
            if confirm != 'y':
                print("✅ User admin sudah ada, melanjutkan tanpa perubahan password")
                return True
        
        # Buat/update user admin default
        admin_email = "admin@waskita.com"
        admin_password = input("Masukkan password untuk admin (default: admin123): ") or "admin123"
        admin_fullname = "Administrator Waskita"
        
        # Hash password dengan benar
        password_hash = generate_password_hash(admin_password)
        
        # Insert admin user dengan ON CONFLICT untuk update password jika user sudah ada
        insert_admin_sql = """
        INSERT INTO users (username, email, password_hash, role, full_name, is_active, theme_preference) 
        VALUES (%s, %s, %s, 'admin', %s, TRUE, 'dark')
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            email = EXCLUDED.email,
            updated_at = CURRENT_TIMESTAMP;
        """
        
        cursor.execute(insert_admin_sql, (admin_username, admin_email, password_hash, admin_fullname))
        
        if existing_admin:
            print(f"✅ User admin '{admin_username}' berhasil diperbarui dengan password baru")
        else:
            print(f"✅ User admin '{admin_username}' berhasil dibuat dengan password yang benar")
        
        # Commit perubahan
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"\n🎉 Setup database berhasil!")
        print(f"📊 Database: {db_config['db_name']}")
        print(f"👤 Admin: {admin_username}")
        print(f"📧 Email: {admin_email}")
        print(f"🔑 Password: [HIDDEN FOR SECURITY]")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saat membuat tabel dan admin: {e}")
        return False

def backup_env_file():
    """
    Membuat backup file .env sebelum diupdate
    
    Returns:
        str: Path file backup yang dibuat, atau None jika tidak ada file .env
    """
    if not os.path.exists('.env'):
        return None
    
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f'.env.backup_{timestamp}'
    
    try:
        import shutil
        shutil.copy2('.env', backup_path)
        print(f"📦 Backup file .env dibuat: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"⚠️  Gagal membuat backup: {e}")
        return None

def update_env_file(db_config):
    """Update file .env dengan konfigurasi database, mempertahankan setting yang sudah ada"""
    try:
        print("\n📝 Mengupdate file .env...")
        
        # Buat backup sebelum update
        backup_file = backup_env_file()
        
        # Baca file .env yang sudah ada jika ada
        existing_config = {}
        other_lines = []
        
        if os.path.exists('.env'):
            with open('.env', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        existing_config[key] = value
                    else:
                        other_lines.append(line)
        
        # Generate secure key hanya jika belum ada
        import secrets
        if 'SECRET_KEY' not in existing_config:
            existing_config['SECRET_KEY'] = secrets.token_hex(32)
        if 'WTF_CSRF_SECRET_KEY' not in existing_config:
            existing_config['WTF_CSRF_SECRET_KEY'] = secrets.token_hex(16)
        if 'JWT_SECRET_KEY' not in existing_config:
            existing_config['JWT_SECRET_KEY'] = secrets.token_hex(16)
        if 'WASKITA_API_KEY' not in existing_config:
            existing_config['WASKITA_API_KEY'] = secrets.token_hex(16)
        
        # Update konfigurasi database
        existing_config.update({
            'DATABASE_URL': f"postgresql://{db_config['db_user']}:{db_config['db_password']}@{db_config['host']}:{db_config['port']}/{db_config['db_name']}",
            'TEST_DATABASE_URL': f"postgresql://{db_config['db_user']}:{db_config['db_password']}@{db_config['host']}:{db_config['port']}/{db_config['db_test_name']}",
            'DATABASE_HOST': db_config['host'],
            'DATABASE_PORT': db_config['port'],
            'DATABASE_NAME': db_config['db_name'],
            'DATABASE_USER': db_config['db_user'],
            'DATABASE_PASSWORD': db_config['db_password'],
            'POSTGRES_USER': db_config['db_user'],
            'POSTGRES_PASSWORD': db_config['db_password'],
            'POSTGRES_DB': db_config['db_name']
        })
        
        # Buat konten .env baru
        env_content = """# =============================================================================
# WASKITA APPLICATION CONFIGURATION
# =============================================================================
# File ini dibuat/diupdate otomatis oleh setup_postgresql.py
# SECURITY WARNING: Jangan pernah commit file .env ke version control!
#
# DEFAULT ADMIN CREDENTIALS (setelah setup):
# Username: admin
# Password: [password yang dimasukkan saat setup]
# Email: admin@waskita.com

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
# Development Database (PostgreSQL)
# Format: postgresql://username:password@host:port/database_name
DATABASE_URL={DATABASE_URL}
TEST_DATABASE_URL={TEST_DATABASE_URL}
DATABASE_HOST={DATABASE_HOST}
DATABASE_PORT={DATABASE_PORT}
DATABASE_NAME={DATABASE_NAME}
DATABASE_USER={DATABASE_USER}
DATABASE_PASSWORD={DATABASE_PASSWORD}

# PostgreSQL Database Settings (for Docker)
POSTGRES_USER={POSTGRES_USER}
POSTGRES_PASSWORD={POSTGRES_PASSWORD}
POSTGRES_DB={POSTGRES_DB}

# =============================================================================
# FLASK CONFIGURATION
# =============================================================================
# Secure key yang digenerate otomatis
SECRET_KEY={SECRET_KEY}
FLASK_ENV=development
FLASK_DEBUG=True

# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================
WTF_CSRF_ENABLED=True
WTF_CSRF_TIME_LIMIT=3600
WTF_CSRF_SECRET_KEY={WTF_CSRF_SECRET_KEY}
JWT_SECRET_KEY={JWT_SECRET_KEY}
WASKITA_API_KEY={WASKITA_API_KEY}

# Session Configuration for Local Network Development
SESSION_COOKIE_SECURE=False
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax
SESSION_COOKIE_DOMAIN=None

# =============================================================================
# FILE UPLOAD CONFIGURATION
# =============================================================================
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH=16777216

# =============================================================================
# WORD2VEC MODEL CONFIGURATION
# =============================================================================
WORD2VEC_MODEL_PATH=models/embeddings/wiki_word2vec_csv_updated.model
NAIVE_BAYES_MODEL1_PATH=models/navesbayes/naive_bayes_model1.pkl
NAIVE_BAYES_MODEL2_PATH=models/navesbayes/naive_bayes_model2.pkl
NAIVE_BAYES_MODEL3_PATH=models/navesbayes/naive_bayes_model3.pkl

# =============================================================================
# EMAIL CONFIGURATION (Gmail SMTP)
# =============================================================================
# For Gmail: Enable 2FA and generate App Password
# Guide: https://support.google.com/accounts/answer/185833
# Leave empty to disable email features
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-16-digit-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com

# =============================================================================
# ADMIN CONFIGURATION
# =============================================================================
ADMIN_EMAIL=admin@waskita.com
ADMIN_EMAILS=admin@waskita.com,admin2@waskita.com

# =============================================================================
# OTP SYSTEM CONFIGURATION
# =============================================================================
OTP_LENGTH=6
OTP_EXPIRY_MINUTES=30
MAX_OTP_ATTEMPTS=3
LOCKOUT_DURATION_MINUTES=15

# =============================================================================
# REGISTRATION SETTINGS
# =============================================================================
REGISTRATION_ENABLED=True
AUTO_APPROVE_REGISTRATION=False

# =============================================================================
# APPLICATION URLS
# =============================================================================
BASE_URL=http://localhost:5000

# =============================================================================
# EMAIL NOTIFICATION SETTINGS
# =============================================================================
SEND_EMAIL_NOTIFICATIONS=True
EMAIL_RETRY_ATTEMPTS=3
EMAIL_RETRY_DELAY_SECONDS=5

# =============================================================================
# APIFY API CONFIGURATION
# =============================================================================
APIFY_API_TOKEN=your-apify-api-token
APIFY_BASE_URL=https://api.apify.com/v2
APIFY_TWITTER_ACTOR=kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest
APIFY_FACEBOOK_ACTOR=apify/facebook-scraper
APIFY_INSTAGRAM_ACTOR=apify/instagram-scraper
APIFY_TIKTOK_ACTOR=clockworks/free-tiktok-scraper
APIFY_TIMEOUT=30
APIFY_MAX_RETRIES=3
APIFY_RETRY_DELAY=5



# =============================================================================
# REDIS CONFIGURATION (Optional)
# =============================================================================
REDIS_URL=redis://localhost:6379/0

# =============================================================================
# PAGINATION
# =============================================================================
POSTS_PER_PAGE=25

# =============================================================================
# LOGGING
# =============================================================================
LOG_LEVEL=INFO
LOG_FILE=logs/waskita.log

# =============================================================================
# DOCKER CONFIGURATION
# =============================================================================
# Docker Port Configuration
DB_PORT=5432
WEB_PORT=5000
REDIS_PORT=6379
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443
CREATE_SAMPLE_DATA=false

# =============================================================================
# CLEANUP CONFIGURATION
# =============================================================================
CLEANUP_EXPIRED_REQUESTS_HOURS=24
KEEP_COMPLETED_REQUESTS_DAYS=30
""".format(**existing_config)
        
        # Tambahkan baris komentar lainnya yang tidak berisi konfigurasi
        env_content += '\n'.join(other_lines)
        
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        
        print("✅ File .env berhasil diupdate, mempertahankan konfigurasi yang sudah ada")
        return True
        
    except Exception as e:
        print(f"❌ Error saat update .env: {e}")
        return False

def check_existing_config():
    """Memeriksa konfigurasi database yang sudah ada di .env"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if not os.path.exists(env_path):
        print("ℹ️  File .env tidak ditemukan, akan dibuat baru")
        return None
    
    existing_config = {}
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_config[key.strip()] = value.strip()
    except Exception as e:
        print(f"❌ Error membaca file .env: {e}")
        return None
    
    # Ekstrak konfigurasi database yang relevan
    db_config = {}
    db_keys = ['DATABASE_URL', 'TEST_DATABASE_URL', 'DATABASE_HOST', 'DATABASE_PORT', 
               'DATABASE_NAME', 'DATABASE_USER', 'DATABASE_PASSWORD']
    
    for key in db_keys:
        if key in existing_config:
            db_config[key] = existing_config[key]
    
    # Periksa apakah konfigurasi menggunakan placeholder/template
    is_placeholder_config = False
    placeholder_values = ['your-database-host', 'your-database-port', 'your-database-name', 
                         'your-database-user', 'your-database-password', 'postgresql://',
                         'localhost', '5432', 'db_waskita', 'admin', 'admin12345']
    
    for value in db_config.values():
        if any(placeholder in str(value).lower() for placeholder in placeholder_values):
            is_placeholder_config = True
            break
    
    if db_config and not is_placeholder_config:
        print("\n📋 Konfigurasi Database yang sudah ada di .env:")
        print("=" * 50)
        for key, value in db_config.items():
            if 'PASSWORD' in key:
                print(f"{key}: {'*' * len(value)}")
            else:
                print(f"{key}: {value}")
        print("=" * 50)
        
        # Tampilkan konfigurasi yang terdeteksi
        detected_config = {}
        if 'DATABASE_HOST' in db_config:
            detected_config['host'] = db_config['DATABASE_HOST']
        if 'DATABASE_PORT' in db_config:
            detected_config['port'] = db_config['DATABASE_PORT']
        if 'DATABASE_NAME' in db_config:
            detected_config['db_name'] = db_config['DATABASE_NAME']
        if 'DATABASE_USER' in db_config:
            detected_config['db_user'] = db_config['DATABASE_USER']
        if 'DATABASE_PASSWORD' in db_config:
            detected_config['db_password'] = db_config['DATABASE_PASSWORD']
        
        return detected_config
    elif is_placeholder_config:
        print("ℹ️  Konfigurasi database menggunakan placeholder/template")
        print("   Setup akan menggunakan konfigurasi baru")
        return None
    else:
        print("ℹ️  Tidak ada konfigurasi database yang ditemukan di .env")
        return None

def main():
    """
    Main function untuk setup utama Waskita
    
    Fungsi ini mengkoordinasikan seluruh proses setup:
    1. Prerequisites check
    2. Deteksi konfigurasi yang sudah ada
    3. Setup database dan user
    4. Pembuatan tabel dan admin user
    5. Update file environment
    
    Returns:
        int: Exit code (0 untuk sukses, 1 untuk error)
    """
    try:
        print("🚀 WASKITA - SETUP UTAMA SETELAH CLONING")
        print("=" * 60)
        print("Selamat datang di Waskita!")
        print("Script ini akan membantu Anda setup aplikasi untuk pertama kali.")
        print()
        
        # Cek prerequisites
        if not check_prerequisites():
            print("\n❌ Setup tidak dapat dilanjutkan. Silakan perbaiki issues di atas.")
            print("\n📋 LANGKAH PERBAIKAN:")
            print("1. Install PostgreSQL: https://www.postgresql.org/download/")
            print("2. Jalankan: pip install -r requirements.txt")
            print("3. Pastikan PostgreSQL service berjalan")
            return 1
    
        print("\n📋 FITUR SETUP YANG AKAN DILAKUKAN:")
        print("1. ✅ Prerequisites check (selesai)")
        print("2. Setup database PostgreSQL")
        print("3. Pembuatan user database")
        print("4. Pembuatan tabel dari schema")
        print("5. Pembuatan user admin default")
        print("6. Update file .env dengan konfigurasi yang benar")
        print()
        
        # Cek konfigurasi yang sudah ada di .env
        existing_config = check_existing_config()
        
        if existing_config:
            print(f"\nℹ️  Konfigurasi database terdeteksi di file .env")
            print(f"   Host: {existing_config.get('host', 'localhost')}")
            print(f"   Port: {existing_config.get('port', '5432')}")
            print(f"   Database: {existing_config.get('db_name', 'db_waskita')}")
            print(f"   User: {existing_config.get('db_user', 'admin')}")
            
            confirm = input("\nApakah Anda ingin menggunakan konfigurasi yang sudah ada? (y/N): ").strip().lower()
            
            if confirm == 'y':
                print("\n✅ Menggunakan konfigurasi database yang sudah ada")
                
                # Setup tabel dan user admin dengan konfigurasi yang ada
                if not create_tables_and_admin(existing_config):
                    return 1
                
                print("\n🎉 Setup database berhasil diselesaikan dengan konfigurasi yang sudah ada!")
                print("\n📋 Informasi Login Default:")
                print("   Username: admin")
                print("   Password: (password yang Anda masukkan atau yang sudah ada)")
                print("   Email: admin@waskita.com")
                print("\n🚀 Jalankan aplikasi dengan: python app.py")
                return 0
        
        confirm = input("Lanjutkan dengan setup baru? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Setup dibatalkan")
            return 0
        
        # Step 1: Setup database dan user
        db_config = create_database_and_user()
        if not db_config:
            print("❌ Setup database gagal")
            return 1
        
        # Step 2: Buat tabel dan admin
        if not create_tables_and_admin(db_config):
            print("❌ Setup tabel dan admin gagal")
            return 1
        
        # Step 3: Update .env
        if not update_env_file(db_config):
            print("❌ Update .env gagal")
            return 1
        
        print("\n" + "=" * 60)
        print("🎉 SETUP BERHASIL! WASKITA SIAP DIGUNAKAN!")
        print("=" * 60)
        print("✅ Semua setup berhasil diselesaikan")
        print("✅ Database PostgreSQL siap digunakan")
        print("✅ User admin telah dibuat")
        print("✅ File .env telah diupdate")
        print()
        print("📋 LANGKAH SELANJUTNYA:")
        print("1. Install semua dependencies: pip install -r requirements.txt")
        print("2. Setup Apify API token di file .env (opsional untuk scraping)")
        print("3. Setup konfigurasi email di .env (opsional untuk notifikasi)")
        print("4. Jalankan aplikasi: python app.py")
        print()
        print("🔗 AKSES APLIKASI:")
        print("   URL: http://localhost:5000")
        print("   Admin: http://localhost:5000/login")
        print()
        print("🔐 LOGIN DEFAULT:")
        print("   Username: admin")
        print("   Password: (password yang Anda masukkan)")
        print("   Email: admin@waskita.com")
        print()
        print("📚 DOKUMENTASI:")
        print("   - Lihat file README.md untuk panduan lengkap")
        print("   - Folder docs/ berisi panduan setup dan security")
        print()
        print("⚠️  PENTING: Ganti password default setelah login pertama!")
        
        return 0
    
    except KeyboardInterrupt:
        print("\n\n❌ Setup dibatalkan oleh pengguna")
        return 1
        
    except Exception as e:
        print(f"\n\n❌ Error tidak terduga selama setup: {e}")
        print("\n📋 TROUBLESHOOTING:")
        print("1. Pastikan PostgreSQL berjalan")
        print("2. Periksa koneksi internet untuk dependencies")
        print("3. Jalankan dengan hak akses administrator jika diperlukan")
        import traceback
        print(f"\n🔍 Detail error:\n{traceback.format_exc()}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)