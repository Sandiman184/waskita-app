# Changelog

All notable changes to this project will be documented in this file.

## [1.4.0] - 2025-12-10

### ✨ Features
- **Admin Templates**: Halaman `classification_settings`, `database`, dan `retrain` ditambahkan
- **ML Utilities**: `IndoBERTClassifier` dan utilitas pelatihan model ditambahkan
- **Training History**: Migrasi Alembic untuk tabel riwayat pelatihan dan metrik

### 📚 Documentation
- Update dokumentasi terkait setup dan referensi komponen baru

### 🧹 Maintenance
- **Version**: Naikkan versi aplikasi menjadi `1.4.0`

## [1.3.1] - 2025-12-10

### 🚀 Deployment & Production
- **Nginx (Dev)**: Tambah `docker/Dockerfile.nginx.dev` untuk mode HTTP-only development
- **Docker**: Perbaikan konfigurasi Docker dan Nginx untuk alur dev/production

### 📚 Documentation
- **README**: Tambahkan referensi konfigurasi SSL, penggunaan `install-build.ps1`, dan troubleshooting
- **Setup Docs**: Penjelasan lebih jelas untuk SSL dan parameter skrip deployment

### 🧹 Maintenance
- **Version**: Bump versi aplikasi menjadi `1.3.1`

## [1.3.0] - 2025-01-15

### 🚀 Deployment & Production
- **VPS Deployment**: Full production-ready deployment configuration
- **Nginx Configuration**: Immutable entrypoint and reverse proxy setup
- **API Endpoints**: Added `/api/models-status` for production monitoring
- **Security Hardening**: Enhanced production security configurations

### 📊 Data Processing
- **CSV Upload**: Improved format detection and fallback mechanisms
- **Data Validation**: Enhanced error handling for malformed CSV files
- **Performance**: Optimized data processing pipelines

### 🔒 Security
- **CSRF Protection**: Fixed token missing issue on first login
- **Session Management**: Improved session configuration and security
- **Production Checklist**: Comprehensive security audit and hardening

### 📚 Documentation
- **Deployment Guides**: Complete VPS deployment documentation
- **Security Guidelines**: OWASP compliance and production security
- **Setup Recommendations**: Structured setup applications and best practices

---

## [1.2.0] - 2025-01-10

### 🛠️ Infrastructure
- **Docker Optimization**: Enhanced Docker configurations for production
- **Nginx Setup**: Complete reverse proxy configuration
- **Deployment Scripts**: PowerShell deployment scripts for VPS

### 📝 Documentation
- **Workflow Diagrams**: End-to-end sequence and flowcharts
- **Security References**: Comprehensive logging and security guidelines
- **Setup Structure**: Restructured setup applications per outline

### 🐛 Bug Fixes
- **CSV Handling**: Fixed format detection issues
- **Upload Reliability**: Improved fallback mechanisms for various CSV formats
- **Documentation**: Updated setup and security guides

---

## [1.1.0] - 2024-12-19

### 🔧 Fixed
- **CRITICAL**: Fixed placeholder values in `setup_postgresql.py` that caused incorrect admin user creation
- **Database**: Updated database configuration to use consistent naming (`admin_ws` instead of `waskita_user`)
- **Authentication**: Fixed password hashing issues that prevented login

### ✨ Added
- **Setup Scripts**: Added comprehensive setup and debugging utilities:
  - `debug_users.py` - Verify user creation and passwords
  - `fix_passwords.py` - Fix existing user passwords
  - `cleanup_old_users.py` - Remove users created with placeholder values
- **Documentation**: 
  - Updated `README.md` with complete setup guide
  - Added `SETUP_CORRECTED.md` with detailed troubleshooting
  - Added `CHANGELOG.md` for tracking changes

### 🗑️ Removed
- **Deprecated**: Removed `create_admin.py` (functionality moved to `setup_postgresql.py`)

### 📝 Changed
- **Environment**: Updated `.env.example` with correct default values and clear instructions
- **Setup Process**: Simplified setup to single command: `python setup_postgresql.py`
- **Documentation**: Comprehensive rewrite of setup documentation

### 🔒 Security
- **Credentials**: Fixed default admin credentials (no more placeholder values)
- **Environment**: Ensured `.env` files are properly ignored in git

### 💡 Default Credentials (After Setup)
```
Username: admin
Password: admin123
Email: admin@waskita.com
```

### 🚀 Quick Setup
```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit .env with your values (minimal: DATABASE_PASSWORD, SECRET_KEY)

# 3. Run setup
python setup_postgresql.py

# 4. Start application
python app.py
```

---

## [1.0.0] - Initial Release

### ✨ Features
- User authentication and authorization system
- Social media data scraping (Twitter, Facebook, Instagram, TikTok)
- Machine Learning classification (Naive Bayes with Word2Vec)
- Data cleaning and preprocessing
- Admin panel for user management
- Soft UI Dashboard with dark/light themes
- Email notifications and OTP system
- PostgreSQL database integration
- Docker support
