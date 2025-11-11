# Panduan Deployment Waskita di VPS

## 📋 Persiapan VPS

### 1. Requirements Sistem
- Ubuntu 20.04/22.04 LTS
- Minimal 4GB RAM (8GB recommended untuk model ML)
- Minimal 50GB storage
- Docker & Docker Compose

### 2. Setup Awal di VPS

```bash
# Login ke VPS Anda
ssh user@your-vps-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y curl wget git python3 python3-pip

# Buat direktori aplikasi
sudo mkdir -p /opt/waskita-app
sudo chown $USER:$USER /opt/waskita-app
```

## 🚀 Deployment Otomatis

### Metode 1: Menggunakan Script Deployment

1. **Upload file ke VPS**:
```bash
# Dari local machine, upload file ke VPS
scp -r .env.production docker-compose.yml vps_validation_fix.py user@your-vps-ip:/opt/waskita-app/

# Upload model files (pastikan sudah ada)
scp -r models/ user@your-vps-ip:/opt/waskita-app/
```

2. **Jalankan deployment**:
```bash
# Login ke VPS
ssh user@your-vps-ip

# Jadikan script executable
chmod +x /opt/waskita-app/deploy_vps.sh

# Jalankan deployment
sudo bash /opt/waskita-app/deploy_vps.sh
```

### Metode 2: Manual Deployment

1. **Install Docker**:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

2. **Install Docker Compose**:
```bash
sudo apt install -y docker-compose-plugin
```

3. **Setup aplikasi**:
```bash
cd /opt/waskita-app

# Pastikan file sudah diupload:
# - docker-compose.yml
# - .env.production  
# - models/ directory dengan semua file model

# Build dan start
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

## 🔧 Validasi Setup

Setelah deployment, jalankan validasi:

```bash
cd /opt/waskita-app
python3 vps_validation_fix.py
```

Script akan memeriksa:
- ✅ Status Docker service
- ✅ Container yang berjalan  
- ✅ Direktori dan file model
- ✅ Environment variables
- ✅ Model loading functionality

## 📊 Monitoring

### Cek status container:
```bash
docker-compose ps
docker-compose logs -f
```

### Cek resource usage:
```bash
docker stats
```

### Restart services:
```bash
docker-compose restart
```

## 🛠 Troubleshooting

### Issue 1: Model tidak loading
**Gejala**: Error "Model not found" atau "DISABLE_MODEL_LOADING=True"

**Solusi**:
```bash
# Pastikan environment variable sudah benar
echo $DISABLE_MODEL_LOADING  # Harus "False"

# Pastikan path model benar
ls -la /opt/waskita-app/models/embeddings/
ls -la /opt/waskita-app/models/navesbayes/
```

### Issue 2: Port sudah digunakan
**Solusi**:
```bash
# Cek port yang digunakan
sudo netstat -tuln | grep :80
sudo netstat -tuln | grep :443

# Jika port digunakan, stop service yang conflicting
sudo systemctl stop nginx  # atau service lain
```

### Issue 3: Docker permission denied
**Solusi**:
```bash
# Tambahkan user ke group docker
sudo usermod -aG docker $USER

# Logout dan login kembali
logout
ssh user@your-vps-ip
```

### Issue 4: Out of memory
**Solusi**:
```bash
# Kurangi resource allocation di docker-compose.yml
# atau upgrade VPS RAM
```

## 🔐 Security Hardening

### 1. Firewall setup:
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp  
sudo ufw allow 22/tcp
sudo ufw enable
```

### 2. SSL Certificate (Let's Encrypt):
```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Request certificate
sudo certbot --nginx -d waskita.site
```

### 3. Regular updates:
```bash
# Setup automatic security updates
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## 📈 Performance Optimization

### 1. Database optimization:
```sql
-- Jalankan di PostgreSQL
VACUUM ANALYZE;
CREATE INDEX IF NOT EXISTS idx_dataset_created ON dataset(created_at);
```

### 2. Gunicorn workers tuning:
```yaml
# Di docker-compose.yml, adjust berdasarkan RAM:
# - 2GB RAM: -w 2 --threads 2  
# - 4GB RAM: -w 4 --threads 4
# - 8GB RAM: -w 6 --threads 6
```

### 3. Caching setup:
```bash
# Pastikan Redis berjalan
redis-cli ping
```

## 🔄 Backup & Recovery

### 1. Backup database:
```bash
# Backup script
pg_dump -U admin -h localhost -d db_waskita > backup_$(date +%Y%m%d).sql
```

### 2. Backup uploads:
```bash
tar -czf uploads_backup_$(date +%Y%m%d).tar.gz /opt/waskita-app/uploads/
```

### 3. Auto-backup setup:
```bash
# Tambahkan ke crontab
0 2 * * * /opt/waskita-app/scripts/backup.sh
```

## 📞 Support

Jika mengalami issues:

1. **Cek logs**: `docker-compose logs -f`
2. **Validasi**: `python3 vps_validation_fix.py`
3. **Restart**: `docker-compose restart`

## ✅ Checklist Final

- [ ] Docker installed
- [ ] Docker Compose installed  
- [ ] File aplikasi diupload ke /opt/waskita-app/
- [ ] Model files ada di models/ directory
- [ ] .env.production dikonfigurasi dengan benar
- [ ] Container berjalan: `docker-compose ps`
- [ ] Aplikasi accessible: `curl http://localhost:5000`
- [ ] Validasi passed: `python3 vps_validation_fix.py`

---

**Catatan**: Pastikan semua file model sudah diupload ke VPS sebelum deployment. File model yang diperlukan:
- `models/embeddings/wiki_word2vec_csv_updated.model`
- `models/navesbayes/naive_bayes_model1.pkl` 
- `models/navesbayes/naive_bayes_model2.pkl`
- `models/navesbayes/naive_bayes_model3.pkl`