[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$VpsHost,
  [Parameter(Mandatory=$true)][string]$VpsUser,
  [int]$VpsPort=22,
  [string]$SshKeyPath,
  [string]$Domain='waskita.site',
  [string]$AdminEmail='beritamasuk2020@gmail.com',
  [string]$RepoUrl='https://github.com/Sandiman184/waskita-app.git',
  [string]$RemoteDir,
  [string]$EnvFilePath='./.env.production',
  [string]$GitUserEmail='sanapati184@gmail.com',
  [string]$GitUserName='Waskita Deploy'
)

if (-not $RemoteDir -or $RemoteDir.Trim() -eq '') { $RemoteDir = "/home/$VpsUser/waskita-app" }

function Test-Binary($name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $cmd) { throw "$name not found in PATH" }
}

Test-Binary 'plink'
Test-Binary 'pscp'

function SSH($cmd) {
  $args = @('-batch','-ssh','-P',$VpsPort)
  if ($SshKeyPath) { $args += @('-i',$SshKeyPath) }
  $args += @("$VpsUser@$VpsHost", $cmd)
  $p = Start-Process -FilePath 'plink' -ArgumentList $args -NoNewWindow -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "SSH command failed: $cmd" }
}

function SCP($local,$remote) {
  $args = @('-batch','-P',$VpsPort)
  if ($SshKeyPath) { $args += @('-i',$SshKeyPath) }
  $args += @($local, "$VpsUser@$VpsHost:$remote")
  $p = Start-Process -FilePath 'pscp' -ArgumentList $args -NoNewWindow -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "SCP failed: $local -> $remote" }
}

SSH "sudo apt-get update -y"
SSH "sudo apt-get install -y git docker.io docker-compose-plugin certbot"
SSH "sudo systemctl enable --now docker"
SSH "sudo ufw allow 22/tcp; sudo ufw allow 80/tcp; sudo ufw allow 443/tcp; sudo ufw --force enable"
SSH "mkdir -p '$RemoteDir'"
SSH "git config --global user.email '$GitUserEmail' && git config --global user.name '$GitUserName'"
SSH "if [ ! -d '$RemoteDir/.git' ]; then git clone '$RepoUrl' '$RemoteDir'; fi"
SSH "cd '$RemoteDir' && git fetch --all && git reset --hard origin/main"
SSH "git config --global --add safe.directory '$RemoteDir'"

if (-not (Test-Path -Path $EnvFilePath)) { throw "Env file not found: $EnvFilePath" }
SCP $EnvFilePath "$RemoteDir/.env.production"

SSH "sudo systemctl stop nginx || true"
SSH "sudo certbot certonly --standalone -d $Domain -d www.$Domain --non-interactive --agree-tos -m $AdminEmail"

SSH "if docker compose version >/dev/null 2>&1; then C='docker compose'; else C='docker-compose'; fi; cd '$RemoteDir' && sudo \$C -f docker/docker-compose.yml --env-file .env.production up -d"
SSH "if docker compose version >/dev/null 2>&1; then C='docker compose'; else C='docker-compose'; fi; cd '$RemoteDir' && sudo \$C -f docker/docker-compose.yml exec web curl -sf http://localhost:5000/api/health"
SSH "curl -skI https://$Domain | head -n 1"

Write-Host "Deployment complete" -ForegroundColor Green