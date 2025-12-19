# 🚀 PANDUAN DEPLOYMENT APLIKASI WASKITA (PRODUCTION READY)

Dokumen ini berisi panduan lengkap **End-to-End Deployment** untuk aplikasi Waskita di lingkungan **Produksi (VPS/Server)**. Panduan ini dirancang untuk memastikan aplikasi berjalan dengan standar keamanan, performa, dan reliabilitas tinggi menggunakan **Docker** dan **Nginx**.

---

## 📋 DAFTAR ISI
1. [Persiapan Awal](#1-persiapan-awal)
2. [Instalasi Dependensi Server](#2-instalasi-dependensi-server)
3. [Konfigurasi Aplikasi](#3-konfigurasi-aplikasi)
4. [Inisialisasi Database](#4-inisialisasi-database)
5. [Build dan Deployment](#5-build-dan-deployment)
6. [Testing & Verifikasi](#6-testing--verifikasi)
7. [Dokumentasi & Maintenance](#7-dokumentasi--maintenance)
8. [Lampiran: Local Development](#lampiran-local-development)

---

## 1. Persiapan Awal

Langkah ini bertujuan menyiapkan kode sumber dan variabel lingkungan yang aman sebelum proses build dimulai.

### 1.1 Cloning Repository
Mengambil kode terbaru dari repository utama.

*   **Perintah Terminal:**
    ```bash
    # Masuk ke direktori home atau www
    cd /var/www/
    
    # Clone repository
    git clone https://github.com/Sandiman184/waskita-app.git
    
    # Masuk ke folder project
    cd waskita-app
    ```

*   **Verifikasi:**
    Jalankan `ls -la` dan pastikan folder `.git` serta struktur project terlihat.

### 1.2 Setup Environment Variables
Menyiapkan konfigurasi rahasia untuk produksi.

*   **Perintah Terminal:**
    ```bash
    # Copy template environment khusus Docker
    cp .env.example.docker .env
    
    # Edit file .env
    nano .env
    ```

*   **Konfigurasi Kritis (.env):**
    Pastikan nilai berikut diubah untuk keamanan:
    ```ini
    FLASK_ENV=production
    DEBUG=False
    SECRET_KEY=<Gunakan string acak panjang & kompleks>
    JWT_SECRET_KEY=<Gunakan string acak panjang & kompleks>
    
    # Database (Gunakan password kuat)
    POSTGRES_PASSWORD=<Password_DB_Kuat>
    DATABASE_URL=postgresql://postgres:<Password_DB_Kuat>@db:5432/db_waskita
    
    # Email SMTP (Wajib untuk OTP & Notifikasi)
    MAIL_USERNAME=email_notifikasi@gmail.com
    MAIL_PASSWORD=app_password_google
    ```

*   **Tujuan:** Memisahkan konfigurasi rahasia dari kode program (12-Factor App methodology).

---

## 2. Instalasi Dependensi Server

Menyiapkan server (Ubuntu/Debian) dengan runtime yang dibutuhkan.

### 2.1 Install Docker & Docker Compose
Waskita berjalan di atas container untuk isolasi dan konsistensi.

*   **Perintah Terminal:**
    ```bash
    # Update repository
    sudo apt-get update
    
    # Install paket dasar
    sudo apt-get install -y ca-certificates curl gnupg
    
    # Install Docker Engine & Plugin Compose
    sudo apt-get install -y docker.io docker-compose-plugin
    
    # Start & Enable Docker
    sudo systemctl enable docker
    sudo systemctl start docker
    ```

*   **Verifikasi:**
    ```bash
    docker --version
    docker compose version
    ```
    *Output Diharapkan:* Menampilkan versi Docker (misal: `24.0.x`) dan Docker Compose (misal: `v2.x`).

---

## 3. Konfigurasi Aplikasi

Menyiapkan layanan pendukung seperti Nginx dan SSL.

### 3.1 Setup Domain & SSL (Certbot)
Aplikasi produksi wajib menggunakan HTTPS.

*   **Perintah Terminal:**
    ```bash
    # Install Certbot
    sudo apt-get install -y certbot
    
    # Generate Sertifikat (Ganti domain.com dengan domain Anda)
    sudo certbot certonly --standalone -d waskita.site --email admin@waskita.site --agree-tos --no-eff-email
    ```

*   **Output Diharapkan:**
    Pesan `Successfully received certificate`. File sertifikat tersimpan di `/etc/letsencrypt/live/waskita.site/`.

*   **Tujuan:** Enkripsi trafik data antara user dan server (HTTPS).

### 3.2 Konfigurasi Nginx
Pastikan konfigurasi Nginx di `docker/nginx.conf` sudah sesuai dengan domain Anda (biasanya otomatis via volume mapping, tapi pastikan `server_name` di file conf jika hardcoded).

---

## 4. Inisialisasi Database

Menyiapkan skema database sebelum aplikasi dijalankan.

### 4.1 Jalankan Container Database
Nyalakan service database terlebih dahulu.

*   **Perintah Terminal:**
    ```bash
    docker compose -f docker/docker-compose.prod.yml up -d db
    ```

*   **Verifikasi:**
    ```bash
    docker compose ps
    ```
    Status service `db` harus `Up`.

### 4.2 Migrasi Database
Menerapkan struktur tabel terbaru.

*   **Perintah Terminal:**
    ```bash
    # Tunggu beberapa detik sampai DB siap, lalu:
    docker compose -f docker/docker-compose.prod.yml run --rm backend flask db upgrade
    ```

*   **Output Diharapkan:**
    Log SQLAlchemy menunjukkan proses migrasi berjalan (misal: `Running upgrade... -> c089d130b448`).

### 4.3 Seeding Data Awal (Admin)
Membuat user administrator pertama.

*   **Perintah Terminal:**
    ```bash
    docker compose -f docker/docker-compose.prod.yml run --rm backend python src/backend/create_admin.py
    ```

*   **Output Diharapkan:**
    `Admin user created/updated successfully.`

---

## 5. Build dan Deployment

Proses utama menjalankan seluruh aplikasi.

### 5.1 Build Image Produksi
Membangun image Docker yang teroptimasi.

*   **Perintah Terminal:**
    ```bash
    docker compose -f docker/docker-compose.prod.yml build
    ```

*   **Penjelasan:** Langkah ini mendownload base image Python, menginstall dependencies dari `requirements.txt`, dan menyalin kode aplikasi ke dalam image.

### 5.2 Menjalankan Layanan (Up)
Menjalankan semua container (Backend, Frontend/Nginx, DB, Redis) di background.

*   **Perintah Terminal:**
    ```bash
    docker compose -f docker/docker-compose.prod.yml up -d
    ```

*   **Verifikasi:**
    ```bash
    docker ps
    ```
    *Output Diharapkan:* Semua container (`waskita-backend`, `waskita-nginx`, `waskita-db`) berstatus **Up**.

---

## 6. Testing & Verifikasi

Memastikan aplikasi berjalan normal di lingkungan produksi.

### 6.1 Smoke Test (Koneksi HTTP)
Cek apakah server merespon request.

*   **Perintah Terminal:**
    ```bash
    curl -I https://waskita.site
    ```

*   **Output Diharapkan:**
    `HTTP/2 200` atau `302 Found` (jika redirect ke login).

### 6.2 Cek Logs Aplikasi
Memastikan tidak ada error runtime di backend.

*   **Perintah Terminal:**
    ```bash
    docker compose -f docker/docker-compose.prod.yml logs --tail=50 backend
    ```

*   **Verifikasi:**
    Tidak ada pesan `Error`, `Traceback`, atau `Critical`. Log harus menunjukkan `Gunicorn running` atau `Listening at: port 5000`.

### 6.3 Test Login
Buka browser, akses `https://waskita.site`, dan coba login dengan akun admin yang dibuat di langkah 4.3.

---

## 7. Dokumentasi & Maintenance

Langkah perawatan rutin untuk menjaga stabilitas sistem.

### 7.1 Backup Database
Lakukan backup rutin.

*   **Perintah:**
    ```bash
    # Backup ke file SQL
    docker compose -f docker/docker-compose.prod.yml exec db pg_dump -U postgres db_waskita > backup_$(date +%F).sql
    ```

### 7.2 Update Aplikasi
Cara memperbarui aplikasi jika ada perubahan kode.

*   **Langkah:**
    1.  `git pull origin main`
    2.  `docker compose -f docker/docker-compose.prod.yml up -d --build` (Build ulang image)
    3.  `docker compose -f docker/docker-compose.prod.yml run --rm backend flask db upgrade` (Jika ada perubahan DB)

### 7.3 Troubleshooting Umum
*   **502 Bad Gateway:** Biasanya Backend belum siap atau crash. Cek logs: `docker compose logs backend`.
*   **Database Connection Refused:** Pastikan kredensial di `.env` sama persis dengan yang digunakan service `db`.

---

## Lampiran: Local Development

Untuk pengembang yang ingin menjalankan di laptop (Non-Production).

1.  **Tanpa Docker:**
    *   Install Python 3.10+ & PostgreSQL.
    *   `pip install -r requirements.txt`
    *   `flask run`
2.  **Dengan Docker (Lokal):**
    *   `docker compose -f docker/docker-compose.local.yml up --build`
    *   Akses: `http://localhost:8080`
