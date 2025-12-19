# 🚀 PANDUAN SETUP & DEPLOYMENT APLIKASI WASKITA

Panduan lengkap instalasi, konfigurasi, dan deployment aplikasi Waskita mulai dari Local Development hingga Production VPS.

---

## 📋 DAFTAR ISI
1. [Prasyarat Sistem](#1-prasyarat-sistem)
2. [Setup Awal (Wajib)](#2-setup-awal-wajib)
3. [Manajemen Model AI (Pembaruan)](#3-manajemen-model-ai-pembaruan)
4. [Skenario 1: Menjalankan Secara Lokal (Tanpa Docker)](#4-skenario-1-menjalankan-secara-lokal-tanpa-docker)
5. [Skenario 2: Menjalankan dengan Docker (Lokal)](#5-skenario-2-menjalankan-dengan-docker-lokal)
6. [Skenario 3: Deployment ke VPS (Production)](#6-skenario-3-deployment-ke-vps-production)
7. [Troubleshooting Umum](#7-troubleshooting-umum)

---

## 1. Prasyarat Sistem

Pastikan perangkat Anda memiliki:
*   **Git**
*   **Python 3.10+** (Untuk menjalankan lokal/script setup)
*   **Docker & Docker Compose** (Untuk skenario Docker)
*   **PostgreSQL 14+** (Hanya jika menjalankan lokal tanpa Docker)

---

## 2. Setup Awal (Wajib)

Lakukan langkah ini setelah cloning repository untuk menyiapkan konfigurasi dasar.

1.  **Clone Repository**
    ```bash
    git clone https://github.com/Sandiman184/waskita-app.git
    cd waskita-app
    ```

2.  **Jalankan Script Setup Otomatis**
    Kami menyediakan script cerdas untuk menyiapkan environment variables (`.env`) dan database.
    ```bash
    # Windows / Linux / Mac
    python src/backend/setup_postgresql.py
    ```

    **Apa yang dilakukan script ini?**
    *   Membuat file `.env` dari template.
    *   Meng-generate **SECRET_KEY** dan **JWT_SECRET_KEY** yang aman secara otomatis.
    *   Meminta input interaktif untuk konfigurasi penting (Email SMTP, Database Password, API Keys).
    *   Membuat database PostgreSQL lokal (jika ada).
    *   Menginstall dependensi Python (`requirements.txt`).

3.  **Setup Model Machine Learning (Penting)**
    Aplikasi ini membutuhkan file model ML yang berukuran besar dan tidak disertakan dalam repository.
    
    Pastikan struktur folder `models/` Anda seperti berikut:
    ```
    models/
    ├── embeddings/
    │   └── word2vec_model.joblib             (Wajib untuk ekstraksi fitur)
    ├── classifiers/
    │   ├── Naive Bayes_classifier_model.joblib
    │   ├── SVM_classifier_model.joblib
    │   └── ... (Model klasifikasi lainnya)
    └── indobert/
        └── ... (File model IndoBERT)
    ```
    *Jika file model belum ada, silakan hubungi administrator project atau jalankan pipeline training.*

---

## 3. Manajemen Model AI (Pembaruan)

Aplikasi menyediakan antarmuka Admin Panel untuk mengelola model AI (IndoBERT, Word2Vec, dll).

### Fitur Update Model (Anti-Locking)
Sistem telah dilengkapi dengan mekanisme robust untuk menangani update model, terutama pada lingkungan Windows dimana file sering terkunci (`[WinError 32]`).

**Alur Kerja Update Model:**
1.  Masuk ke **Admin Panel > AI Model Management**.
2.  Upload file model baru (mendukung chunked upload untuk file besar > 1GB).
3.  **Jika di Linux/Docker:** Model akan langsung terupdate tanpa downtime.
4.  **Jika di Windows:**
    *   Jika file sedang digunakan, sistem akan menyimpan update sebagai `.pending`.
    *   Anda akan diminta untuk melakukan **Restart Server**.
    *   Gunakan tombol **"Restart Server Now"** yang tersedia di halaman tersebut.
    *   Saat restart, sistem otomatis:
        *   Menerapkan file `.pending` menjadi model utama.
        *   Membersihkan file sampah (`.tmp`, `.old`) yang tidak terpakai.

---

## 4. Skenario 1: Menjalankan Secara Lokal (Tanpa Docker)

Cocok untuk pengembangan fitur cepat (coding & debugging).

1.  **Aktifkan Virtual Environment**
    ```bash
    # Windows
    python -m venv venv
    venv\Scripts\activate
    
    # Linux/Mac
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Migrasi Database**
    Pastikan database sudah dibuat via script setup di atas, lalu jalankan migrasi tabel:
    ```bash
    flask db upgrade
    ```

3.  **Jalankan Aplikasi**
    ```bash
    flask run
    ```
    Akses di: `http://localhost:5000`

---

## 5. Skenario 2: Menjalankan dengan Docker (Lokal)

Cocok untuk menguji aplikasi dalam container yang mirip dengan produksi, tanpa menginstall PostgreSQL secara manual.

### Konfigurasi & Dampak Perubahan Terbaru (Desember 2025)
*   **Upload Besar:** Mendukung upload model hingga 10GB.
*   **File Locking:** Docker (Linux) tidak terpengaruh isu file locking Windows. Mekanisme Shadow Copy otomatis non-aktif.
*   **Restart Server:** Fitur restart di Admin Panel berfungsi dengan me-restart Gunicorn worker, memuat ulang model tanpa perlu mematikan container.

### Langkah Menjalankan:

1.  **Build & Run Container**
    Gunakan file compose khusus lokal (`docker-compose.local.yml`) yang dikonfigurasi untuk development (Hot-reload, HTTP only).
    ```bash
    # Perintah ini akan mem-build ulang image dan menjalankan container
    docker-compose -f docker/docker-compose.yml -f docker/docker-compose.local.yml up --build
    ```
    *Catatan: Flag `--build` sangat penting saat pertama kali setelah update kode agar perubahan Dockerfile/Environment terbaca.*

2.  **Verifikasi Container Berjalan**
    Pastikan 3 service utama aktif: `web`, `db`, dan `nginx`.
    ```bash
    docker ps
    ```

3.  **Akses Aplikasi**
    Buka browser dan akses alamat berikut (via Nginx Proxy):
    👉 **http://localhost:8080**
    *(Jangan akses port 5000, karena itu adalah port internal container aplikasi).*

4.  **Menghentikan Aplikasi**
    ```bash
    docker-compose -f docker/docker-compose.local.yml down
    ```
    *Gunakan `down -v` jika ingin menghapus volume database (reset data).*

### Troubleshooting Docker Lokal
*   **Upload Gagal / Timeout:** Pastikan Anda mengakses via `localhost:8080` (Nginx).
*   **Database Error:** Jika terjadi error koneksi DB saat awal start, tunggu beberapa detik.

### Cara Mudah (Windows PowerShell)
```powershell
# Jalankan Docker (Build & Run)
.\install-build.ps1

# Jika ingin instalasi bersih (Hapus database lama & mulai dari nol)
.\install-build.ps1 -Clean
```

---

## 6. Skenario 3: Deployment ke VPS (Production)

Untuk lingkungan produksi dengan keamanan SSL (HTTPS) dan performa optimal.

### Metode Otomatis (Recommended)
Gunakan script `deploy-vps.ps1` dari komputer lokal Anda (Windows PowerShell).

**Persiapan:**
*   VPS Ubuntu/Debian bersih (Fresh Install).
*   Domain yang sudah diarahkan ke IP VPS (A Record).
*   Akses SSH root/user sudo.

**Perintah Deployment:**
```powershell
./scripts/deploy-vps.ps1 `
  -VpsHost "IP_ADDRESS_VPS" `
  -VpsUser "root" `
  -Domain "waskita.site" `
  -AdminEmail "admin@waskita.site" `
  -VpsPassword "password_ssh_anda"
```

**Apa yang dilakukan script ini?**
1.  Masuk ke VPS via SSH.
2.  Install Docker, Git, dan Certbot.
3.  Clone repository terbaru.
4.  Copy file `.env` lokal Anda ke server sebagai `.env.production`.
5.  Generate sertifikat SSL (HTTPS) via Let's Encrypt.
6.  Build dan jalankan container Docker (Nginx + Gunicorn + DB).

### Metode Manual
Jika ingin deploy manual di server:
1.  SSH ke server.
2.  Clone repo & masuk direktori.
3.  Buat file `.env.production` (bisa copy dari lokal).
4.  Jalankan:
    ```bash
    # Gunakan file compose prod untuk konfigurasi SSL & Nginx yang benar
    docker-compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml --env-file .env.production up -d --build
    ```

Akses aplikasi di: `https://domain-anda.com`

---

## 7. Troubleshooting Umum

### Database Error "DuplicateTable"
*   **Penyebab:** Database diinisialisasi ulang tanpa menghapus volume lama yang korup.
*   **Solusi:** Jalankan `.\install-build.ps1 -Clean` untuk reset total.

### Error "File Word2Vec model tidak ditemukan"
*   **Penyebab:** File `word2vec_model.joblib` tidak ada di folder `models/embeddings/`.
*   **Solusi:** Download file model dari penyimpanan cloud tim dan letakkan di folder tersebut. Restart container.

### Permission Denied (Uploads)
*   **Penyebab:** User Docker tidak punya akses tulis ke folder host.
*   **Solusi:** Script build otomatis menangani ini (`chmod 775`). Jika masih gagal, jalankan manual: `chmod -R 775 uploads/` di Linux/Mac.

---

## 8. Referensi Lanjutan
*   [Spesifikasi Sistem](SPECIFIKASI_SISTEM.md) - Detail hardware & software stack.
*   [Panduan Keamanan](SECURITY_GUIDE.md) - Standar keamanan & checklist admin.
