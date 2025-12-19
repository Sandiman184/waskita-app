# 🔒 PANDUAN KEAMANAN APLIKASI WASKITA

Dokumen ini menjelaskan arsitektur keamanan, fitur proteksi, dan praktik terbaik yang diterapkan dalam aplikasi Waskita.

---

## 📋 DAFTAR ISI
1. [Ringkasan Fitur Keamanan](#1-ringkasan-fitur-keamanan)
2. [Sistem Autentikasi & Otorisasi](#2-sistem-autentikasi--otorisasi)
3. [Manajemen Sesi & Proteksi Data](#3-manajemen-sesi--proteksi-data)
4. [Keamanan Deployment (Docker & VPS)](#4-keamanan-deployment)
5. [Audit & Logging](#5-audit--logging)
6. [Checklist Keamanan untuk Admin](#6-checklist-keamanan-untuk-admin)

---

## 1. Ringkasan Fitur Keamanan

Aplikasi Waskita dirancang dengan pendekatan *Security by Design*, mencakup:

| Fitur | Deskripsi | Status |
| :--- | :--- | :--- |
| **Password Hashing** | Menggunakan algoritma **Bcrypt** (via Werkzeug) untuk menyimpan password. | ✅ Aktif |
| **CSRF Protection** | Perlindungan terhadap *Cross-Site Request Forgery* pada semua form (Flask-WTF). | ✅ Aktif |
| **Secure Session** | Cookie sesi dilindungi dengan flag `HttpOnly`, `Secure` (di production), dan `SameSite=Lax`. | ✅ Aktif |
| **Rate Limiting** | Membatasi jumlah request untuk mencegah Brute Force (Flask-Limiter). | ✅ Aktif |
| **Input Validation** | Validasi ketat pada input form dan upload file (MIME type check). | ✅ Aktif |
| **SQL Injection** | Menggunakan ORM (SQLAlchemy) yang secara otomatis menolak injeksi SQL. | ✅ Aktif |
| **XSS Protection** | Auto-escaping pada template Jinja2 untuk mencegah script berbahaya. | ✅ Aktif |

---

## 2. Sistem Autentikasi & Otorisasi

### 2.1 Multi-Level User Roles
Sistem membedakan hak akses berdasarkan peran:
*   **Admin:** Akses penuh (CRUD User, Dataset, Klasifikasi, Reset Password).
*   **User Biasa:** Akses terbatas pada data pribadi dan fitur klasifikasi.

### 2.2 Verifikasi OTP (One-Time Password)
Untuk meningkatkan keamanan saat registrasi atau login pertama:
*   **Mekanisme:** Mengirim kode 6 digit ke email pengguna.
*   **Provider:** Menggunakan SMTP Gmail dengan App Password.
*   **Keamanan:** Kode berlaku 5 menit, maksimal 3x percobaan salah sebelum akun dikunci sementara.

### 2.3 Manajemen Password
*   **Hashing:** Password tidak pernah disimpan dalam bentuk teks asli (plain text).
*   **Reset Password:** Fitur reset password mengirim token aman ke email pengguna.

---

## 3. Manajemen Sesi & Proteksi Data

### 3.1 Konfigurasi Cookie
Dalam file `.env` (atau `.env.production`), konfigurasi sesi diatur sebagai berikut:
```ini
SESSION_COOKIE_HTTPONLY=True  # Mencegah akses cookie via JavaScript
SESSION_COOKIE_SECURE=True    # Hanya kirim cookie via HTTPS (Production)
SESSION_COOKIE_SAMESITE=Lax   # Mencegah CSRF lintas domain
```

### 3.2 Proteksi Upload File
*   **Validasi Ekstensi:** Hanya mengizinkan `.csv`, `.xlsx`, `.xls`.
*   **Validasi Konten:** Memeriksa header file untuk memastikan tipe MIME yang benar.
*   **Sanitasi Nama File:** Menggunakan `secure_filename()` untuk mencegah path traversal.

### 3.3 Penanganan Data Sensitif
*   **Environment Variables:** Kredensial (DB Password, API Keys, Secret Keys) **WAJIB** disimpan di file `.env` dan **TIDAK BOLEH** di-commit ke Git.
*   **Placeholder:** Gunakan `.env.example` dengan nilai placeholder untuk referensi developer lain.

---

## 4. Keamanan Deployment

### 4.1 Docker Security
*   **Non-Root User:** Container aplikasi berjalan sebagai user biasa (`waskita`), bukan `root`.
*   **Minimal Base Image:** Menggunakan `python:3.11-slim` untuk mengurangi *attack surface*.
*   **Network Isolation:** Database tidak diekspos ke publik, hanya bisa diakses oleh container aplikasi dalam network internal Docker.

### 4.2 VPS & Nginx Security (Production)
*   **SSL/HTTPS:** Wajib menggunakan sertifikat SSL (Let's Encrypt) yang diatur otomatis oleh script deployment.
*   **Reverse Proxy:** Nginx bertindak sebagai gerbang depan, menyembunyikan server aplikasi (Gunicorn).
*   **Firewall:** Hanya port 80 (HTTP), 443 (HTTPS), dan 22 (SSH) yang dibuka.

---

## 5. Audit & Logging

### 5.1 Audit Trail
Sistem mencatat aktivitas penting pengguna ke database/log:
*   Login/Logout sukses & gagal.
*   Upload & penghapusan dataset.
*   Perubahan konfigurasi oleh Admin.

### 5.2 Error Logging
*   Di mode produksi, error detail **tidak ditampilkan** ke pengguna (halaman 500 generik).
*   Log error lengkap disimpan di server untuk analisis developer.

---

## 6. Checklist Keamanan untuk Admin

Sebelum aplikasi dibuka ke publik, Admin wajib memastikan:
- [ ] File `.env` produksi tidak boleh ada di repository Git.
- [ ] `SECRET_KEY`, `JWT_SECRET_KEY`, dan `WTF_CSRF_SECRET_KEY` menggunakan string acak yang panjang.
- [ ] Password database (`POSTGRES_PASSWORD`) kuat dan unik.
- [ ] Debug Mode (`FLASK_DEBUG`) bernilai `False` di production.
- [ ] SSL/HTTPS aktif dan sertifikat valid.
- [ ] Port database (5432) tidak terekspos ke internet publik (hanya via Docker network).
- [ ] Akun Admin default sudah diganti passwordnya.
