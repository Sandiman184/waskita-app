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
    Write-Host "  - Akses: http://localhost:5000"
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
    $downArgs = @('-f', 'docker/docker-compose.yml')
    if (Test-Path 'docker/docker-compose.local.yml') { $downArgs += @('-f', 'docker/docker-compose.local.yml') }
    $downArgs += @('down', '--volumes', '--remove-orphans')
    & $compose.exe $compose.sub @downArgs 2>$null
    
    Write-Host "Menghapus volume database lama..." -ForegroundColor Gray
    docker volume rm waskita_postgres_data -f 2>$null
    
    Write-Host "Pembersihan selesai" -ForegroundColor Green
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Default
    )
    if (Test-Path $Path) {
        $content = Get-Content $Path
        foreach ($line in $content) {
            if ($line -match "^$Key=(.*)$") { return $Matches[1] }
        }
    }
    return $Default
}

# Determine environment & compose files
$envFile = ".env"
$useDockerEnv = $false
$composeFiles = @("docker/docker-compose.yml")

if ($Production) {
    Write-Host "" 
    Write-Host "=== PRODUCTION BUILD (SSL ON) ===" -ForegroundColor Magenta
    $envFile = ".env.production"
    if (-not (Test-Path $envFile)) {
        Write-Host "Error: File $envFile tidak ditemukan!" -ForegroundColor Red
        Write-Host "Buat file .env.production atau salin dari .env.docker sesuai kebutuhan." -ForegroundColor Yellow
        exit 1
    }

    # Validasi sertifikat SSL untuk produksi
    if (-not (Test-Path "ssl/fullchain.pem") -or -not (Test-Path "ssl/privkey.pem")) {
        Write-Host "Error: Sertifikat SSL tidak ditemukan di folder 'ssl/'!" -ForegroundColor Red
        Write-Host "Pastikan 'ssl/fullchain.pem' dan 'ssl/privkey.pem' tersedia sebelum deploy produksi." -ForegroundColor Yellow
        Write-Host "Lihat panduan di 'ssl/README.md'." -ForegroundColor Gray
        exit 1
    }
    # Pastikan SSL aktif untuk produksi
    $env:ENABLE_SSL = "true"
} else {
    Write-Host "" 
    Write-Host "=== DEVELOPMENT BUILD (HTTP-ONLY) ===" -ForegroundColor Blue
    if (Test-Path ".env.docker") {
        Write-Host "Menggunakan .env.docker untuk environment Docker" -ForegroundColor Green
        $useDockerEnv = $true
        $envFile = ".env.docker"
    } else {
        Write-Host "Menggunakan .env untuk environment lokal" -ForegroundColor Yellow
    }
    # Tambahkan override agar Nginx berjalan HTTP-only
    if (Test-Path "docker/docker-compose.local.yml") {
        $composeFiles += "docker/docker-compose.local.yml"
    } else {
        Write-Host "Warning: 'docker/docker-compose.local.yml' tidak ditemukan. Nginx akan tetap mencoba HTTPS." -ForegroundColor Yellow
    }
    # Nonaktifkan SSL untuk lokal
    $env:ENABLE_SSL = "false"
}

# Check environment file
if (-not (Test-Path $envFile)) {
    Write-Host "Warning: File $envFile tidak ditemukan!" -ForegroundColor Yellow
    
    if (Test-Path ".env.example") {
        Write-Host "Membuat file .env dari .env.example..." -ForegroundColor Yellow
        Copy-Item ".env.example" $envFile
        Write-Host "File .env berhasil dibuat dari template" -ForegroundColor Green
        
        # Prompt user untuk mengisi kredensial database secara interaktif
        Write-Host ""
        Write-Host "=== KONFIGURASI DATABASE ===" -ForegroundColor Cyan
        Write-Host "Silakan masukkan kredensial database PostgreSQL:" -ForegroundColor Yellow
        
        $dbUser = Read-Host "Database Username (default: admin)"
        if ([string]::IsNullOrEmpty($dbUser)) { $dbUser = "admin" }
        
        $dbPass = Read-Host "Database Password (default: your_secure_password)" -AsSecureString
        $dbPassPlain = if ($dbPass) { [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPass)) } else { "your_secure_password" }
        
        $dbName = Read-Host "Database Name (default: db_waskita)"
        if ([string]::IsNullOrEmpty($dbName)) { $dbName = "db_waskita" }
        
        # Update file .env dengan kredensial yang dimasukkan
        $envContent = Get-Content $envFile -Raw
        $envContent = $envContent -replace "DATABASE_USER=.*", "DATABASE_USER=$dbUser"
        $envContent = $envContent -replace "DATABASE_PASSWORD=.*", "DATABASE_PASSWORD=$dbPassPlain"
        $envContent = $envContent -replace "DATABASE_NAME=.*", "DATABASE_NAME=$dbName"
        $envContent = $envContent -replace "POSTGRES_USER=.*", "POSTGRES_USER=$dbUser"
        $envContent = $envContent -replace "POSTGRES_PASSWORD=.*", "POSTGRES_PASSWORD=$dbPassPlain"
        $envContent = $envContent -replace "POSTGRES_DB=.*", "POSTGRES_DB=$dbName"
        
        Set-Content -Path $envFile -Value $envContent
        Write-Host "Kredensial database berhasil diupdate!" -ForegroundColor Green
        
    } else {
        Write-Host "Error: File .env.example tidak ditemukan!" -ForegroundColor Red
        Write-Host "Silakan buat file .env secara manual atau pastikan .env.example tersedia." -ForegroundColor Yellow
        exit 1
    }
} else {
    # Periksa apakah kredensial masih menggunakan nilai default
    # Hanya periksa untuk file .env (lokal), bukan .env.docker
    if ($envFile -eq ".env") {
        $envContent = Get-Content $envFile -Raw
        if ($envContent -match "your_secure_password" -or $envContent -match "admin_ws") {
            Write-Host ""
            Write-Host "=== PERINGATAN KEAMANAN ===" -ForegroundColor Red
            Write-Host "File .env masih menggunakan kredensial default!" -ForegroundColor Yellow
            Write-Host "Sangat disarankan untuk mengubah kredensial database." -ForegroundColor Yellow
            
            $changeCreds = Read-Host "Apakah Anda ingin mengubah kredensial sekarang? (y/N)"
            if ($changeCreds -eq "y" -or $changeCreds -eq "Y") {
                Write-Host ""
                Write-Host "=== UPDATE KREDENSIAL DATABASE ===" -ForegroundColor Cyan
                
                $dbUser = Read-Host "Database Username (default: admin)"
                if ([string]::IsNullOrEmpty($dbUser)) { $dbUser = "admin" }
                
                $dbPass = Read-Host "Database Password" -AsSecureString
                $dbPassPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPass))
                
                $dbName = Read-Host "Database Name (default: db_waskita)"
                if ([string]::IsNullOrEmpty($dbName)) { $dbName = "db_waskita" }
                
                # Update file .env dengan kredensial baru
                $envContent = $envContent -replace "DATABASE_USER=.*", "DATABASE_USER=$dbUser"
                $envContent = $envContent -replace "DATABASE_PASSWORD=.*", "DATABASE_PASSWORD=$dbPassPlain"
                $envContent = $envContent -replace "DATABASE_NAME=.*", "DATABASE_NAME=$dbName"
                $envContent = $envContent -replace "POSTGRES_USER=.*", "POSTGRES_USER=$dbUser"
                $envContent = $envContent -replace "POSTGRES_PASSWORD=.*", "POSTGRES_PASSWORD=$dbPassPlain"
                $envContent = $envContent -replace "POSTGRES_DB=.*", "POSTGRES_DB=$dbName"
                
                Set-Content -Path $envFile -Value $envContent
                Write-Host "Kredensial database berhasil diupdate!" -ForegroundColor Green
            }
        }
    }
}

# Build and start
Write-Host ""
Write-Host "=== MEMULAI BUILD & INSTALASI ===" -ForegroundColor Green
Write-Host "Building Docker images..." -ForegroundColor Yellow

$args = @()
foreach ($f in $composeFiles) { $args += @('-f', $f) }
if (Test-Path $envFile) { $args += @('--env-file', $envFile) }
$args += @('up', '--build', '-d')

& $compose.exe $compose.sub @args

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Error: Build gagal!" -ForegroundColor Red
    Write-Host "Periksa log error di atas untuk detail masalah." -ForegroundColor Yellow
    exit 1
}

# Wait for services to be ready
Write-Host ""
Write-Host "Menunggu services siap..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Check if services are running
Write-Host "Memeriksa status services..." -ForegroundColor Yellow
$psArgs = @('-f', 'docker/docker-compose.yml')
if (-not $Production -and (Test-Path 'docker/docker-compose.local.yml')) { $psArgs += @('-f', 'docker/docker-compose.local.yml') }
if (Test-Path $envFile) { $psArgs += @('--env-file', $envFile) }
$psArgs += @('ps', '--services', '--filter', 'status=running')

$containers = & $compose.exe $compose.sub @psArgs
if ($containers -match "web" -and $containers -match "db") {
    Write-Host "Services berjalan dengan baik" -ForegroundColor Green
} else {
    Write-Host "Warning: Beberapa services mungkin belum siap" -ForegroundColor Yellow
    Write-Host "Gunakan 'docker-compose logs' untuk memeriksa detail" -ForegroundColor Gray
}

# Success message
Write-Host ""
Write-Host "=== INSTALASI BERHASIL! ===" -ForegroundColor Green
Write-Host ""

$httpPort = if ($Production) { '80' } else { '8080' }
$httpsPort = Get-EnvValue -Path $envFile -Key 'NGINX_HTTPS_PORT' -Default '443'
$webPort = Get-EnvValue -Path $envFile -Key 'WEB_PORT' -Default '5000'

if ($Production) {
    Write-Host "🚀 PRODUCTION DEPLOYMENT SIAP (SSL aktif)" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "Akses aplikasi:" -ForegroundColor White
    Write-Host "- HTTPS (Nginx): https://yourdomain.com/" -ForegroundColor Cyan
    Write-Host "- HTTP  (redir): http://yourdomain.com/" -ForegroundColor Cyan
    Write-Host "- Port lokal terpublikasi: HTTP=$httpPort, HTTPS=$httpsPort" -ForegroundColor Gray
} else {
    Write-Host "🎉 DEVELOPMENT ENVIRONMENT SIAP (HTTP-only)" -ForegroundColor Blue
    Write-Host ""
    Write-Host "Akses aplikasi:" -ForegroundColor White
    Write-Host "- Nginx:   http://localhost:$httpPort/" -ForegroundColor Cyan
    Write-Host "- Web App: http://localhost:$webPort/" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Default Login:" -ForegroundColor White
Write-Host "- Username: admin" -ForegroundColor Green
Write-Host "- Password: admin123" -ForegroundColor Green
Write-Host ""
Write-Host "PENTING: Ubah password default setelah login pertama!" -ForegroundColor Yellow
Write-Host ""

# Useful commands
Write-Host "Commands berguna:" -ForegroundColor White
Write-Host "- Lihat logs:     $($compose.label) -f docker/docker-compose.yml logs -f" -ForegroundColor Gray
Write-Host "- Stop services:  $($compose.label) -f docker/docker-compose.yml down" -ForegroundColor Gray
Write-Host "- Restart:        $($compose.label) -f docker/docker-compose.yml restart" -ForegroundColor Gray
Write-Host "- Status:         $($compose.label) -f docker/docker-compose.yml ps" -ForegroundColor Gray
Write-Host ""

if ($Clean) {
    Write-Host "Fresh installation dengan data bersih berhasil!" -ForegroundColor Green
} else {
    Write-Host "Build berhasil! Aplikasi siap digunakan." -ForegroundColor Green
}