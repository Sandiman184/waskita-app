# install-build.ps1
# Script instalasi & orkestrasi Docker untuk Waskita
# Otomatis jalankan lokal (HTTP-only) atau produksi (SSL) sesuai parameter

param(
    [switch]$Clean,
    [switch]$Production,
    [switch]$Help
)

if ($Help) {
    Write-Host "=== WASKITA INSTALL BUILD SCRIPT ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Script instalasi dan build aplikasi Waskita dengan Docker."
    Write-Host ""
    Write-Host "Parameter:"
    Write-Host "  -Clean       : Bersihkan data lama sebelum build (fresh install)"
    Write-Host "  -Production  : Build untuk production environment"
    Write-Host "  -Help        : Tampilkan bantuan ini"
    Write-Host ""
    Write-Host "Contoh penggunaan:"
    Write-Host "  .\install-build.ps1                # Build normal (development)"
    Write-Host "  .\install-build.ps1 -Clean         # Fresh install dengan data bersih"
    Write-Host "  .\install-build.ps1 -Production    # Build untuk production"
    Write-Host ""
    Write-Host "Setelah instalasi berhasil:"
    Write-Host "  - Akses: http://localhost:8080 (Development/Local)"
    Write-Host "  - Akses: https://waskita.site (Production)"
    Write-Host "  - Login: admin / admin123"
    Write-Host ""
    exit 0
}

Write-Host "=== WASKITA INSTALL BUILD ===" -ForegroundColor Cyan
Write-Host ""

# Check Docker installation
Write-Host "Memeriksa Docker installation..." -ForegroundColor Yellow

# Check if Docker is installed
docker --version > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker tidak terinstall!" -ForegroundColor Red
    Write-Host "Silakan install Docker Desktop terlebih dahulu." -ForegroundColor Yellow
    exit 1
}

# Check if Docker daemon is running
docker info > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker Desktop tidak berjalan!" -ForegroundColor Red
    Write-Host "Silakan jalankan Docker Desktop terlebih dahulu, lalu coba lagi." -ForegroundColor Yellow
    Write-Host "Tunggu hingga Docker Desktop selesai starting up." -ForegroundColor Gray
    exit 1
}

function Get-ComposeCommand {
    # Prioritaskan plugin baru: `docker compose`, fallback ke `docker-compose`
    docker compose version > $null 2>&1
    if ($LASTEXITCODE -eq 0) { return @{ exe = 'docker'; sub = 'compose'; label = 'docker compose' } }
    docker-compose --version > $null 2>&1
    if ($LASTEXITCODE -eq 0) { return @{ exe = 'docker-compose'; sub = ''; label = 'docker-compose' } }
    Write-Host "Error: Docker Compose tidak tersedia!" -ForegroundColor Red
    Write-Host "Silakan perbarui Docker Desktop agar mendukung 'docker compose'." -ForegroundColor Yellow
    exit 1
}

$compose = Get-ComposeCommand
Write-Host "Docker dan $($compose.label) tersedia dan berjalan" -ForegroundColor Green

# Clean installation if requested
if ($Clean) {
    Write-Host ""
    Write-Host "=== MEMBERSIHKAN INSTALASI LAMA ===" -ForegroundColor Yellow
    Write-Host "Menghentikan container yang berjalan..." -ForegroundColor Gray
    
    # Deteksi nama project (default: docker)
    $project = "waskita-app" 
    # Sesuaikan dengan nama folder atau COMPOSE_PROJECT_NAME
    
    $downArgs = @('-f', 'docker/docker-compose.yml')
    if (Test-Path 'docker/docker-compose.http-only.yml') { $downArgs += @('-f', 'docker/docker-compose.http-only.yml') }
    if (Test-Path 'docker/docker-compose.local.yml') { $downArgs += @('-f', 'docker/docker-compose.local.yml') }
    if (Test-Path 'docker/docker-compose.prod.yml') { $downArgs += @('-f', 'docker/docker-compose.prod.yml') }
    
    $downArgs += @('down', '--volumes', '--remove-orphans')
    
    # Jalankan perintah down
    Write-Host "Menjalankan: docker compose down..." -ForegroundColor Gray
    if ($compose.sub) {
        & $compose.exe $compose.sub @downArgs 2>$null
    } else {
        & $compose.exe @downArgs 2>$null
    }
    
    Write-Host "Menghapus volume database lama..." -ForegroundColor Gray
    # Coba hapus volume dengan berbagai kemungkinan nama (tergantung versi compose)
    docker volume rm docker_postgres_data docker_waskita_postgres_data waskita-app_postgres_data -f 2>$null
    
    Write-Host "Pembersihan selesai" -ForegroundColor Green
}

# Build and run containers
Write-Host ""
Write-Host "=== MEMULAI BUILD & DEPLOYMENT ===" -ForegroundColor Yellow

if ($Production) {
    Write-Host "Mode: PRODUCTION (SSL Enabled)" -ForegroundColor Cyan
    Write-Host "Pastikan sertifikat SSL sudah terpasang di host!" -ForegroundColor Red
    
    $composeFiles = @('-f', 'docker/docker-compose.yml', '-f', 'docker/docker-compose.prod.yml')
} else {
    Write-Host "Mode: DEVELOPMENT (HTTP Only)" -ForegroundColor Cyan
    # Gunakan docker-compose.local.yml yang sudah dikonfigurasi dengan benar untuk lokal
    $composeFiles = @('-f', 'docker/docker-compose.yml', '-f', 'docker/docker-compose.local.yml')
}

Write-Host "Building images (bisa memakan waktu lama untuk install dependencies)..." -ForegroundColor Gray
if ($compose.sub) {
    & $compose.exe $compose.sub @composeFiles build
} else {
    & $compose.exe @composeFiles build
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Build gagal!" -ForegroundColor Red
    exit 1
}

Write-Host "Starting containers..." -ForegroundColor Gray
if ($compose.sub) {
    & $compose.exe $compose.sub @composeFiles up -d
} else {
    & $compose.exe @composeFiles up -d
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Gagal menjalankan container!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== INSTALASI BERHASIL ===" -ForegroundColor Green
if ($Production) {
    Write-Host "Aplikasi berjalan di: https://waskita.site" -ForegroundColor Cyan
} else {
    Write-Host "Aplikasi berjalan di: http://localhost:8080" -ForegroundColor Cyan
}
Write-Host "Gunakan 'docker compose logs -f' untuk melihat log aplikasi." -ForegroundColor Gray
