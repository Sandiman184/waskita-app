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

#### Model Loading Issues
```bash
# Cek apakah model files ada di container
docker-compose exec app ls -la /app/models/

# Cek file Word2Vec
docker-compose exec app ls -la /app/models/embeddings/

# Cek file Naive Bayes
docker-compose exec app ls -la /app/models/navesbayes/

# Restart aplikasi untuk reload model
docker-compose restart app

# Cek logs untuk error model loading
docker-compose logs app | grep -i model

# Test model loading manual
docker-compose exec app python -c "
import os
print('Word2Vec exists:', os.path.exists('/app/models/embeddings/wiki_word2vec_csv_updated.model'))
print('NB Model1 exists:', os.path.exists('/app/models/navesbayes/naive_bayes_model1.pkl'))
"
```

#### Email Configuration Issues
```bash
# Test email configuration
docker-compose exec app python -c "
from flask_mail import Mail
from app import app
mail = Mail(app)
print('Mail server:', app.config.get('MAIL_SERVER'))
print('Mail port:', app.config.get('MAIL_PORT'))
print('Mail username:', app.config.get('MAIL_USERNAME'))
"

# Check email service status
docker-compose exec app python -c "
import smtplib
try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    print('Gmail SMTP connection: SUCCESS')
    server.quit()
except Exception as e:
    print('Gmail SMTP connection: FAILED -', str(e))
"
```

#### Application Startup Issues
```bash
# Check application logs
docker-compose logs app --tail=100

# Check database connection
docker-compose exec app python -c "
from app import db
try:
    db.engine.connect()
    print('Database connection: SUCCESS')
except Exception as e:
    print('Database connection: FAILED -', str(e))
"

# Check Redis connection
docker-compose exec app python -c "
import redis
try:
    r = redis.Redis(host='redis', port=6379, db=0)
    r.ping()
    print('Redis connection: SUCCESS')
except Exception as e:
    print('Redis connection: FAILED -', str(e))
"
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
8. [🚀 Deployment Workflow](#-deployment-workflow)

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

### 5. Setup Database Migrations dengan Flask-Migrate

Aplikasi Waskita menggunakan **Flask-Migrate** dengan **Alembic** untuk manajemen migrasi database. Ini adalah pendekatan modern yang lebih fleksibel dibandingkan menggunakan file SQL schema statis.

#### Keunggulan Flask-Migrate:
- **Version Control**: Setiap perubahan database dapat dilacak melalui migrasi
- **Auto-generate**: Migrasi dapat digenerate otomatis dari perubahan model
- **Rollback**: Dapat melakukan downgrade ke versi sebelumnya jika diperlukan
- **Consistency**: Memastikan konsistensi schema di semua environment

#### Perintah Migrasi Utama:
```bash
# Initialize migrations (hanya sekali di awal project)
flask db init

# Generate migration otomatis dari perubahan model
flask db migrate -m "Deskripsi perubahan"

# Apply semua migrasi yang pending
flask db upgrade

# Rollback ke migrasi sebelumnya
flask db downgrade

# Lihat status migrasi saat ini
flask db current

# Lihat history migrasi
flask db history
```

#### Untuk Docker Environment:
```bash
# Jalankan migrasi di container aplikasi
docker-compose exec app flask db upgrade

# Generate migrasi baru dari dalam container
docker-compose exec app flask db migrate -m "nama_migrasi"

# Lihat status migrasi
docker-compose exec app flask db current
```

### 6. Best Practices untuk Development

#### 🔧 Environment Management
```bash
# Selalu gunakan virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate    # Windows

# Install dependencies dengan requirements.txt
pip install -r requirements.txt

# Freeze dependencies setelah perubahan
pip freeze > requirements.txt

# Gunakan .env untuk konfigurasi sensitif
# JANGAN commit .env ke version control!
```

#### 🗄️ Database Management
```bash
# Backup database secara berkala
pg_dump -U waskita_user waskita_db > backup_$(date +%Y%m%d).sql

# Restore dari backup
psql -U waskita_user -d waskita_db < backup.sql

# Monitor database performance
# Install pg_stat_statements di PostgreSQL
```

#### 🐳 Docker Development Best Practices
```bash
# Gunakan Docker Compose untuk development
docker-compose up -d --build

# Monitor logs secara real-time
docker-compose logs -f app

# Masuk ke container untuk debugging
docker-compose exec app bash

# Rebuild containers setelah perubahan code
docker-compose up -d --build

# Clean up resources yang tidak digunakan
docker system prune -f
docker volume prune -f
```

#### 📊 Performance Optimization
```bash
# Monitor resource usage
docker stats

# Optimize Python application
# Gunakan gunicorn untuk production
# Enable worker processes dan threads

# Optimize PostgreSQL
shared_buffers = 25% of RAM
effective_cache_size = 50% of RAM
work_mem = 4MB per connection

# Enable Redis caching untuk performa
```

### 7. Contoh Implementasi - Setup Production Ready

#### 🔐 Production Environment Configuration
```bash
# .env.prod - Production Environment
SECRET_KEY=your-super-secure-random-secret-key-here
DATABASE_URL=postgresql://waskita_user:secure_password@db:5432/waskita_db
REDIS_URL=redis://redis:6379/0
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MODEL_WORD2VEC_PATH=/app/models/embeddings/wiki_word2vec_csv_updated.model
MODEL_NAIVE_BAYES_PATH=/app/models/navesbayes/naive_bayes_model1.pkl
```

---

## 🚀 DEPLOYMENT WORKFLOW

### Environment Files yang Didukung
Aplikasi Waskita mendukung multiple environment files untuk berbagai deployment scenario:

#### 1. `.env` - Local Development
- Untuk development tradisional tanpa Docker
- Database: `localhost:5432`
- Tanpa SSL, debug mode enabled

#### 2. `.env.docker` - Docker Development  
- Untuk Docker development dengan SSL disabled
- Database: `postgres:5432` (Docker networking)
- Nginx HTTP configuration

#### 3. `.env.production` - Docker Production
- Untuk production deployment dengan SSL enabled
- Database SSL: `sslmode=require`
- Nginx SSL configuration dengan HSTS

### Quick Deployment Commands

#### Local Development
```bash
cp .env.example .env
# Edit .env untuk local database
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

#### Docker Development (SSL Disabled)
```bash
cp .env.example .env.docker
# .env.docker sudah dikonfigurasi untuk Docker development
docker-compose -f docker-compose.yml up -d --build
```

#### Docker Production (SSL Enabled)
```bash
cp .env.example .env.production
# Edit .env.production untuk production settings
docker-compose -f docker-compose.yml --env-file .env.production up -d --build
```

#### Automated VPS Deployment
```bash
# Menggunakan script otomatis
./deploy-vps.sh

# Atau manual setup
bash <(curl -s https://raw.githubusercontent.com/Sandiman184/waskita-app/main/scripts/vps-setup.sh)
```

### Deployment Checklist

#### Pre-Deployment
- [ ] Environment file sesuai target deployment
- [ ] Semua credentials diganti dengan values production
- [ ] SSL certificate tersedia (untuk production)
- [ ] Database backup sebelum deploy
- [ ] Test deployment di staging environment

#### During Deployment
- [ ] Monitor logs real-time: `docker-compose logs -f`
- [ ] Verify health checks: `curl http://localhost:5000/health`
- [ ] Test database connection
- [ ] Verify SSL certificate (jika production)

#### Post-Deployment
- [ ] Monitor application performance
- [ ] Setup automated backups
- [ ] Configure monitoring dan alerting
- [ ] Update documentation dengan deployment details

### Troubleshooting Deployment

#### Common Issues
```bash
# Port already in use
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Database connection issues
docker-compose logs postgres | grep -i "connection"

# SSL certificate problems
docker-compose logs nginx | grep -i "ssl"

# Model loading failures  
docker-compose logs app | grep -i "model"
```

#### Quick Fixes
```bash
# Restart specific service
docker-compose restart app

# Rebuild containers
docker-compose up -d --build

# Reset database (hati-hati!)
docker-compose down -v
docker-compose up -d

# Check resource usage
docker stats
```

### Monitoring & Maintenance

#### Health Monitoring
```bash
# Application health
curl -f http://localhost:5000/health

# Database health
docker-compose exec postgres pg_isready -U $POSTGRES_USER

# Redis health
docker-compose exec app python -c "import redis; redis.Redis(host='redis').ping()"
```

#### Log Management
```bash
# Real-time logs
docker-compose logs -f --tail=50

# Error monitoring
docker-compose logs app | grep -E "(error|exception|fail)"

# Security monitoring
docker-compose logs app | grep -E "(login|auth|security|otp)"
```

#### Backup Procedures
```bash
# Database backup
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup_$DATE.sql
gzip backup_$DATE.sql

# Environment backup
cp .env.production backup/.env.production.$DATE
cp docker-compose.yml backup/docker-compose.yml.$DATE
```

### Best Practices Deployment

#### Security
- Gunakan environment variables untuk semua credentials
- Enable SSL/TLS untuk production deployment
- Setup firewall rules yang appropriate
- Regular security scanning dan patching

#### Performance
- Monitor resource usage (CPU, memory, disk)
- Optimize database configuration
- Enable caching dengan Redis
- Setup load balancing jika diperlukan

#### Reliability
- Implement health checks
- Setup automated backups
- Configure monitoring dan alerting
- Document recovery procedures

#### Maintenance
- Regular updates dan patching
- Monitor logs untuk anomalies
- Regular performance tuning
- Update documentation secara berkala

#### 🚀 Production Deployment Script
```bash
#!/bin/bash
# deploy-prod.sh

echo "🚀 Starting Production Deployment..."

# Pull latest code
git pull origin main

# Build and deploy
docker-compose -f docker-compose.prod.yml up -d --build

# Run database migrations
docker-compose -f docker-compose.prod.yml exec app flask db upgrade

# Check application health
echo "✅ Deployment completed!"
echo "🌐 Application URL: https://your-domain.com"
echo "📊 Health Check: curl https://your-domain.com/health"
```

#### 📋 Production Readiness Checklist
- [ ] ✅ Environment variables configured for production
- [ ] ✅ Database backups configured
- [ ] ✅ SSL/TLS certificates installed
- [ ] ✅ Monitoring and alerting setup
- [ ] ✅ Log aggregation configured
- [ ] ✅ Performance testing completed
- [ ] ✅ Security scanning completed
- [ ] ✅ Disaster recovery plan in place
- [ ] ✅ Load testing performed
- [ ] ✅ Documentation updated

# Generate migrasi baru dari container
docker-compose exec app flask db migrate -m "Nama migrasi"

# Lihat status migrasi di Docker
docker-compose exec app flask db current
```

#### Migrasi vs Static SQL Schema:
- **Gunakan `flask db upgrade`** untuk environment production dan development
- **File `database_schema.sql`** disediakan sebagai backup/referensi saja
- **Prioritas**: Selalu gunakan sistem migrasi untuk perubahan database

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

### 🧠 Konfigurasi Model Paths di Docker

Model machine learning (Word2Vec dan Naive Bayes) harus tersedia di dalam container Docker. Berikut cara setup yang benar:

#### 1. Pastikan File Model Ada di Host
File model harus berada di path berikut di host machine:
```
waskita-app/
├── models/
│   ├── embeddings/
│   │   └── wiki_word2vec_csv_updated.model
│   └── navesbayes/
│       ├── naive_bayes_model1.pkl
│       ├── naive_bayes_model2.pkl
│       └── naive_bayes_model3.pkl
```

#### 2. Docker Volume Mapping
File `docker-compose.yml` sudah mengkonfigurasi volume mapping yang benar:
```yaml
volumes:
  - ./models:/app/models  # Map folder models host ke container
```

#### 3. Verifikasi Model di Container
```bash
# Cek apakah model files ada di container
docker-compose exec app ls -la /app/models/

# Expected output:
# embeddings/  navesbayes/

# Cek file Word2Vec
docker-compose exec app ls -la /app/models/embeddings/

# Cek file Naive Bayes
docker-compose exec app ls -la /app/models/navesbayes/
```

#### 4. Troubleshooting Model Loading
Jika model tidak terload:
```bash
# Restart aplikasi untuk reload model
docker-compose restart app

# Cek logs untuk error model loading
docker-compose logs app | grep -i model

# Pastikan file model ada dan readable
docker-compose exec app python -c "
import os
print('Word2Vec exists:', os.path.exists('/app/models/embeddings/wiki_word2vec_csv_updated.model'))
print('NB Model1 exists:', os.path.exists('/app/models/navesbayes/naive_bayes_model1.pkl'))
"
```

#### 5. Download Model (Jika Belum Ada)
Jika file model belum tersedia, sistem akan otomatis mencoba mendownload saat pertama kali running:
- Word2Vec model akan didownload dari URL yang dikonfigurasi
- Naive Bayes models akan di-training otomatis dari sample data

**Note**: Proses download/training pertama kali mungkin memakan waktu beberapa menit.

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

## 🔐 Nginx SSL Toggle (ENABLE_SSL)

Gunakan toggle `ENABLE_SSL` untuk memilih konfigurasi Nginx secara otomatis antara HTTP-only (lokal) dan SSL (production).

### Variabel Penting
- `ENABLE_SSL`: `false` untuk lokal (HTTP-only), `true` untuk production (SSL aktif)
- `NGINX_SERVER_NAME`: nama host/domain untuk Nginx (contoh: `localhost` atau `app.waskita.my.id`)

### Cara Pakai
- Lokal (HTTP-only):
  - Jalankan: `./install-build.ps1 -Local` (Windows PowerShell)
  - Mengaktifkan `ENABLE_SSL=false` dan menggunakan `nginx.http.conf`
  - Akses: `http://localhost:${NGINX_HTTP_PORT}` (default `80`)
- Production (SSL ON):
  - Jalankan: `./install-build.ps1 -Production`
  - Mengaktifkan `ENABLE_SSL=true` dan menggunakan `nginx.conf` (SSL)
  - Set `NGINX_SERVER_NAME` ke domain Anda (contoh: `waskita.example.com`)
  - Pastikan sertifikat berada di `docker/ssl/` dan path sesuai di `docker/nginx.conf`

### File Terkait
- `docker/docker-compose.yml`: memuat `ENABLE_SSL` dan `NGINX_SERVER_NAME` ke container Nginx
- `docker/docker-compose.local.yml`: override lokal, memaksa `ENABLE_SSL=false` dan hanya port HTTP
- `docker/nginx.entrypoint.sh`: memilih config otomatis (SSL vs HTTP) berdasarkan `ENABLE_SSL`

### Verifikasi Cepat
- Cek Nginx memilih config yang benar:
  - `docker compose logs nginx` → harus muncul `Using SSL config` (production) atau `Using HTTP config` (local)
- Test HTTP (lokal):
  - `curl -I http://localhost:${NGINX_HTTP_PORT}` → status `200 OK`
- Test HTTPS (production):
  - `curl -I https://your-domain` → status `200 OK`, sertifikat valid

### Catatan
- `.env.docker` kini menyertakan default `ENABLE_SSL=false` dan `NGINX_SERVER_NAME=localhost`.
- Script `install-build.ps1` akan meng-override nilai tersebut saat startup sesuai mode yang dipilih.
 - `.env.docker` juga menetapkan `REDIS_URL=redis://redis:6379/0` agar koneksi Redis dalam Docker berjalan benar.