# Waskita — Analisis Konten Radikal

**Versi 2.0 (Desember 2025)**

## Deskripsi Aplikasi

**Waskita** adalah platform intelijen digital yang dikembangkan khusus untuk mendukung kegiatan akademik dan penelitian dalam memantau serta menganalisis penyebaran konten radikal di media sosial. Aplikasi ini mengintegrasikan kecerdasan buatan (Artificial Intelligence) dengan pendekatan *Hybrid Model*, menggabungkan algoritma *Deep Learning* (IndoBERT) dan *Machine Learning* konvensional untuk memberikan analisis yang akurat dan mendalam.

Aplikasi ini dirancang untuk membantu akademisi, peneliti, dan pengamat sosial dalam mengidentifikasi pola narasi ekstremisme secara dini. Melalui antarmuka yang profesional dan terorganisir, Waskita menyajikan visualisasi data yang komprehensif, memungkinkan pengguna untuk memahami tren penyebaran konten radikal dan merumuskan strategi mitigasi yang efektif.

### Fitur Utama
1.  **Analisis Multi-Model AI:** Menyediakan 7 algoritma klasifikasi (termasuk IndoBERT, SVM, dan Naive Bayes) untuk komparasi akurasi dan validasi hasil penelitian.
2.  **Scraping Multi-Platform:** Kemampuan pengumpulan data otomatis dari berbagai platform media sosial (Twitter, TikTok, Facebook) untuk mendapatkan korpus data yang relevan.
3.  **Preprocessing Teks Otomatis:** Modul pembersihan data yang canggih untuk menghilangkan noise (emoji, URL, simbol) dan menormalisasi teks agar siap dianalisis.
4.  **Dashboard Visualisasi:** Penyajian data statistik dan tren dalam format grafis yang mudah dipahami untuk keperluan pelaporan akademik.
5.  **Manajemen Dataset:** Fitur pengelolaan data yang fleksibel, mendukung impor/ekspor format standar penelitian (CSV/XLSX).

### Manfaat bagi Akademisi
*   **Efisiensi Penelitian:** Mengotomatisasi proses pengumpulan dan pelabelan data yang memakan waktu.
*   **Akurasi Ilmiah:** Menggunakan model bahasa terkini (IndoBERT) yang telah disesuaikan dengan konteks bahasa Indonesia.
*   **Reproduksibilitas:** Menyimpan riwayat klasifikasi dan konfigurasi model untuk memvalidasi hasil eksperimen.

### Teknologi yang Digunakan
*   **Backend:** Python Flask (Framework web yang ringan dan modular).
*   **Machine Learning:** PyTorch, Scikit-Learn, Gensim, Transformers.
*   **Database:** PostgreSQL (Penyimpanan data relasional yang handal).
*   **Frontend:** HTML5, CSS3, JavaScript (Antarmuka responsif).
*   **Deployment:** Docker (Kontainerisasi untuk konsistensi lingkungan).

---

## Konfigurasi Instalasi

### Persyaratan Sistem Minimum
*   **Sistem Operasi:** Windows 10/11, macOS, atau Linux (Ubuntu 20.04+).
*   **Prosesor:** Minimal Dual Core (Disarankan Quad Core untuk pelatihan model).
*   **Memori (RAM):** Minimal 8 GB (Disarankan 16 GB untuk performa optimal model IndoBERT).
*   **Penyimpanan:** Minimal 20 GB ruang kosong (SSD disarankan).
*   **Perangkat Lunak:** Docker Desktop (Wajib), Git.

### Langkah-langkah Instalasi

1.  **Unduh Paket Aplikasi**
    Clone repositori aplikasi dari sumber resmi menggunakan Git:
    ```bash
    git clone https://github.com/Sandiman184/waskita-app.git
    cd waskita-app
    ```

2.  **Ekstrak dan Persiapan**
    Pastikan struktur folder sudah sesuai. Jalankan skrip persiapan untuk mengatur konfigurasi awal:
    ```bash
    # Pada terminal (Windows/Linux/Mac)
    python src/backend/setup_postgresql.py
    ```

3.  **Jalankan Proses Instalasi (Docker)**
    Bangun dan jalankan aplikasi menggunakan Docker Compose untuk memastikan semua dependensi terinstal dengan benar:
    ```bash
    docker-compose -f docker/docker-compose.local.yml up --build
    ```

4.  **Verifikasi Instalasi**
    Buka peramban web dan akses alamat berikut untuk memastikan aplikasi berjalan:
    *   URL: `http://localhost:8080`
    *   Login Default: `admin` / (Password yang Anda set saat setup)

---

## Persyaratan Tambahan

### Library dan Dependensi
Aplikasi ini bergantung pada sejumlah pustaka Python utama yang akan diinstal otomatis oleh Docker, antara lain:
*   `flask`, `flask-sqlalchemy`, `flask-login` (Core Web)
*   `torch`, `transformers` (Deep Learning)
*   `scikit-learn`, `gensim`, `numpy`, `pandas` (Data Science)
*   `psycopg2-binary` (Database Driver)

### Konfigurasi Jaringan
*   Aplikasi menggunakan port `8080` (Web) dan `5432` (Database Internal) secara default.
*   Pastikan firewall tidak memblokir port tersebut pada lingkungan lokal.
*   Untuk fitur scraping, diperlukan koneksi internet yang stabil untuk mengakses API media sosial.

### Izin Sistem
*   **Akses File:** Aplikasi memerlukan izin baca/tulis pada folder `uploads/` untuk menyimpan dataset dan `models/` untuk memuat model AI.
*   **Docker:** User harus terdaftar dalam grup `docker` (Linux) atau menjalankan Docker Desktop sebagai Administrator (Windows).

---

## Gaya Antarmuka

Waskita mengusung filosofi desain yang **profesional dan akademis**, mengutamakan kejelasan data di atas elemen dekoratif.

*   **Nuansa Akademik:** Tata letak yang bersih dan terstruktur, mirip dengan jurnal atau dashboard analitik profesional.
*   **Palet Warna:** Menggunakan dominasi warna **Merah Maroon** dan **Abu-abu Gelap** yang merepresentasikan keseriusan dan urgensi topik (radikalisme), namun tetap nyaman di mata.
*   **Tipografi:** Menggunakan jenis huruf sans-serif yang modern dan mudah dibaca untuk memastikan keterbacaan teks analisis yang panjang.
*   **Navigasi Terorganisir:** Menu dikelompokkan secara logis (Dashboard, Data, Klasifikasi, Pengaturan) untuk memudahkan alur kerja penelitian.
*   **Kesederhanaan Visual:** Menghindari penggunaan ikon yang berlebihan atau elemen grafis yang mengganggu, sehingga fokus pengguna tetap pada substansi data dan hasil analisis.

---

**Hak Cipta © 2025 Tim Pengembang Waskita.**
Dikembangkan untuk Kepentingan Riset Akademik.
