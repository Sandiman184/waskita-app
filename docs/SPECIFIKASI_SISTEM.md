# 📘 SPESIFIKASI SISTEM WASKITA

Dokumen ini merinci spesifikasi teknis, fungsional, dan kebutuhan sistem untuk aplikasi Waskita (Analisis Konten Radikal).

---

## 1. Arsitektur Sistem

*   **Tipe Aplikasi:** Web Application (Monolith dengan Service-Oriented Components)
*   **Backend Framework:** Python Flask 3.x
*   **Frontend Framework:** HTML5, CSS3 (Soft UI Dashboard), JavaScript (Vanilla + Plugins)
*   **Database:** PostgreSQL 14+
*   **Machine Learning:** Scikit-Learn (Naive Bayes), IndoBERT (Transformers), Word2Vec (Gensim)
*   **Deployment:** Docker Container (Nginx Reverse Proxy + Gunicorn)

---

## 2. Spesifikasi Kebutuhan Perangkat (Hardware Requirements)

### Server (Production / VPS)
*   **CPU:** Minimal 2 vCPU (Disarankan 4 vCPU untuk training model/fine-tuning).
*   **RAM:** Minimal 4 GB (Disarankan 8 GB jika menggunakan model IndoBERT aktif).
*   **Storage:** Minimal 20 GB SSD (untuk dataset, model, dan log).
*   **OS:** Ubuntu 20.04 / 22.04 LTS atau Debian 11+.

### Client (Pengguna)
*   **Perangkat:** Laptop, PC, Tablet, atau Smartphone.
*   **Browser:** Google Chrome (Terbaru), Firefox, Safari, Edge.
*   **Koneksi Internet:** Diperlukan untuk akses web dan fitur scraping.

---

## 3. Spesifikasi Kebutuhan Perangkat Lunak (Software Stack)

| Komponen | Teknologi / Library | Keterangan |
| :--- | :--- | :--- |
| **Bahasa Pemrograman** | Python 3.10+ | Core logic backend & ML. |
| **Web Server** | Nginx | Reverse proxy, SSL termination, static file serving. |
| **App Server** | Gunicorn | WSGI HTTP Server untuk menjalankan Flask di production. |
| **Database** | PostgreSQL | Penyimpanan data relasional (User, Dataset, Hasil). |
| **ORM** | SQLAlchemy | Abstraksi database dan manajemen model. |
| **ML Libraries** | Scikit-learn, Transformers, PyTorch | Training dan inferensi klasifikasi teks. |
| **NLP Libraries** | Sastrawi, NLTK | Preprocessing teks Bahasa Indonesia (Stopword, Stemming). |
| **Task Queue** | Celery + Redis (Opsional) | Untuk background task berat (Scraping/Training). |
| **Frontend UI** | Soft UI Dashboard (Bootstrap 5) | Desain antarmuka modern, responsif, dan support Dark Mode. |

---

## 4. Spesifikasi Fungsional

### A. Manajemen Pengguna & Keamanan
1.  **Login & Registrasi:** Support hashing password (Bcrypt) dan verifikasi email (OTP).
2.  **Role Management:** Pemisahan akses antara **Admin** (Full Access) dan **User** (Limited).
3.  **Session Security:** Timeout otomatis, proteksi CSRF, dan Secure Cookies.

### B. Pengolahan Data
1.  **Upload Dataset:** Support format `.csv` dan `.xlsx` dengan validasi struktur kolom.
2.  **Scraping Media Sosial:** Integrasi API (via Apify) untuk Twitter, TikTok, Facebook.
3.  **Preprocessing:** Pembersihan data otomatis (hapus emoji, url, normalisasi kata).

### C. Klasifikasi & AI
1.  **Model:** Naive Bayes Classifier dengan ekstraksi fitur Word2Vec/TF-IDF.
2.  **Output:** Label "Radikal" / "Non-Radikal" beserta skor probabilitas.
3.  **Fine-Tuning:** Fitur untuk melatih ulang model dengan dataset baru (Admin only).

### D. Antarmuka Pengguna (UI/UX)
1.  **Responsive Design:** Tampilan menyesuaikan layar Desktop, Tablet, dan Mobile.
2.  **Dark Mode:** Mode gelap sebagai default (sesuai User Rules), opsi switch ke Light Mode.
3.  **Dashboard Interaktif:** Grafik statistik dataset dan hasil klasifikasi.

---

## 5. Spesifikasi Lingkungan (Environment)

Aplikasi menggunakan konfigurasi berbasis **12-Factor App** melalui file `.env`:

*   `FLASK_ENV`: development / production
*   `DATABASE_URL`: Connection string PostgreSQL
*   `SECRET_KEY`: Kunci enkripsi sesi
*   `MAIL_*`: Konfigurasi SMTP Server
*   `APIFY_*`: Token dan Actor ID untuk scraping

---

## 6. Skenario Deployment

*   **Lokal (Dev):** Flask Development Server (`flask run`) atau Docker Compose Local.
*   **Produksi:** VPS dengan Docker Compose (Nginx -> Gunicorn -> Flask), SSL via Certbot.
