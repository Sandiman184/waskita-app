# Waskita — Aplikasi Klasifikasi Konten Radikal

Aplikasi web Flask untuk klasifikasi konten media sosial (Radikal/Non‑Radikal) dengan Naive Bayes dan UI Soft UI Dashboard. Aplikasi ini dikembangkan untuk penelitian akademis dalam bidang analisis sentimen dan deteksi konten radikal pada media sosial.

Versi Dokumen: 1.3 — Diperbarui: 2025-01-15

## Tujuan Akademis
- **Domain Penelitian**: Analisis sentimen dan klasifikasi teks untuk deteksi konten radikal
- **Kontribusi Akademis**: Pengembangan model machine learning untuk identifikasi konten berbahaya secara otomatis
- **Batasan Penelitian**: Fokus pada konten berbahasa Indonesia dengan dataset media sosial terbatas

## Fitur Singkat
- Login/Register dengan role Admin/User dan OTP (opsional)
- Upload dataset CSV/XLSX, scraping via Apify (opsional)
- Cleaning teks otomatis (emoji, link, tanda baca)
- Klasifikasi dan probabilitas hasil
- Dark/Light mode, notifikasi SweetAlert2
- UI Profile dengan Timeline Recent Activities
- UI default bahasa Indonesia

## 🚀 Quick Deployment Guide

### Development Options:

#### 1. Local Development
```bash
# Clone repository
git clone https://github.com/Sandiman184/waskita-app.git
cd waskita-app

# Setup environment
cp .env.example .env
# Edit .env dengan konfigurasi lokal
# PENTING: Set DISABLE_MODEL_LOADING=True jika belum memiliki file model

# Install dependencies & run
pip install -r requirements.txt
python setup_postgresql.py
python app.py
```

#### 2. Docker Development
```bash
# Gunakan .env.docker untuk development
cp .env.example .env.docker
# Edit .env.docker (ENABLE_SSL=false, NGINX_SERVER_NAME=localhost)

docker-compose -f docker/docker-compose.local.yml up --build
```

#### 3. Docker Production
```bash
# Gunakan .env.production untuk production  
cp .env.example .env.production
# Edit .env.production (ENABLE_SSL=true, NGINX_SERVER_NAME=yourdomain.com)

# Pastikan variabel berikut ada di .env.production:
# - DATABASE_URL (contoh: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB})
# - REDIS_URL (contoh: redis://redis:6379/0)

docker-compose -f docker/docker-compose.yml up --build -d
```

#### 4. Automated VPS Deployment
```bash
# Script otomatis untuk VPS
./install-build.ps1 -Production
```

### Access Points:
- **Development**: http://localhost:5000/
- **Production**: https://yourdomain.com/ (dengan SSL)

### Environment Files:
- `.env` - Local development
- `.env.docker` - Docker development (SSL disabled)  
- `.env.production` - Docker production (SSL enabled)

### Deployment Workflow

#### Development Flow:
1. **Code** → **Test Locally** → **Docker Test** → **Commit** → **Push**

#### Production Flow:
1. **Setup VPS** → **Configure Domain** → **Deploy with SSL** → **Monitor**

#### Quick Commands:
```bash
# Development
docker-compose -f docker/docker-compose.local.yml up --build

# Production  
docker-compose -f docker/docker-compose.yml up --build -d

# Automated VPS
./install-build.ps1 -Production
```

## 📖 Dokumentasi Lengkap

Untuk konfigurasi SSL yang lengkap, setup production, dan troubleshooting, silakan lihat dokumentasi detail:

- **[Konfigurasi SSL untuk Production](docs/SETUP_APPS.md#8-konfigurasi-ssl-untuk-production)** - Panduan lengkap setup SSL dengan Let's Encrypt dan self-signed certificates
- **[Script install-build.ps1](docs/SETUP_APPS.md#9-script-install-buildps1)** - Dokumentasi parameter dan penggunaan script deployment otomatis
- **[Troubleshooting](docs/SETUP_APPS.md#10-troubleshooting)** - Solusi untuk masalah umum selama deployment

### Konfigurasi SSL Penting:
- **Let's Encrypt**: Untuk production dengan domain nyata
- **Self-signed**: Untuk testing production di localhost
- **Environment Variables**: `ENABLE_SSL=true`, `NGINX_SERVER_NAME=yourdomain.com`

### Script install-build.ps1:
```powershell
# Development mode (HTTP-only)
.\install-build.ps1 -Clean

# Production mode (SSL enabled)  
.\install-build.ps1 -Production -Clean

# Help information
.\install-build.ps1 -Help
```

## Konfigurasi Penting

### Database Configuration:
- **Development**: `DATABASE_URL=postgresql://user:pass@localhost:5432/db`
- **Docker**: Otomatis menggunakan service name `db`

### Security Settings:
- `SECRET_KEY` - Wajib, generate dengan: `python -c "import secrets; print(secrets.token_hex(32))"`
- `OTP_ENABLED` - `False` untuk development, `True` untuk production
- **Logging**: Log tersimpan terpusat di folder `logs/` (absolute path)
- **Rate Limiting**: Aktif untuk login dan API endpoints

### Optional Services:
- Email: `MAIL_USERNAME`, `MAIL_PASSWORD`
- Apify: `APIFY_API_TOKEN` untuk scraping data

## Arsitektur Sistem
- `nginx` sebagai reverse proxy dan terminasi SSL
- `web` (Flask + Gunicorn) sebagai aplikasi utama
- `db` (PostgreSQL) untuk penyimpanan data
- `redis` untuk caching dan rate limiting
- Model ML (Word2Vec, Naive Bayes) dimuat saat startup

## Endpoint Penting
- `GET /api/health` — status aplikasi dan database
- `GET /api/models-status` — status pemuatan model ML
- `GET /login` — halaman login
- `GET /` — redirect ke dashboard/login

## Quick Verification
- **Local**: http://localhost:5000/
- **Docker**: 
  ```bash
  docker-compose -f docker/docker-compose.yml ps
  docker-compose -f docker/docker-compose.yml logs -f web
  ```

## Dokumentasi Lengkap
- `docs/SETUP_APPS.md` — langkah detail instalasi dan konfigurasi
- `docs/SECURITY_GUIDE.md` — keamanan, OTP, sesi, CORS

## Referensi Akademis
Aplikasi ini dikembangkan untuk mendukung penelitian dalam bidang:
- **Natural Language Processing (NLP)** untuk bahasa Indonesia
- **Machine Learning** untuk klasifikasi teks
- **Web Application Development** dengan framework Flask
- **Database Management** dengan PostgreSQL

## Kontribusi
Untuk berkontribusi pada pengembangan aplikasi ini:
1. Fork repository
2. Buat branch untuk fitur baru (`git checkout -b feature/namafitur`)
3. Commit perubahan (`git commit -m 'Menambahkan fitur xyz'`)
4. Push ke branch (`git push origin feature/namafitur`)
5. Buat Pull Request

## Lisensi
Lihat [LICENSE](LICENSE) di repository.