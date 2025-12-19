#!/usr/bin/env python3
"""
WASKITA - SETUP UTAMA APLIKASI
===================================================

Script ini adalah setup utama untuk aplikasi Waskita setelah cloning dari GitHub.
Fitur yang disediakan:
1. Setup environment variables (.env) dengan input interaktif
2. Setup database PostgreSQL (Lokal & Docker)
3. Pembuatan user admin default
4. Inisialisasi struktur folder & dependensi

CARA PENGGUNAAN:
1. Jalankan: python src/backend/setup_postgresql.py
2. Ikuti instruksi interaktif

Untuk bantuan lebih lanjut, lihat dokumentasi di folder docs/
"""

import os
import sys
import shutil
import secrets
import subprocess
import time
from pathlib import Path

# Coba import psycopg2
try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Warna untuk output console
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")

def print_step(text):
    print(f"\n{Colors.BLUE}>> {text}{Colors.ENDC}")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")

def prompt_input(label, default=None, is_password=False):
    """Helper untuk input user dengan default value"""
    default_str = f" [{default}]" if default else ""
    prompt_text = f"{label}{default_str}: "
    
    val = input(prompt_text)
    if not val and default:
        return default
    return val

# 1. SETUP ENVIRONMENT VARIABLES
def setup_env_file():
    print_step("Konfigurasi Environment (.env)...")
    
    root_dir = Path(__file__).resolve().parent.parent.parent
    env_path = root_dir / '.env'
    
    # Pilih template berdasarkan preferensi user
    print("\nPilih lingkungan deployment:")
    print("1. Local Development (Tanpa Docker)")
    print("2. Docker Environment")
    choice = input("Pilihan (1/2) [1]: ").strip()
    
    if choice == '2':
        template_name = '.env.example.docker'
        print_step("Menggunakan template Docker...")
    else:
        template_name = '.env.example.local'
        print_step("Menggunakan template Local...")
        
    env_example_path = root_dir / template_name
    
    # Fallback ke .env.example lama jika template baru tidak ada
    if not env_example_path.exists():
        env_example_path = root_dir / '.env.example'
    
    if not env_example_path.exists():
        print_error(f"Template {template_name} tidak ditemukan!")
        return False
    
    # Baca template
    with open(env_example_path, 'r') as f:
        env_content = f.read()
    
    # Jika .env belum ada, copy dulu
    if not env_path.exists():
        print_warning("File .env belum ada. Membuat dari template...")
        
        # Auto-generate secrets
        secret_key = secrets.token_hex(32)
        jwt_key = secrets.token_hex(32)
        env_content = env_content.replace('change-this-to-a-secure-random-key', secret_key)
        env_content = env_content.replace('change-this-jwt-secret-key', jwt_key)
        
        # Tulis file baru
        with open(env_path, 'w') as f:
            f.write(env_content)
    else:
        # Jika sudah ada, baca konten eksisting agar tidak tertimpa total
        # Namun kita tetap menggunakan struktur template baru sebagai referensi jika perlu update key
        with open(env_path, 'r') as f:
            env_content = f.read()

    print("\nSilakan lengkapi konfigurasi penting berikut (tekan Enter untuk skip/default):")
    
    # Daftar konfigurasi yang perlu input user
    config_prompts = [
        # (Key, Label, Default/Placeholder)
        ("DATABASE_PASSWORD", "Password Database Lokal (untuk user 'postgres'/'admin')", "admin12345"),
        ("MAIL_USERNAME", "Email Gmail untuk SMTP (Notifikasi/OTP)", "your-email@gmail.com"),
        ("MAIL_PASSWORD", "App Password Gmail", "your-app-password"),
        ("APIFY_API_TOKEN", "Apify API Token (Scraping)", "your-apify-api-token"),
        ("APIFY_TWITTER_ACTOR", "Apify Twitter Actor ID", "heLL6fU..."),
        ("APIFY_TIKTOK_ACTOR", "Apify TikTok Actor ID", "Clockworks..."),
        ("APIFY_FACEBOOK_ACTOR", "Apify Facebook Actor ID", "KoJ..."),
        ("ADMIN_EMAIL", "Email Super Admin", "admin@waskita.com"),
        ("MAX_CONTENT_LENGTH", "Batas Upload (bytes) - Default 10GB", "10737418240"),
    ]
    
    # Hanya minta input UPLOAD_FOLDER jika di local, Docker sudah diset di template
    if choice != '2':
        config_prompts.append(("UPLOAD_FOLDER", "Folder Upload (Relative/Absolute)", "uploads"))
    
    new_content = env_content
    changes_made = False
    
    for key, label, placeholder in config_prompts:
        # Cek apakah value saat ini masih default/placeholder
        current_val_line = [line for line in new_content.split('\n') if line.startswith(f"{key}=")]
        if current_val_line:
            current_val = current_val_line[0].split('=', 1)[1].strip()
            # Jika value masih placeholder atau default example, minta input
            if current_val in [placeholder, "change-this-api-key", "your_secure_password"]:
                user_val = prompt_input(label, default=None)
                if user_val:
                    # Replace line
                    new_content = new_content.replace(f"{key}={current_val}", f"{key}={user_val}")
                    changes_made = True
            else:
                # Opsi untuk override jika user mau
                if input(f"Konfigurasi '{key}' sudah diset ({current_val[:5]}...). Ubah? (y/n): ").lower() == 'y':
                    user_val = prompt_input(label, default=current_val)
                    if user_val and user_val != current_val:
                        new_content = new_content.replace(f"{key}={current_val}", f"{key}={user_val}")
                        changes_made = True
    
    if changes_made:
        with open(env_path, 'w') as f:
            f.write(new_content)
        print_success("File .env berhasil diperbarui dengan konfigurasi Anda.")
    else:
        print_success("File .env tidak berubah (menggunakan konfigurasi yang ada).")
        
    return True

# 2. SETUP DATABASE POSTGRESQL
def setup_database():
    print_step("Setup Database PostgreSQL...")
    
    if not PSYCOPG2_AVAILABLE:
        print_error("Library 'psycopg2' belum terinstall.")
        print("   Silakan install dulu: pip install psycopg2-binary")
        return False
        
    # Input kredensial database
    print("Masukkan kredensial PostgreSQL Lokal Anda:")
    db_host = prompt_input("Host", "localhost")
    db_port = prompt_input("Port", "5432")
    db_user = prompt_input("Username", "postgres")
    db_pass = prompt_input("Password", is_password=True)
    db_name = "db_waskita"
    
    try:
        # Koneksi ke database 'postgres' untuk membuat database baru
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_pass,
            dbname="postgres"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Cek apakah database sudah ada
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db_name}'")
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Membuat database '{db_name}'...")
            cursor.execute(f"CREATE DATABASE {db_name}")
            print_success(f"Database '{db_name}' berhasil dibuat!")
        else:
            print_success(f"Database '{db_name}' sudah ada.")
            
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.OperationalError as e:
        print_error(f"Gagal koneksi ke PostgreSQL: {e}")
        print_warning("Pastikan PostgreSQL service berjalan dan password benar.")
        return False

# 3. INSTALASI DEPENDENSI
def install_dependencies():
    print_step("Memeriksa Dependensi Python...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print_success("Semua dependensi berhasil diinstall!")
        return True
    except subprocess.CalledProcessError:
        print_error("Gagal menginstall dependensi. Cek koneksi internet atau permission.")
        return False

# MAIN EXECUTION
def main():
    print_header("WASKITA APP - INITIAL SETUP")
    
    # 1. Setup .env
    if not setup_env_file():
        return
        
    # 2. Install Dependencies
    if input("\nInstall dependensi Python sekarang? (y/n): ").lower() == 'y':
        install_dependencies()
        
    # 3. Setup Database
    if input("\nSetup database PostgreSQL sekarang? (y/n): ").lower() == 'y':
        setup_database()
        
    print_header("SETUP SELESAI")
    print("\nLangkah selanjutnya:")
    print("1. Jalankan migrasi database: flask db upgrade")
    print("2. Jalankan aplikasi: flask run")
    print("3. Atau gunakan Docker: docker-compose up --build")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup dibatalkan oleh pengguna.")
        sys.exit(0)
