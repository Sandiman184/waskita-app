# Waskita — Aplikasi Klasifikasi Konten Radikal

Aplikasi web Flask untuk klasifikasi konten media sosial (Radikal/Non‑Radikal) dengan Naive Bayes dan UI Soft UI Dashboard.

## Fitur Singkat
- Login/Register dengan role Admin/User dan OTP (opsional)
- Upload dataset CSV/XLSX, scraping via Apify (opsional)
- Cleaning teks otomatis (emoji, link, tanda baca)
- Klasifikasi dan probabilitas hasil
- Dark/Light mode, notifikasi SweetAlert2

## Quick Start

### Lokal (Development)
Windows (PowerShell):
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python setup_postgresql.py
python app.py
```

Linux/Mac (bash):
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python setup_postgresql.py
python app.py
```

- Minimal `.env`:
  - `DATABASE_URL=postgresql://<user>:<pass>@localhost:5432/<db>`
  - `SECRET_KEY=<random_string>`
  - `OTP_ENABLED=False` (disarankan untuk dev)
  

### Docker
- Pastikan `.env` sudah ada. Opsional set:
  - `DATABASE_URL_DOCKER=postgresql://<user>:<pass>@waskita-app-postgres:5432/<db>`
    - atau gunakan `host.docker.internal:5432` jika pakai Postgres lokal dari container
- Compose memakai fallback: `DATABASE_URL=${DATABASE_URL_DOCKER:-${DATABASE_URL}}`

Windows (PowerShell):
```powershell
./install-build.ps1
```

- Akses: `http://localhost:5000/`

## Konfigurasi Penting
- `DATABASE_URL` (wajib, untuk lokal)
- `DATABASE_URL_DOCKER` (opsional, diprioritaskan oleh container)
- `SECRET_KEY` (wajib)
- `OTP_ENABLED` (`False` untuk dev, `True` untuk produksi bila OTP diperlukan)
- Email/Apify (opsional): `MAIL_USERNAME`, `MAIL_PASSWORD`, `APIFY_API_TOKEN`

## Verifikasi Cepat
- Lokal: buka `http://localhost:5000/`
- Docker:
  - `docker compose -f docker\docker-compose.yml ps`
  - `docker compose -f docker\docker-compose.yml logs -f web`

## Dokumentasi Lengkap
- `docs/SETUP_APPS.md` — langkah detail instalasi dan konfigurasi
- `docs/SECURITY_GUIDE.md` — keamanan, OTP, sesi, CORS

## Lisensi
Lihat [LICENSE](LICENSE) di repository.