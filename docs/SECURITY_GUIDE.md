# 🔒 PANDUAN KEAMANAN APLIKASI WASKITA

**Versi Dokumen:** 2.0  
**Tanggal Pembaruan:** 19 Desember 2025

Dokumen ini menjelaskan arsitektur keamanan, analisis risiko, dan prosedur penanganan insiden untuk aplikasi Waskita.

---

## 📋 DAFTAR ISI
1. [Arsitektur Keamanan](#1-arsitektur-keamanan)
2. [Analisis Risiko (Threat Modeling)](#2-analisis-risiko-threat-modeling)
3. [Mekanisme Proteksi Data](#3-mekanisme-proteksi-data)
4. [Audit & Monitoring](#4-audit--monitoring)
5. [Prosedur Penanganan Insiden](#5-prosedur-penanganan-insiden)
6. [Kebijakan Pembaruan](#6-kebijakan-pembaruan)

---

## 1. Arsitektur Keamanan

Sistem menerapkan pendekatan **Defense in Depth** dengan beberapa lapisan pertahanan.

```mermaid
graph TD
    Attacker[External Threat] -- DDOS/Exploit --> CloudFlare[Network Firewall / Cloudflare]
    CloudFlare --> Nginx[Nginx (Reverse Proxy & SSL)]
    
    subgraph "App Layer Security"
        Nginx -- Rate Limiting --> Flask[Flask App]
        Flask -- Auth & CSRF --> Logic[Business Logic]
        Logic -- Sanitization --> DB[(Database)]
    end
    
    subgraph "Data Security"
        DB -- Encryption at Rest --> Disk[Storage]
        Logic -- Hashing --> Passwords[User Credentials]
    end
```

### Komponen Kunci
1.  **Network Level:** Hanya port 443 (HTTPS) dan 22 (SSH - Restricted) yang dibuka.
2.  **Application Level:** Flask-Limiter untuk rate limiting, Flask-WTF untuk CSRF protection.
3.  **Data Level:** Enkripsi password dengan Bcrypt dan sanitasi input database.

---

## 2. Analisis Risiko (Threat Modeling)

Kami menggunakan model STRIDE untuk mengidentifikasi dan memitigasi ancaman.

| Kategori (STRIDE) | Ancaman Potensial | Mitigasi yang Diterapkan |
| :--- | :--- | :--- |
| **Spoofing** | Penyerang menyamar sebagai user lain. | Autentikasi ketat (Session + OTP), Secure Cookie, `SameSite=Lax`. |
| **Tampering** | Memanipulasi data klasifikasi/hasil. | Validasi input server-side, integritas database, CSRF token pada setiap form POST. |
| **Repudiation** | User menyangkal melakukan aksi berbahaya. | **Audit Logging** komprehensif mencatat setiap aksi kritis (Login, Upload, Delete) dengan IP & Timestamp. |
| **Information Disclosure** | Kebocoran data sensitif (error logs). | Debug Mode `False` di production. Error generik untuk user, log detail hanya di server. |
| **Denial of Service** | Membanjiri server dengan request scraping. | **Rate Limiting** (Flask-Limiter) pada endpoint API dan Login. Pembatasan ukuran file upload (Max 10GB). |
| **Elevation of Privilege** | User biasa mengakses fitur Admin. | Dekorator `@admin_required` pada setiap route sensitif. Pengecekan role di setiap fungsi backend. |

---

## 3. Mekanisme Proteksi Data

### A. Enkripsi Data (Data Encryption)
1.  **In Transit (Saat Transmisi):**
    *   Seluruh komunikasi Wajib menggunakan **TLS 1.2/1.3** (HTTPS).
    *   Sertifikat SSL dikelola otomatis oleh Certbot (Let's Encrypt).
    *   Header HSTS (*HTTP Strict Transport Security*) diaktifkan di Nginx.

2.  **At Rest (Saat Disimpan):**
    *   **Password:** Disimpan sebagai hash menggunakan **Bcrypt** (Work factor default).
    *   **Database:** Volume Docker database terlindungi oleh permission sistem operasi (hanya root/docker user).
    *   **Environment Variables:** Kredensial sensitif tidak di-hardcode, melainkan dibaca dari file `.env` yang tidak masuk version control.

### B. Autentikasi & Otorisasi
*   **Multi-Factor Authentication (MFA):** OTP via Email wajib untuk login pertama atau aktivitas mencurigakan.
*   **Session Management:**
    *   `HTTPOnly`: True (Mencegah XSS mengambil cookie).
    *   `Secure`: True (Hanya dikirim via HTTPS).
    *   `Lifetime`: Sesi kadaluarsa otomatis setelah 24 jam.

---

## 4. Audit & Monitoring

### Audit Logging
Setiap aksi yang mengubah state sistem dicatat di tabel `user_activities` dan log file.

**Contoh Log Audit:**
```json
{
  "timestamp": "2025-12-19T10:00:00Z",
  "user_id": 1,
  "action": "DELETE_DATASET",
  "resource_id": "dataset_123",
  "ip_address": "202.158.x.x",
  "status": "SUCCESS"
}
```

### Monitoring Server
*   **Resource Monitoring:** Penggunaan CPU/RAM container dipantau (via `docker stats`).
*   **Application Logs:** Log aplikasi Flask disimpan di `/var/log/waskita/` dengan rotasi harian.

---

## 5. Prosedur Penanganan Insiden

Jika terjadi indikasi pelanggaran keamanan (misal: Brute Force attack, kebocoran data):

1.  **Identifikasi & Konfirmasi:**
    *   Cek log Nginx dan Aplikasi untuk pola anomali.
    *   Verifikasi laporan dari user atau monitoring system.

2.  **Isolasi (Containment):**
    *   Blir IP penyerang di firewall/Nginx (`deny <ip>;`).
    *   Jika akun kompromi: `UPDATE users SET is_active=False WHERE id=<user_id>;`

3.  **Pemberantasan (Eradication):**
    *   Patch celah keamanan (update code/library).
    *   Reset password paksa untuk akun terdampak.
    *   Rotasi `SECRET_KEY` dan API Keys jika diduga bocor.

4.  **Pemulihan (Recovery):**
    *   Restore database dari backup terakhir yang bersih (jika data rusak).
    *   Restart layanan: `docker compose restart`.
    *   Monitoring intensif selama 24 jam pasca insiden.

5.  **Pelajaran (Post-Incident):**
    *   Buat laporan insiden (Root Cause Analysis).
    *   Update dokumen ini jika ada prosedur baru.

---

## 6. Kebijakan Pembaruan

1.  **OS & Docker:** Update keamanan sistem operasi host dilakukan setiap bulan (`apt update && apt upgrade`).
2.  **Dependencies:** Cek dependensi Python (`pip list --outdated`) setiap rilis minor baru.
3.  **Database:** Backup data sebelum melakukan upgrade versi mayor PostgreSQL.
