# 🚀 PANDUAN SETUP APLIKASI WASKITA

Panduan lengkap untuk menjalankan aplikasi Waskita baik secara lokal maupun dengan Docker.

## 📊 STATUS APLIKASI SAAT INI (JANUARI 2025)

### ✅ APLIKASI BERJALAN DENGAN BAIK
**Environment**: Development Mode dengan Docker
**Status**: Semua service berjalan normal
**Versi**: Production Ready v2.0

### 🐳 DOCKER CONTAINERS YANG TERDEPLOY:
- **waskita-app-postgres**: PostgreSQL 15 (port 5432)
- **waskita-app-redis**: Redis 7 (port 6379) 
- **waskita-app-web**: Flask Application (port 5000)
- **waskita-app-nginx**: Nginx Reverse Proxy (port 80/443)

### 🔧 KONFIGURASI YANG BERJALAN:
- **Database**: PostgreSQL dengan user `[POSTGRES_USER]` / `[POSTGRES_PASSWORD]`
- **Application**: Flask dengan secret key yang aman
- **Email**: Gmail SMTP aktif dengan OTP system
- **Models**: Word2Vec dan Naive Bayes terload dengan baik
- **Security**: CSRF protection, JWT, dan rate limiting aktif

---

## 🚀 DOCKER PRODUCTION SETUP

### Persyaratan Production
- **Docker Engine**: 20.10+
- **Docker Compose**: v2.0+
- **Server RAM**: 8GB minimum (16GB recommended)
- **Storage**: 50GB+ SSD recommended
- **Network**: Stable internet connection
- **SSL Certificate**: Untuk HTTPS (recommended)

### 1. Persiapan Server Production

#### Update System
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y curl wget git htop
```

#### Install Docker (jika belum ada)
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Setup Production Environment

#### Clone dan Setup
```bash
# Clone repository
git clone https://github.com/shidayaturrohman19-dev/waskita-app.git
cd waskita-app

# Setup production environment
cp .env.example .env.prod
```

#### Konfigurasi .env.prod
```bash
# Database Production
POSTGRES_DB=waskita_prod
POSTGRES_USER=waskita_prod_user
POSTGRES_PASSWORD=STRONG_PASSWORD_HERE
DATABASE_URL=postgresql://waskita_prod_user:STRONG_PASSWORD_HERE@postgres:5432/waskita_prod

# Application Production
SECRET_KEY=VERY_STRONG_SECRET_KEY_HERE
FLASK_ENV=production
WEB_PORT=5000

# Security
SECURITY_PASSWORD_SALT=RANDOM_SALT_HERE

# Email Production
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-production-email@domain.com
MAIL_PASSWORD=your-app-password

# Redis Production
REDIS_URL=redis://redis:6379/0

# Production Settings
CREATE_SAMPLE_DATA=false
DEBUG=false
```

### 3. Deploy Production

#### Menggunakan Docker Compose Production
```bash
# Build dan deploy production
docker-compose -f docker-compose.prod.yml up -d --build

# Atau menggunakan script
.\install-build.ps1 -Production
```

#### Verifikasi Production Deployment
```bash
# Cek status containers
docker-compose -f docker-compose.prod.yml ps

# Cek logs
docker-compose -f docker-compose.prod.yml logs -f

# Test aplikasi
curl -I http://localhost:5000
```

### 4. SSL/HTTPS Setup (Recommended)

#### Menggunakan Certbot + Nginx
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Generate SSL certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

### 5. Monitoring & Maintenance

#### Health Checks
```bash
# Script health check
#!/bin/bash
# health-check.sh
docker-compose -f docker-compose.prod.yml ps | grep -q "Up" || {
    echo "Container down, restarting..."
    docker-compose -f docker-compose.prod.yml restart
}
```

#### Backup Database
```bash
# Backup script
#!/bin/bash
# backup-db.sh
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose -f docker-compose.prod.yml exec -T postgres pg_dump -U waskita_prod_user waskita_prod > backup_$DATE.sql
```

#### Log Management
```bash
# Rotate logs
docker-compose -f docker-compose.prod.yml logs --tail=1000 > app.log
docker system prune -f
```

---

## 🔧 DOCKER COMMANDS & TROUBLESHOOTING

### Perintah Docker Berguna

#### Container Management
```bash
# Lihat semua containers
docker-compose ps

# Start/Stop/Restart services
docker-compose start
docker-compose stop
docker-compose restart

# Rebuild specific service
docker-compose up -d --build app

# Scale services
docker-compose up -d --scale app=3
```

#### Database Operations
```bash
# Masuk ke database container
docker-compose exec postgres psql -U waskita_user -d waskita_db

# Backup database
docker-compose exec postgres pg_dump -U waskita_user waskita_db > backup.sql

# Restore database
docker-compose exec -T postgres psql -U waskita_user -d waskita_db < backup.sql

# Reset database (HATI-HATI!)
docker-compose down -v
docker-compose up -d
```

#### Application Commands
```bash
# Masuk ke app container
docker-compose exec app bash

# Jalankan migrations
docker-compose exec app flask db upgrade

# Create admin user
docker-compose exec app python create_admin.py

# Run tests
docker-compose exec app python -m pytest
```

### Troubleshooting Docker

#### Container Won't Start
```bash
# Lihat error logs
docker-compose logs app
docker-compose logs postgres

# Rebuild containers
docker-compose down
docker-compose up -d --build

# Reset semua (HATI-HATI!)
docker-compose down -v
docker system prune -f
docker-compose up -d --build
```

#### Port Already in Use
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Linux/Mac
sudo lsof -ti:5000 | xargs kill -9

# Atau ubah port di .env
WEB_PORT=5001
```

#### Database Connection Issues
```bash
# Cek database container
docker-compose logs postgres

# Test koneksi
docker-compose exec postgres pg_isready -U waskita_user

# Reset database container
docker-compose stop postgres
docker-compose rm postgres
docker volume rm waskita_postgres_data
docker-compose up -d postgres
```

#### Out of Memory/Disk Space
```bash
# Cek disk usage
docker system df

# Clean up
docker system prune -f
docker volume prune -f
docker image prune -a -f

# Limit container memory
# Tambahkan di docker-compose.yml:
# mem_limit: 1g
# memswap_limit: 1g
```

#### Performance Issues
```bash
# Monitor resource usage
docker stats

# Optimize PostgreSQL
# Edit postgresql.conf di container:
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB

# Scale aplikasi
docker-compose up -d --scale app=2
```

---

## 📋 DAFTAR ISI

1. [🐳 Setup Docker (Rekomendasi)](#-setup-docker-rekomendasi)
2. [💻 Setup Lokal (Development)](#-setup-lokal-development)
3. [🔧 Konfigurasi Environment](#-konfigurasi-environment)
4. [🗄️ Setup Database](#️-setup-database)
5. [👤 Pembuatan Admin User](#-pembuatan-admin-user)
6. [📋 Perintah Berguna](#-perintah-berguna)
7. [🔍 Troubleshooting](#-troubleshooting)

---

## 🐳 SETUP DOCKER (Rekomendasi)

### Persyaratan Sistem
- **Docker Desktop** (Windows/Mac) atau **Docker Engine** (Linux)
- **Docker Compose** v2.0+
- **Git** untuk clone repository
- **4GB RAM** minimum (8GB recommended)
- **10GB disk space** tersedia

### Quick Start dengan Docker (5 Menit)

#### 1. Persiapan Environment
```bash
# Clone repository
git clone https://github.com/shidayaturrohman19-dev/waskita-app.git
cd waskita-app

# Verifikasi Docker installation
docker --version
docker-compose --version

# Test Docker
docker run hello-world
```

#### 2. Setup Environment
```bash
# Copy template environment
cp .env.example .env

# File .env sudah dikonfigurasi optimal untuk Docker
# Edit sesuai kebutuhan jika diperlukan
```

#### 3. Build dan Deploy
```bash
# Metode 1: Menggunakan Script Installer (Recommended)
# Windows PowerShell:
.\install-build.ps1

# Untuk clean install (hapus data lama):
.\install-build.ps1 -Clean

# Metode 2: Manual Docker Compose
docker-compose up -d --build

# Lihat status containers
docker-compose ps
```

#### 4. Verifikasi Installation
```bash
# Lihat logs semua services
docker-compose logs

# Test koneksi database
docker-compose exec postgres psql -U waskita_user -d waskita_db
```

#### 5. Akses Aplikasi
- **🌐 Web Application**: http://localhost:5000
- **🗄️ PostgreSQL Database**: localhost:5432
- **🔴 Redis Cache**: localhost:6379
- **📊 Database Admin** (jika enabled): http://localhost:8080

**🎯 Login Default:**
- **👨‍💼 Admin**: admin@waskita.com / admin123
- **👤 User**: user@test.com / user123

**✅ SELESAI!** Aplikasi sudah siap digunakan dengan:
- ✅ Database PostgreSQL otomatis terkonfigurasi
- ✅ Admin user otomatis dibuat
- ✅ Sample data otomatis dimuat
- ✅ Semua dependencies terinstall
- ✅ Redis cache aktif
- ✅ Auto-restart containers

---

## 💻 SETUP LOKAL (Development)

### Persyaratan Sistem
- **Python**: 3.11.x (recommended) atau 3.9+
- **PostgreSQL**: 13+ (recommended) atau MySQL 8.0+
- **Redis**: 6.0+ (opsional, untuk caching)
- **Git**: Latest version
- **RAM**: Minimal 4GB (8GB recommended)
- **Storage**: Minimal 2GB free space

### 1. Clone Repository
```bash
git clone https://github.com/shidayaturrohman19-dev/waskita-app.git
cd waskita-app
```

### 2. Setup Python Environment
```bash
# Buat virtual environment
python -m venv venv

# Aktivasi virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### 3. Setup Environment Variables
```bash
# Copy template environment
cp .env.example .env

# Edit file .env sesuai kebutuhan
# Windows: notepad .env
# Linux/Mac: nano .env
```

### 4. Setup Database PostgreSQL

#### Opsi A: Menggunakan Script Otomatis (Recommended)
```bash
# Jalankan script setup database
python setup_postgresql.py
```

Script ini akan:
- ✅ Membuat database `waskita_db` dan `waskita_test_db`
- ✅ Membuat user database `waskita_user`
- ✅ Membuat semua tabel dari schema (termasuk sistem OTP terbaru)
- ✅ Membuat admin user default dengan password yang aman
- ✅ Update file `.env` dengan konfigurasi database lengkap
- ✅ Generate secure keys untuk SECRET_KEY, CSRF, dan JWT

**Fitur Database Terbaru:**
- ✅ **Sistem OTP Lengkap**: Tabel `registration_requests`, `admin_notifications`, dan `otp_email_logs`
- ✅ **Registrasi Aman**: Verifikasi OTP untuk pendaftaran pengguna baru
- ✅ **Notifikasi Admin**: Sistem pemberitahuan untuk approval registrasi
- ✅ **Logging Email**: Tracking pengiriman email OTP untuk audit
- ✅ **Index Optimized**: Index yang dioptimalkan untuk performa query tinggi

#### Opsi B: Setup Manual PostgreSQL
```bash
# 1. Install PostgreSQL (jika belum ada)
# Windows: Download dari https://www.postgresql.org/download/windows/
# Ubuntu: sudo apt install postgresql postgresql-contrib
# Mac: brew install postgresql

# 2. Masuk ke PostgreSQL
sudo -u postgres psql

# 3. Buat database dan user
CREATE DATABASE waskita_db;
CREATE USER waskita_user WITH PASSWORD 'waskita_password123';
GRANT ALL PRIVILEGES ON DATABASE waskita_db TO waskita_user;
ALTER USER waskita_user CREATEDB;
\q

# 4. Import schema database
psql -U waskita_user -d waskita_db -f database_schema.sql

# 5. Update .env dengan konfigurasi database
DATABASE_URL=postgresql://waskita_user:waskita_password123@localhost:5432/waskita_db
```

### 5. Setup Database Migrations
```bash
# Initialize migrations (jika belum ada)
flask db init

# Create migration
flask db migrate -m "Initial migration"

# Apply migrations
flask db upgrade
```

### 6. Buat Admin User
```bash
# Menggunakan script otomatis
python create_admin.py

# Atau manual melalui aplikasi
python app.py
# Kemudian buka http://localhost:5000/register dan daftar sebagai admin
```

### 7. Jalankan Aplikasi
```bash
# Development mode
python app.py

# Atau menggunakan Flask CLI
flask run

# Atau dengan Gunicorn (production-like)
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 8. Akses Aplikasi
- **URL**: http://localhost:5000
- **Admin**: admin@waskita.com / admin123
- **User**: user@test.com / user123

---

## 🔧 KONFIGURASI ENVIRONMENT

### File .env untuk Development Lokal
```bash
# Database Configuration
DATABASE_URL=postgresql://waskita_user:waskita_password123@localhost:5432/waskita_db
TEST_DATABASE_URL=postgresql://waskita_user:waskita_password123@localhost:5432/waskita_test

# Flask Configuration
SECRET_KEY=your-secret-key-change-in-production
FLASK_ENV=development
FLASK_DEBUG=True
WEB_PORT=5000

# Upload Configuration
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH=16777216

# Model Paths (pastikan file model ada)
WORD2VEC_MODEL_PATH=models/embeddings/wiki_word2vec_csv_updated.model
NAIVE_BAYES_MODEL1_PATH=models/navesbayes/naive_bayes_model1.pkl
NAIVE_BAYES_MODEL2_PATH=models/navesbayes/naive_bayes_model2.pkl
NAIVE_BAYES_MODEL3_PATH=models/navesbayes/naive_bayes_model3.pkl

# Email Configuration (untuk OTP)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# API Configuration
APIFY_API_TOKEN=your_apify_api_token_here

# Redis (opsional untuk development lokal)
REDIS_URL=redis://localhost:6379/0

# Development Settings
CREATE_SAMPLE_DATA=true
```

### File .env untuk Docker
```bash
# Database (otomatis dibuat di Docker)
POSTGRES_DB=waskita_db
POSTGRES_USER=waskita_user
POSTGRES_PASSWORD=waskita_password123
DATABASE_URL=postgresql://waskita_user:waskita_password123@postgres:5432/waskita_db

# Application
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
WEB_PORT=5000

# Redis (otomatis dikonfigurasi)
REDIS_URL=redis://redis:6379/0

# Docker Configuration
CREATE_SAMPLE_DATA=true
```

---

## 🗄️ SETUP DATABASE

### PostgreSQL (Recommended)

#### 1. Instalasi PostgreSQL
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# CentOS/RHEL
sudo yum install postgresql-server postgresql-contrib
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Windows
# Download dari: https://www.postgresql.org/download/windows/

# macOS
brew install postgresql
brew services start postgresql
```

#### 2. Konfigurasi Database
```bash
# Masuk sebagai postgres user
sudo -u postgres psql

# Buat database dan user
CREATE DATABASE waskita_db;
CREATE DATABASE waskita_test;  -- untuk testing
CREATE USER waskita_user WITH PASSWORD 'waskita_password123';

# Grant privileges
GRANT ALL PRIVILEGES ON DATABASE waskita_db TO waskita_user;
GRANT ALL PRIVILEGES ON DATABASE waskita_test TO waskita_user;
ALTER USER waskita_user CREATEDB;

# Exit
\q
```

#### 3. Import Schema
```bash
# Import schema ke database
psql -U waskita_user -d waskita_db -f database_schema.sql

# Atau menggunakan migrations
flask db upgrade
```

### MySQL (Alternatif)

#### 1. Instalasi MySQL
```bash
# Ubuntu/Debian
sudo apt install mysql-server

# CentOS/RHEL
sudo yum install mysql-server
sudo systemctl start mysqld
sudo systemctl enable mysqld

# Windows/macOS
# Download dari: https://dev.mysql.com/downloads/mysql/
```

#### 2. Konfigurasi MySQL
```sql
-- Masuk ke MySQL
mysql -u root -p

-- Buat database dan user
CREATE DATABASE waskita_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE waskita_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'waskita_user'@'localhost' IDENTIFIED BY 'waskita_password123';

-- Grant privileges
GRANT ALL PRIVILEGES ON waskita_db.* TO 'waskita_user'@'localhost';
GRANT ALL PRIVILEGES ON waskita_test.* TO 'waskita_user'@'localhost';
FLUSH PRIVILEGES;

-- Exit
EXIT;
```

#### 3. Update .env untuk MySQL
```bash
DATABASE_URL=mysql+pymysql://waskita_user:waskita_password123@localhost:3306/waskita_db
```

---

## 👤 PEMBUATAN ADMIN USER

### Metode 1: Script Otomatis (Recommended)
```bash
# Jalankan script create_admin.py
python create_admin.py
```

Script ini akan:
- ✅ Membuat admin user dengan email: admin@waskita.com
- ✅ Password default: admin123
- ✅ Membuat sample user: user@test.com / user123
- ✅ Membuat sample data (jika CREATE_SAMPLE_DATA=true)

### Metode 2: Manual melalui Database
```sql
-- PostgreSQL
INSERT INTO users (email, password_hash, role, is_active, created_at) 
VALUES (
    'admin@waskita.com', 
    'pbkdf2:sha256:260000$...',  -- hash dari 'admin123'
    'admin', 
    true, 
    NOW()
);
```

### Metode 3: Melalui Web Interface
```bash
# 1. Jalankan aplikasi
python app.py

# 2. Buka browser ke http://localhost:5000/register
# 3. Daftar dengan email admin
# 4. Ubah role di database menjadi 'admin'
```

### Metode 4: Interactive Script
```bash
# Buat admin user secara interaktif
python -c "
from create_admin import create_admin_user
create_admin_user()
"
```

---

## 📋 PERINTAH BERGUNA

### Development Commands
```bash
# Jalankan aplikasi development
python app.py

# Jalankan dengan auto-reload
flask run --reload

# Jalankan tests
python -m pytest

# Jalankan security tests
python run_security_tests.py

# Database migrations
flask db migrate -m "Description"
flask db upgrade
flask db downgrade

# Create admin user
python create_admin.py

# Setup database
python setup_postgresql.py
```

### Docker Commands
```bash
# Build dan jalankan
docker-compose up -d

# Lihat logs
docker-compose logs -f

# Masuk ke container
docker-compose exec app bash

# Restart services
docker-compose restart

# Stop semua
docker-compose down

# Reset semua data
docker-compose down -v
```

### Database Commands
```bash
# PostgreSQL
psql -U waskita_user -d waskita_db

# Backup database
pg_dump -U waskita_user waskita_db > backup.sql

# Restore database
psql -U waskita_user -d waskita_db < backup.sql

# MySQL
mysql -u waskita_user -p waskita_db

# Backup MySQL
mysqldump -u waskita_user -p waskita_db > backup.sql

# Restore MySQL
mysql -u waskita_user -p waskita_db < backup.sql
```

---

## 🔍 TROUBLESHOOTING

### Database Connection Issues

#### PostgreSQL Connection Error
```bash
# Cek status PostgreSQL
sudo systemctl status postgresql

# Restart PostgreSQL
sudo systemctl restart postgresql

# Cek port PostgreSQL
sudo netstat -tulpn | grep :5432

# Test connection
psql -U waskita_user -d waskita_db -h localhost
```

#### MySQL Connection Error
```bash
# Cek status MySQL
sudo systemctl status mysql

# Restart MySQL
sudo systemctl restart mysql

# Cek port MySQL
sudo netstat -tulpn | grep :3306
```

### Python Environment Issues

#### Module Not Found
```bash
# Pastikan virtual environment aktif
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install ulang dependencies
pip install -r requirements.txt

# Cek installed packages
pip list
```

#### Permission Errors
```bash
# Linux/Mac - fix permissions
sudo chown -R $USER:$USER .
chmod +x *.py

# Windows - run as administrator
```

### Application Errors

#### Port Already in Use
```bash
# Cek port yang digunakan
netstat -tulpn | grep :5000

# Kill process menggunakan port
# Linux/Mac:
sudo lsof -ti:5000 | xargs kill -9
# Windows:
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

#### Missing Model Files
```bash
# Download model files (jika diperlukan)
mkdir -p models/embeddings models/navesbayes

# Atau disable model loading untuk development
# Set di .env:
WORD2VEC_MODEL_PATH=""
```

#### Email OTP Not Working
```bash
# Test email configuration
python -c "
from flask_mail import Mail, Message
from app import app
mail = Mail(app)
with app.app_context():
    msg = Message('Test', sender=app.config['MAIL_USERNAME'], recipients=['test@example.com'])
    msg.body = 'Test email'
    try:
        mail.send(msg)
        print('Email sent successfully!')
    except Exception as e:
        print(f'Email error: {e}')
"
```

### Docker Issues

#### Container Won't Start
```bash
# Lihat error logs
docker-compose logs

# Rebuild containers
docker-compose down
docker-compose up --build

# Reset semua
docker-compose down -v
docker system prune -f
```

#### Database Container Issues
```bash
# Cek database logs
docker-compose logs postgres

# Masuk ke database container
docker-compose exec postgres psql -U waskita_user -d waskita_db

# Reset database volume
docker-compose down -v
docker volume rm waskita_postgres_data
```

---

// ... existing code ...