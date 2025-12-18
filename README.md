# 📡 Waskita — Analisis Konten Radikal

**Waskita** adalah aplikasi berbasis web yang dirancang untuk mendeteksi dan mengklasifikasikan konten radikal di media sosial menggunakan Machine Learning (Naive Bayes & IndoBERT). Aplikasi ini dilengkapi dengan dashboard analitik modern (Soft UI) untuk memantau tren penyebaran konten.

> **Status:** 🟢 Active Maintenance  
> **Versi:** 1.4 (Februari 2025)

---

## 🌟 Fitur Utama

*   **Klasifikasi Cerdas:** Menggunakan algoritma **Naive Bayes** yang diperkuat dengan **Word2Vec** dan **IndoBERT**.
*   **Multi-Platform Scraping:** Mendukung input data dari Twitter, TikTok, dan Facebook (via Apify).
*   **Preprocessing Otomatis:** Pembersihan teks (Emoji, URL, Simbol) secara otomatis sebelum analisis.
*   **Dashboard Interaktif:** Visualisasi data real-time dengan tema *Dark Mode* yang elegan.
*   **Sistem Keamanan:** Login berbasis Role (Admin/User), Verifikasi OTP Email, dan Proteksi CSRF/XSS.
*   **Manajemen Data:** Upload dataset (CSV/XLSX) dan ekspor hasil analisis.

---

## 🚀 Panduan Cepat (Quick Start)

Kami menyediakan dokumentasi terpisah untuk setiap kebutuhan Anda:

### 1. Instalasi & Deployment
Ingin menjalankan aplikasi di laptop atau server?
👉 **[Baca Panduan Setup & Deployment (docs/SETUP_APPS.md)](docs/SETUP_APPS.md)**
*   Setup Lokal (Development)
*   Menjalankan dengan Docker
*   Deployment ke VPS (Production)

### 2. Spesifikasi Sistem
Detail teknis mengenai hardware, software stack, dan arsitektur sistem.
👉 **[Lihat Spesifikasi Sistem (docs/SPECIFIKASI_SISTEM.md)](docs/SPECIFIKASI_SISTEM.md)**

### 3. Keamanan
Panduan keamanan, konfigurasi SSL, dan perlindungan data.
👉 **[Baca Panduan Keamanan (docs/SECURITY_GUIDE.md)](docs/SECURITY_GUIDE.md)**

---

## 🛠️ Cara Menjalankan (Singkat)

### A. Menggunakan Docker (Rekomendasi)
```bash
# 1. Setup Environment
python src/backend/setup_postgresql.py

# 2. Jalankan Container
docker-compose -f docker/docker-compose.local.yml up --build

# 3. Akses Aplikasi
# Buka http://localhost:8080
```

### B. Menggunakan Python Lokal
```bash
# 1. Install Dependensi
pip install -r requirements.txt

# 2. Setup Database & Env
python src/backend/setup_postgresql.py

# 3. Migrasi Database
flask db upgrade

# 4. Jalankan Aplikasi
flask run
# Buka http://localhost:5000
```

---

## 📂 Struktur Project

```
waskita-app/
├── docker/                 # Konfigurasi Docker (Dockerfile, Compose, Nginx)
├── docs/                   # Dokumentasi Lengkap (Setup, Security, Specs)
├── scripts/                # Script Utilitas (Deploy VPS)
├── src/
│   ├── backend/            # Source Code Backend (Flask)
│   │   ├── blueprints/     # Modul/Rute Aplikasi
│   │   ├── models/         # Definisi Database (SQLAlchemy)
│   │   ├── services/       # Logika Bisnis (Cleaning, Scraping)
│   │   └── utils/          # Fungsi Pembantu (ML, Security)
│   └── frontend/           # Source Code Frontend
│       ├── static/         # CSS, JS, Images
│       └── templates/      # File HTML (Jinja2)
├── .env.example            # Template Environment Variables
├── README.md               # File ini
└── requirements.txt        # Daftar Dependensi Python
```

---

## 🤝 Kontribusi

Silakan buat **Issue** atau **Pull Request** jika Anda menemukan bug atau ingin menambahkan fitur baru. Pastikan untuk mengikuti panduan keamanan yang ada.

---

**Copyright © 2025 Waskita Team.**  
Developed for Academic Research on Radical Content Detection.
