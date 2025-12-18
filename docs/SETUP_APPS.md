# 🚀 PANDUAN SETUP & DEPLOYMENT APLIKASI WASKITA

Panduan lengkap instalasi, konfigurasi, dan deployment aplikasi Waskita mulai dari Local Development hingga Production VPS.

---

## 📋 DAFTAR ISI
1. [Prasyarat Sistem](#1-prasyarat-sistem)
2. [Setup Awal (Wajib)](#2-setup-awal-wajib)
3. [Skenario 1: Menjalankan Secara Lokal (Tanpa Docker)](#3-skenario-1-menjalankan-secara-lokal-tanpa-docker)
4. [Skenario 2: Menjalankan dengan Docker (Lokal)](#4-skenario-2-menjalankan-dengan-docker-lokal)
5. [Skenario 3: Deployment ke VPS (Production)](#5-skenario-3-deployment-ke-vps-production)

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

---

## 3. Skenario 1: Menjalankan Secara Lokal (Tanpa Docker)

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

## 4. Skenario 2: Menjalankan dengan Docker (Lokal)

Cocok untuk menguji aplikasi dalam container yang mirip dengan produksi, tanpa menginstall PostgreSQL secara manual.

1.  **Pastikan `.env` sudah siap** (Lihat Langkah 2).
    
2.  **Jalankan Docker Compose Lokal**
    Gunakan konfigurasi khusus lokal yang mendukung *hot-reload* dan HTTP (tanpa SSL).
    ```bash
    docker-compose -f docker/docker-compose.local.yml up --build
    ```

3.  **Akses Aplikasi**
    Buka browser: `http://localhost:8080`
    *(Catatan: Docker lokal menggunakan port 8080 agar tidak bentrok dengan service lain)*

---

## 5. Skenario 3: Deployment ke VPS (Production)

Cocok untuk membuat aplikasi dapat diakses publik dengan domain, SSL/HTTPS, dan performa tinggi.

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
    docker-compose -f docker/docker-compose.yml up -d --build
    ```
