# Changelog

All notable changes to this project will be documented in this file.

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