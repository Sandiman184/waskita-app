#!/bin/sh

# Script untuk inisialisasi admin user saat Docker container pertama kali dijalankan
# File: init_admin.sh

echo "=========================================="
echo "Waskita - Inisialisasi Admin User"
echo "=========================================="

# Gunakan Python untuk parsing DATABASE_URL yang lebih reliable
echo "Menggunakan Python untuk inisialisasi database..."
python /app/init_database.py

# Cek apakah inisialisasi berhasil
if [ $? -eq 0 ]; then
    echo "=========================================="
    echo "Inisialisasi selesai!"
    echo "=========================================="
    exit 0
else
    echo "Gagal inisialisasi database"
    exit 1
fi