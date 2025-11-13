# Instalasi & Persiapan Awal

Dokumen ini menjelaskan langkah instalasi dan persiapan awal aplikasi Waskita untuk keperluan pengembangan (development) dan produksi (production) tanpa duplikasi, sesuai outline yang diinginkan.

Versi Dokumen: 1.1 — Diperbarui: 2025-11-13

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

## 8. Rekomendasi Setup

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