# Waskita — Aplikasi Klasifikasi Konten Radikal

Aplikasi web Flask untuk klasifikasi konten media sosial (Radikal/Non‑Radikal) dengan Naive Bayes dan UI Soft UI Dashboard. Aplikasi ini dikembangkan untuk penelitian akademis dalam bidang analisis sentimen dan deteksi konten radikal pada media sosial.

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

## Alur Kerja Aplikasi

### Diagram Alur Pengembangan
```
Clone Repository → Setup Environment → Konfigurasi Database → Jalankan Aplikasi
       │                  │                    │                    │
       │                  │                    │              Development Mode
       │                  │              (Lokal/Docker)          atau
       │            (Virtual Env)                           Production Mode
       │                  │
       │            Install Dependencies
       │
GitHub Repository
```

### Quick Start

#### 1. Clone Repository
```bash
git clone https://github.com/Sandiman184/waskita-app.git
cd waskita-app
```

#### 2. Setup Environment
##### Lokal (Development)
Windows (PowerShell):
```powershell
python -m venv venv
```
```powershell
venv\Scripts\activate
```
```powershell
pip install -r requirements.txt
```
```powershell
copy .env.example .env
```

Linux/Mac (bash):
```bash
python -m venv venv
```
```bash
source venv/bin/activate
```
```bash
pip install -r requirements.txt
```
```bash
cp .env.example .env
```

- Minimal `.env`:
  - `DATABASE_URL=postgresql://<user>:<pass>@localhost:5432/<db>`
  - `SECRET_KEY=<random_string>`
  - `OTP_ENABLED=False` (disarankan untuk dev)

#### 3. Konfigurasi Database
```powershell
python setup_postgresql.py
```

#### 4. Jalankan Aplikasi (Development Mode)
```powershell
python app.py
```

- Akses: `http://localhost:5000/`

### Docker (Production Ready)
#### Prerequisites Docker
- Pastikan `.env` sudah dikonfigurasi dengan benar
- Opsional set untuk Docker:
  - `DATABASE_URL_DOCKER=postgresql://<user>:<pass>@waskita-app-postgres:5432/<db>`
    - atau gunakan `host.docker.internal:5432` jika menggunakan Postgres lokal dari container
- Compose menggunakan fallback: `DATABASE_URL=${DATABASE_URL_DOCKER:-${DATABASE_URL}}`

#### Build dan Jalankan dengan Docker
Windows (PowerShell):
```powershell
./install-build.ps1
```

Manual build:
```bash
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d
```

- Akses: `http://localhost:5000/`

### Workflow Pengembangan

#### Development Workflow
1. **Setup Awal**: Clone repository dan setup environment
2. **Development**: Modifikasi kode dan test secara lokal
3. **Testing**: Jalankan aplikasi dan verifikasi fungsionalitas
4. **Commit**: Simpan perubahan dengan pesan commit yang jelas
5. **Push**: Kirim perubahan ke repository GitHub

#### Production Deployment
1. **Build Docker Image**: `docker compose -f docker/docker-compose.yml build`
2. **Deploy Container**: `docker compose -f docker/docker-compose.yml up -d`
3. **Monitoring**: Pantau log aplikasi untuk memastikan berjalan normal
4. **Scaling**: Sesuaikan resource berdasarkan kebutuhan

### Opsi B — Satu sumber DATABASE_URL (direkomendasi dengan fallback)
- Gunakan satu `DATABASE_URL` di `.env` untuk lokal.
- Untuk Docker, Anda boleh set `DATABASE_URL_DOCKER`; jika tidak ada, container fallback ke `DATABASE_URL`.
- Compose sudah menerapkan: `DATABASE_URL=${DATABASE_URL_DOCKER:-${DATABASE_URL}}`.

Contoh `.env` minimal:
```env
DATABASE_URL=postgresql://user:pass@localhost:5432/db
# Opsional untuk Docker (diprioritaskan di container jika ada):
DATABASE_URL_DOCKER=postgresql://user:pass@waskita-app-postgres:5432/db
```

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