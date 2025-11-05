# 🚀 Waskita - Aplikasi Klasifikasi Konten Radikal

Aplikasi web untuk klasifikasi konten media sosial menggunakan machine learning dengan algoritma Naive Bayes.

## ✨ Fitur Utama

- 🔐 **Sistem Autentikasi** - Login/Register dengan role management (Admin/User)
- 📊 **Dashboard Interaktif** - Monitoring data dan hasil klasifikasi
- 📁 **Manajemen Dataset** - Upload dan kelola dataset CSV/XLSX
- 🕷️ **Web Scraping** - Scraping data dari Twitter, Facebook, Instagram, TikTok
- 🧹 **Data Cleaning** - Pembersihan data otomatis (emoji, link, tanda baca)
- 🤖 **Klasifikasi ML** - Klasifikasi Radikal/Non-Radikal dengan Naive Bayes
- 🎨 **UI Modern** - Soft UI Dashboard dengan Dark/Light mode
- 📧 **Notifikasi Email** - Sistem notifikasi dan OTP

## 🛠️ Teknologi

- **Backend**: Python Flask
- **Database**: PostgreSQL
- **Frontend**: HTML, CSS, JavaScript (Soft UI Dashboard)
- **ML**: Scikit-learn, Word2Vec
- **Scraping**: Apify API

## 📋 Persyaratan Sistem

- Python 3.8+
- PostgreSQL 12+
- Git

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/Sandiman184/waskita-app.git
cd waskita-app
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Setup Environment

```bash
# Copy file environment
cp .env.example .env

# Edit .env dengan konfigurasi Anda
# Minimal yang perlu diubah:
# - DATABASE_PASSWORD
# - SECRET_KEY
# - MAIL_USERNAME & MAIL_PASSWORD (opsional)
```

### 4. Setup Database

```bash
# Jalankan setup otomatis
python setup_postgresql.py
```

Script ini akan:
- ✅ Membuat database PostgreSQL
- ✅ Membuat user database
- ✅ Membuat semua tabel (termasuk tabel OTP untuk sistem registrasi)
- ✅ Membuat admin user default
- ✅ Update file .env dengan konfigurasi lengkap

**Fitur Database Terbaru (Januari 2025):**
- ✅ Sistem OTP untuk registrasi dan login pertama
- ✅ Tabel `registration_requests` untuk mengelola pendaftaran pengguna
- ✅ Tabel `admin_notifications` untuk notifikasi admin
- ✅ Tabel `otp_email_logs` untuk logging email OTP
- ✅ Index yang dioptimalkan untuk performa query
- ✅ Sistem audit trail untuk logging aktivitas pengguna
- ✅ Tabel klasifikasi dengan probabilitas confidence

### 5. Jalankan Aplikasi

```bash
python app.py
```

Aplikasi akan berjalan di: `http://localhost:5000`

**Status Aplikasi Saat Ini (Januari 2025):**
- ✅ **Development Mode**: Berjalan dengan konfigurasi development
- ✅ **Database**: PostgreSQL dengan schema lengkap
- ✅ **Authentication**: Sistem OTP aktif untuk keamanan
- ✅ **Machine Learning**: Model Naive Bayes dengan Word2Vec embedding
- ✅ **Security**: Middleware keamanan aktif (CORS, rate limiting, CSRF protection)
- ✅ **Documentation**: Dokumentasi lengkap tersedia di folder `docs/`

## 🔑 Default Login

Setelah setup berhasil:

```
Username: admin
Password: admin123
Email: admin@waskita.com
```

**Fitur Keamanan Terbaru (Januari 2025):**
- ✅ **OTP Verification**: Login pertama memerlukan verifikasi email OTP
- ✅ **Admin Approval**: Registrasi user baru memerlukan persetujuan admin
- ✅ **Rate Limiting**: Proteksi terhadap brute force attacks
- ✅ **Password Hashing**: Password disimpan dengan bcrypt hashing
- ✅ **Session Security**: HttpOnly cookies dengan secure flags

⚠️ **Penting**: Ganti password default setelah login pertama dan setup email SMTP untuk fitur OTP!

## 📁 Struktur Project (Januari 2025)

```
waskita-app/
├── app.py                 # Main application
├── config.py             # Configuration
├── models.py             # Database models (termasuk OTP)
├── routes.py             # Main routes
├── otp_routes.py         # Routes untuk sistem OTP
├── setup_postgresql.py   # Database setup
├── create_admin.py       # Script pembuatan admin user
├── docker/               # Konfigurasi Docker
│   ├── docker-compose.yml
│   ├── nginx.conf
│   ├── database_schema.sql
│   └── init_database.py
├── templates/            # HTML templates
│   ├── auth/            # Template autentikasi
│   ├── admin/           # Template admin panel
│   ├── classification/  # Template klasifikasi
│   └── dataset/         # Template manajemen dataset
├── static/              # CSS, JS, images
├── migrations/          # Database migrations
│   └── versions/        # Migration scripts
├── docs/               # Documentation
│   ├── SETUP_APPS.md    # Panduan setup lengkap
│   └── SECURITY_GUIDE.md # Panduan keamanan
├── security_middleware.py # Middleware keamanan
├── security_utils.py    # Utilities keamanan
├── security_logger.py   # Logging keamanan
└── email_service.py    # Service email
```

## 🔧 Konfigurasi Lanjutan

### Email Configuration (Opsional)

Untuk fitur notifikasi email, setup Gmail SMTP:

1. Enable 2FA di Gmail
2. Generate App Password
3. Update `.env`:

```env
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-16-digit-app-password
```

### API Keys (Opsional)

Untuk web scraping, daftar di [Apify](https://apify.com):

```env
APIFY_API_TOKEN=your-apify-token
```

## 🔬 Fitur Penelitian

### **Machine Learning Methodology**
- **Algoritma**: Naive Bayes dengan Word2Vec embedding
- **Akurasi**: 85-92% pada dataset uji
- **Preprocessing**: Tokenisasi, normalisasi teks bahasa Indonesia
- **Feature Extraction**: Word2Vec untuk representasi semantik

### **Security & Authentication**
- **Multi-layer Authentication**: Password hashing, OTP verification
- **Web Protection**: CSRF, rate limiting, input validation
- **Database Security**: SQLAlchemy ORM, parameterized queries

### **Research Data Management**
- **Multi-format Input**: CSV, XLSX, JSON untuk dataset
- **Data Validation**: Otomatis cleaning dan preprocessing
- **Export Capabilities**: Hasil klasifikasi dalam berbagai format

### **Analytics Dashboard**
- **Real-time Statistics**: Monitoring performa model
- **Visualization**: Chart dan grafik untuk analisis data
- **Audit Trail**: Logging aktivitas untuk penelitian

## 🛠️ Teknologi

- **Python** - Bahasa pemrograman utama
- **Flask** - Web framework
- **PostgreSQL** - Database
- **Scikit-learn** - Machine learning library
- **Word2Vec** - Text embedding
- **Bootstrap** - Frontend framework
- **Docker** - Containerization

## 📚 Dokumentasi Lengkap (Januari 2025)

- **[Setup Guide](docs/SETUP_APPS.md)** - Panduan instalasi detail untuk development dan production
- **[Security Guide](docs/SECURITY_GUIDE.md)** - Konfigurasi keamanan lengkap dengan best practices
- **Docker Deployment** - Konfigurasi container untuk production environment
- **API Documentation** - Endpoint dan integrasi sistem

## 🤝 Kontribusi Penelitian

Kontribusi untuk pengembangan penelitian ini sangat diterima dari komunitas akademik. Silakan:

1. Fork repository ini
2. Buat branch untuk fitur baru (`git checkout -b feature/fitur-baru`)
3. Commit perubahan (`git commit -m 'Tambah fitur baru'`)
4. Push ke branch (`git push origin feature/fitur-baru`)
5. Buat Pull Request

## 📄 Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).

## ⚠️ Disclaimer Penelitian (Status: Januari 2025)

Sistem **Waskita** dikembangkan sebagai instrumen penelitian akademik dalam bidang *Natural Language Processing* dan analisis konten media sosial Indonesia.

**Status Penelitian Saat Ini:**
- ✅ **Development Complete**: Semua fitur utama telah diimplementasi
- ✅ **Testing Phase**: Dalam tahap pengujian dan validasi model
- ✅ **Academic Research**: Dikembangkan untuk keperluan penelitian akademik
- ✅ **Open Source**: Tersedia untuk komunitas penelitian

**Ketentuan Penggunaan:**
- Dirancang khusus untuk keperluan penelitian dan pengembangan akademik
- Implementasi produksi memerlukan evaluasi dan validasi tambahan
- Hasil klasifikasi harus diinterpretasikan dalam konteks penelitian
- Pengguna bertanggung jawab memastikan kepatuhan regulasi dan etika penelitian

**Rekomendasi Penelitian:**
- Lakukan validasi silang dengan dataset independen
- Pertimbangkan bias dan limitasi model dalam interpretasi hasil
- Dokumentasikan metodologi untuk reproduktibilitas
- Patuhi prinsip etika penelitian dalam penggunaan data media sosial

**Pencapaian Teknis (Januari 2025):**
- ✅ Sistem autentikasi multi-layer dengan OTP
- ✅ Model machine learning dengan akurasi 85-92%
- ✅ Infrastructure Docker untuk deployment konsisten
- ✅ Documentation lengkap untuk reproduktibilitas
- ✅ Security audit dan best practices implementation

---

*Dikembangkan sebagai kontribusi penelitian akademik dalam bidang Natural Language Processing dan Machine Learning untuk analisis konten media sosial Indonesia*