# Instalasi & Persiapan Awal

Dokumen ini menjelaskan langkah instalasi dan persiapan awal aplikasi Waskita untuk keperluan pengembangan (development) dan produksi (production) tanpa duplikasi, sesuai outline yang diinginkan.

Versi Dokumen: 1.3 — Diperbarui: 2025-01-15

## Daftar Isi

1. Pendahuluan
2. Prasyarat Sistem
3. Setup dengan Docker (Rekomendasi)
   - 3.1 Clone repository
   - 3.2 Setup environment (.env / .env.production)
   - 3.3 Build & run (dev dan production)
   - 3.4 Verifikasi & akses aplikasi
4. Setup Lokal (Development)
   - 4.1 Virtualenv
   - 4.2 Install dependencies
   - 4.3 Setup database
   - 4.4 Jalankan aplikasi
5. Setup Database & Migrasi
6. Pembuatan Admin User
7. Quick Commands untuk Dev & Prod

---

## 1. Pendahuluan

Aplikasi Waskita adalah aplikasi Flask untuk klasifikasi konten media sosial (Radikal/Non‑Radikal). Dokumen ini memandu setup untuk pengembang dan deployment produksi secara ringkas dan konsisten.

## 2. Prasyarat Sistem

- `Git`
- `Python 3.9+` (disarankan `3.11.x`) — untuk setup lokal
- `PostgreSQL 13+` — untuk database
- `Redis 6.0+` (opsional, untuk caching)
- `Docker Desktop` (Windows/Mac) atau `Docker Engine` (Linux)
- `Docker Compose v2.0+`
- Minimal `4GB RAM` (disarankan `8GB`)
- Minimal `10GB` ruang disk kosong

## 3. Setup dengan Docker (Rekomendasi)

### 3.1 Clone repository
```bash
git clone https://github.com/shidayaturrohman19-dev/waskita-app.git
cd waskita-app
```

### 3.2 Setup environment (.env / .env.production)
```bash
# Salin template environment untuk development
cp .env.example .env

# (Opsional) Siapkan environment untuk production
cp .env.example .env.production
# Edit .env.production sesuai kebutuhan (DATABASE_URL, REDIS_URL, ENABLE_SSL, NGINX_SERVER_NAME)
```

### 3.3 Build & run (dev dan production)
```bash
# Development dengan Docker (compose lokal)
docker-compose -f docker/docker-compose.local.yml up --build

# Production dengan Docker (di server/VPS)
docker-compose -f docker/docker-compose.yml up --build -d
```

### 3.4 Verifikasi & akses aplikasi
```bash
# Verifikasi containers
docker-compose ps
docker-compose logs web --tail=100

# Verifikasi health endpoint
curl http://localhost:5000/api/health

# Akses aplikasi
# Development (lokal):
http://localhost:5000
# Production (contoh):
https://yourdomain.com

# Jika database dijalankan di container
docker-compose exec db psql -U waskita_user -d waskita_db
```

## 4. Setup Lokal (Development)

### 4.1 Virtualenv
```bash
python -m venv venv

# Aktivasi virtualenv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip
```

### 4.2 Install dependencies
```bash
pip install -r requirements.txt
```

### 4.3 Setup database
```bash
# Opsi otomatis (disarankan)
python setup_postgresql.py

# (Alternatif manual)
# Buat database dan user, lalu set DATABASE_URL di .env
```

### 4.4 Jalankan aplikasi
```bash
python app.py
# atau
flask run
```

## 5. Setup Database & Migrasi

Aplikasi menggunakan Flask-Migrate (Alembic) untuk manajemen migrasi database.

```bash
# Apply migrasi yang ada
flask db upgrade

# Generate migrasi dari perubahan model (opsional)
flask db migrate -m "Deskripsi perubahan"

# Status migrasi
flask db current
```

Untuk Docker:
```bash
docker-compose -f docker/docker-compose.local.yml exec web flask db upgrade
docker-compose -f docker/docker-compose.local.yml exec web flask db migrate -m "nama_migrasi"
```

## 6. Pembuatan Admin User

```bash
# Lokal
python create_admin.py

# Docker
docker-compose -f docker/docker-compose.local.yml exec web python create_admin.py
```

## 7. Quick Commands untuk Dev & Prod

### Development Lokal
```bash
git clone https://github.com/shidayaturrohman19-dev/waskita-app.git
cd waskita-app

python -m venv venv
venv\Scripts\activate            # Windows
# atau
source venv/bin/activate         # Linux/Mac

cp .env.example .env
pip install -r requirements.txt
python setup_postgresql.py
flask db upgrade
python create_admin.py
python app.py
```

### Development dengan Docker
```bash
git clone https://github.com/shidayaturrohman19-dev/waskita-app.git
cd waskita-app

cp .env.example .env
docker-compose -f docker/docker-compose.local.yml up --build
```

### Production dengan Docker
```bash
git clone https://github.com/shidayaturrohman19-dev/waskita-app.git
cd waskita-app

cp .env.example .env.production
# Edit .env.production untuk konfigurasi production

docker-compose -f docker/docker-compose.yml up --build -d
docker-compose -f docker/docker-compose.yml exec web flask db upgrade
docker-compose -f docker/docker-compose.yml exec web python create_admin.py
```

## 8. Konfigurasi SSL untuk Production

### 8.1 Persiapan Sertifikat SSL

#### Opsi A: Let's Encrypt (Recommended)
```bash
# Install certbot
sudo apt install certbot

# Generate sertifikat untuk domain Anda
certbot certonly --standalone -d waskita.site -d www.waskita.site

# Copy sertifikat ke folder ssl/
mkdir -p ssl
cp /etc/letsencrypt/live/waskita.site/fullchain.pem ssl/
cp /etc/letsencrypt/live/waskita.site/privkey.pem ssl/
```

#### Opsi B: Self-Signed Certificate (Testing)
```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout ssl/privkey.pem -out ssl/fullchain.pem -days 365 -nodes -subj "/CN=waskita.site"
```

### 8.2 Konfigurasi Environment Production

Edit file `.env.production`:
```bash
# SSL Configuration
ENABLE_SSL=true
NGINX_SERVER_NAME=waskita.site
SSL_CERT_PATH=/etc/nginx/ssl/fullchain.pem
SSL_KEY_PATH=/etc/nginx/ssl/privkey.pem

# Port Configuration  
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# Database Production
POSTGRES_DB=waskita_prod
POSTGRES_USER=admin
POSTGRES_PASSWORD=password_production_strong

# Security
SECRET_KEY=your_production_secret_key_here
DEBUG=false
```

### 8.3 Setup Domain & DNS

#### Untuk Testing Lokal:
```bash
# Edit file hosts
# C:\Windows\System32\drivers\etc\hosts
127.0.0.1       waskita.site
127.0.0.1       www.waskita.site
```

#### Untuk Production Server:
1. Beli domain (waskita.site)
2. Setup DNS A record ke server IP Anda
3. Setup reverse proxy jika diperlukan

### 8.4 Deployment Production

```bash
# Build dan jalankan production environment
.\install-build.ps1 -Production -Clean

# Atau manual dengan docker-compose
docker-compose -f docker/docker-compose.yml up --build -d
```

### 8.5 Verifikasi SSL

```bash
# Test SSL certificate
curl -vI https://waskita.site

# Test HTTP to HTTPS redirect  
curl -I http://waskita.site

# Check security headers
curl -s -D - https://waskita.site -o /dev/null
```

## 9. Script install-build.ps1

Script `install-build.ps1` mendukung kedua mode:

### Development Mode (HTTP-only)
```powershell
.\install-build.ps1              # Mode development default
.\install-build.ps1 -Clean       # Fresh install development
```

### Production Mode (SSL)
```powershell
.\install-build.ps1 -Production    # Mode production dengan SSL
.\install-build.ps1 -Production -Clean  # Fresh install production
```

### Help Documentation
```powershell
.\install-build.ps1 -Help
```

## 10. Troubleshooting

### Nginx Restart Loop
Jika Nginx restart terus, pastikan:
1. File sertifikat SSL ada di folder `ssl/`
2. Konfigurasi `ENABLE_SSL` sesuai dengan environment
3. Gunakan file compose yang tepat (http-only vs production)

### SSL Certificate Errors
```bash
# Regenerate sertifikat jika perlu
openssl req -x509 -newkey rsa:4096 -keyout ssl/privkey.pem -out ssl/fullchain.pem -days 365 -nodes -subj "/CN=localhost"
```

## 11. Rekomendasi Setup

- Development (disarankan)
  - Jalankan dengan Docker Compose untuk lingkungan konsisten: `docker-compose -f docker/docker-compose.local.yml up --build`
  - Gunakan `.env` dari template: `cp .env.example .env`
  - Verifikasi status aplikasi via health endpoint `GET /api/health` (di `routes.py:7159`): `curl http://localhost:5000/api/health`
  - Migrasi database dan pembuatan admin dari container: `docker-compose -f docker/docker-compose.local.yml exec web flask db upgrade` dan `docker-compose -f docker/docker-compose.local.yml exec web python create_admin.py`
  - Resource nyaman: 2 vCPU, 4–8 GB RAM, 10 GB disk

- Production (direkomendasikan)
  - Pisahkan konfigurasi ke `.env.production`: `cp .env.example .env.production` dan sesuaikan `DATABASE_URL`, `REDIS_URL`, `ENABLE_SSL`, `NGINX_SERVER_NAME`
  - Deploy: `docker-compose -f docker/docker-compose.yml up --build -d`
  - Jalankan migrasi saat deploy: `docker-compose -f docker/docker-compose.yml exec web flask db upgrade`
  - Jalankan aplikasi dengan Gunicorn (contoh): `gunicorn -w 4 --threads 2 -b 0.0.0.0:5000 app:app`
  - Praktik keamanan: cookies `HttpOnly` dan `Secure`, password hash (Bcrypt), CORS sesuai domain frontend
  - Observability minimal: health check (`/api/health`), log aplikasi, log keamanan (`security.log`), metrics dasar (request/latensi)
  - Resource awal: 2–4 vCPU, 4–8 GB RAM, SSD 20+ GB; scale horizontal via `docker-compose up -d --scale web=2`

## 8. Konfigurasi SSL untuk Production

### 🚀 Overview Konfigurasi SSL

Aplikasi Waskita mendukung dua mode operasi:
- **Development**: HTTP-only mode (tanpa SSL)
- **Production**: HTTPS dengan SSL encryption

### ⚙️ Environment Variables untuk SSL

#### File `.env.production`:
```bash
# SSL Configuration
ENABLE_SSL=true
NGINX_SERVER_NAME=waskita.site
SSL_CERT_PATH=/etc/letsencrypt/live/waskita.site/fullchain.pem
SSL_KEY_PATH=/etc/letsencrypt/live/waskita.site/privkey.pem

# Port Configuration  
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# Database & Redis
DATABASE_URL=postgresql://user:pass@db:5432/db_waskita
REDIS_URL=redis://redis:6379/0
```

#### File `.env.docker` (Development):
```bash
# SSL Configuration - DISABLED untuk development
ENABLE_SSL=false
NGINX_SERVER_NAME=localhost

# Port Configuration
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
```

### 📋 Cara Setup SSL

#### 1. Menggunakan Let's Encrypt (Production Real)
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Generate certificate
certbot certonly --standalone -d waskita.site -d www.waskita.site

# Certificate akan disimpan di:
# /etc/letsencrypt/live/waskita.site/fullchain.pem
# /etc/letsencrypt/live/waskita.site/privkey.pem
```

#### 2. Self-Signed Certificate (Development/Testing)
```bash
# Script otomatis generate self-signed certificate
./install-build.ps1 -Production

# Atau manual:
openssl req -x509 -newkey rsa:4096 -keyout ssl/privkey.pem -out ssl/fullchain.pem -days 365 -nodes -subj "/CN=localhost"
```

#### 3. Menggunakan Existing Certificate
```bash
# Copy certificate ke folder ssl/
cp /path/to/your/certificate.crt ssl/fullchain.pem
cp /path/to/your/private.key ssl/privkey.pem
```

### 🐳 Docker Volume Mounts untuk SSL

#### Production (`docker-compose.yml`):
```yaml
volumes:
  - /etc/letsencrypt/live/waskita.site/fullchain.pem:/etc/nginx/ssl/fullchain.pem:ro
  - /etc/letsencrypt/live/waskita.site/privkey.pem:/etc/nginx/ssl/privkey.pem:ro
```

#### Development (`docker-compose.http-only.yml`):
```yaml
# Tidak ada volume mounts SSL - HTTP-only mode
```

### 🔧 Nginx SSL Configuration

File `docker/nginx.conf` sudah dikonfigurasi dengan:

```nginx
# HTTP redirect ke HTTPS
server {
    listen 80;
    server_name waskita.site www.waskita.site;
    return 301 https://$host$request_uri;
}

# HTTPS server dengan SSL
server {
    listen 443 ssl http2;
    server_name waskita.site www.waskita.site;
    
    # SSL certificates
    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    
    # SSL security settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers off;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
}
```

### 🚀 Deployment Commands

#### Production dengan SSL:
```bash
# Method 1: Automated script
./install-build.ps1 -Production

# Method 2: Manual docker-compose
docker-compose -f docker/docker-compose.yml up --build -d
```

#### Development tanpa SSL:
```bash
# Method 1: Automated script (HTTP-only)
./install-build.ps1

# Method 2: Manual dengan HTTP-only config
docker-compose -f docker/docker-compose.yml -f docker/docker-compose.http-only.yml up --build -d
```

### 🛠️ Troubleshooting SSL

#### Error: Certificate not found
```bash
# Check certificate exists
ls -la /etc/letsencrypt/live/waskita.site/

# Generate self-signed fallback
openssl req -x509 -newkey rsa:4096 -keyout ssl/privkey.pem -out ssl/fullchain.pem -days 365 -nodes -subj "/CN=localhost"
```

#### Error: Permission denied
```bash
# Fix certificate permissions
chmod 644 /etc/letsencrypt/live/waskita.site/*.pem
chown root:root /etc/letsencrypt/live/waskita.site/*.pem
```

#### Error: Nginx restart loop
```bash
# Fallback ke HTTP-only mode
./install-build.ps1
```

### ✅ Verification

#### Check SSL Certificate:
```bash
# Test HTTPS connection
curl -I https://waskita.site

# Check certificate details
openssl s_client -connect waskita.site:443 -servername waskita.site
```

#### Check HTTP Redirect:
```bash
# Test HTTP → HTTPS redirect
curl -I http://waskita.site
# Should return: 301 Moved Permanently + Location: https://waskita.site
```

### 🔄 Certificate Renewal

#### Let's Encrypt Auto-Renewal:
```bash
# Setup cron job untuk auto-renewal
0 12 * * * certbot renew --quiet && docker-compose -f /path/to/waskita-app/docker/docker-compose.yml exec nginx nginx -s reload
```

#### Manual Renewal:
```bash
# Renew certificate
certbot renew

# Reload Nginx
docker-compose -f docker/docker-compose.yml exec nginx nginx -s reload
```

## 9. Keunggulan Aplikasi

- Fitur fungsional
  - Manajemen peran: Admin memiliki CRUD penuh; User akses data milik sendiri
  - Upload & scraping dataset: CSV/XLSX, platform sosial (Twitter/Facebook/Instagram/TikTok)
  - Cleaning data: penghapusan emoji, link, tanda baca; siap untuk klasifikasi
  - Klasifikasi Naive Bayes: hasil Radikal/Non‑Radikal dengan probabilitas; tampil di halaman detail

- Keamanan
  - Validasi input melalui middleware; pencatatan ke `security.log` pada level aplikasi
  - Password di‑hash (Bcrypt), sesi aman, cookies `HttpOnly`/`Secure`, dukungan CORS

- Pengalaman UI
  - Soft UI Dashboard dengan Dark Mode default, responsif di desktop/tablet/ponsel

- Operasional
  - Health endpoint (`/api/health`) untuk monitoring dan readiness
  - Migrasi database (Flask‑Migrate) memudahkan evolusi skema
  - Notifikasi SweetAlert2 untuk feedback aksi penting

## 10. Static Files Management

### File Statis yang Disertakan:
- **CSS/JS**: File static untuk Soft UI Dashboard theme
- **Images**: Logo dan ikon aplikasi
- **Templates**: File HTML dengan integrasi Flask

### Konfigurasi:
- Static files disimpan di direktori `static/`
- Template files disimpan di direktori `templates/`
- Cache control diatur melalui Nginx untuk production
- Versioning untuk assets CSS/JS untuk menghindari cache issues

### Development:
- File static dilayani secara otomatis oleh Flask development server
- Perubahan pada file static langsung terlihat tanpa restart

### Production:
- Nginx meng-handle static files untuk performa optimal
- Compression (gzip/brotli) diaktifkan untuk CSS/JS
- Cache headers dioptimalkan untuk static assets