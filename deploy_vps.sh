#!/bin/bash

# Script deployment untuk VPS Waskita
# Pastikan dijalankan dengan: sudo bash deploy_vps.sh

echo "=========================================="
echo "DEPLOYMENT WASKITA KE VPS"
echo "=========================================="

# Fungsi untuk logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Fungsi untuk error handling
error_exit() {
    log "ERROR: $1"
    exit 1
}

# Cek apakah script dijalankan sebagai root
if [ "$EUID" -ne 0 ]; then 
    echo "Script ini harus dijalankan dengan sudo"
    exit 1
fi

log "Memulai deployment Waskita ke VPS..."

# 1. Update system
log "Update system packages..."
apt-get update && apt-get upgrade -y || error_exit "Gagal update system"

# 2. Install Docker jika belum ada
if ! command -v docker &> /dev/null; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh || error_exit "Gagal install Docker"
    rm get-docker.sh
else
    log "Docker sudah terinstall"
fi

# 3. Install Docker Compose jika belum ada
if ! command -v docker-compose &> /dev/null; then
    log "Installing Docker Compose..."
    apt-get install -y docker-compose-plugin || error_exit "Gagal install Docker Compose"
else
    log "Docker Compose sudah terinstall"
fi

# 4. Start Docker service
log "Starting Docker service..."
systemctl enable docker
systemctl start docker || error_exit "Gagal start Docker service"

# 5. Cek direktori aplikasi
APP_DIR="/opt/waskita-app"
if [ ! -d "$APP_DIR" ]; then
    log "Creating application directory..."
    mkdir -p "$APP_DIR" || error_exit "Gagal buat direktori aplikasi"
fi

# 6. Copy file aplikasi (asumsi file sudah diupload)
log "Checking application files..."
if [ ! -f "$APP_DIR/docker-compose.yml" ]; then
    error_exit "File docker-compose.yml tidak ditemukan di $APP_DIR"
fi

if [ ! -f "$APP_DIR/.env.production" ]; then
    error_exit "File .env.production tidak ditemukan di $APP_DIR"
fi

# 7. Cek dan buat direktori models
MODELS_DIR="$APP_DIR/models"
if [ ! -d "$MODELS_DIR" ]; then
    log "Creating models directory..."
    mkdir -p "$MODELS_DIR/embeddings" "$MODELS_DIR/navesbayes" || error_exit "Gagal buat direktori models"
fi

# 8. Pastikan model files ada
log "Checking model files..."
MODEL_FILES=(
    "$MODELS_DIR/embeddings/wiki_word2vec_csv_updated.model"
    "$MODELS_DIR/navesbayes/naive_bayes_model1.pkl"
    "$MODELS_DIR/navesbayes/naive_bayes_model2.pkl"
    "$MODELS_DIR/navesbayes/naive_bayes_model3.pkl"
)

for file in "${MODEL_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        error_exit "Model file tidak ditemukan: $file"
    fi
    log "✓ Found: $(basename "$file")"
done

# 9. Build dan start containers
log "Building and starting Docker containers..."
cd "$APP_DIR" || error_exit "Gagal pindah ke direktori aplikasi"

docker-compose down || log "Warning: Gagal stop containers sebelumnya"

docker-compose build --no-cache || error_exit "Gagal build containers"

docker-compose up -d || error_exit "Gagal start containers"

# 10. Tunggu sampai aplikasi ready
log "Waiting for application to be ready..."
sleep 30

# 11. Test aplikasi
log "Testing application..."
if curl -f http://localhost:5000/health > /dev/null 2>&1; then
    log "✓ Aplikasi berjalan dengan baik"
else
    log "⚠ Aplikasi mungkin butuh waktu lebih lama untuk start"
fi

# 12. Cek container status
log "Checking container status..."
docker-compose ps

# 13. Setup firewall (jika diperlukan)
log "Setting up firewall..."
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp
ufw --force enable || log "Warning: Gagal enable firewall"

# 14. Setup log rotation
log "Setting up log rotation..."
cat > /etc/logrotate.d/waskita << EOF
/opt/waskita-app/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF

log "=========================================="
log "DEPLOYMENT SELESAI!"
log "=========================================="
log "Aplikasi dapat diakses di:"
log "- HTTP: http://$(hostname -I | awk '{print $1}'):80"
log "- HTTPS: https://$(hostname -I | awk '{print $1}'):443"
log ""
log "Untuk monitor: docker-compose logs -f"
log "Untuk stop: docker-compose down"
log "Untuk restart: docker-compose restart"

# 15. Jalankan validasi
log "Running validation..."
if [ -f "vps_validation_fix.py" ]; then
    python3 vps_validation_fix.py || log "Warning: Validasi menemukan issues"
fi

echo ""
echo "✅ DEPLOYMENT SUKSES!"
echo "Periksa file vps_validation.log untuk detail validasi"