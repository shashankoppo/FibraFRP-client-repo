# One-command new client deployment.
# Creates a fresh Odoo database and installs the default CE/custom profile.
#
# Usage:
#   .\deploy-new.ps1 -DbName client_name
#   .\deploy-new.ps1 -DbName client_name -Country IN

param(
    [Parameter(Mandatory=$true)]
    [string]$DbName,

    [string]$Country = "IN",
    [string]$AdminLogin = "admin",
    [string]$AdminLanguage = "en_US",
    [switch]$NoPull
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
$PostgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "odoo" }

function Stop-Deploy {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    exit 1
}

if ($DbName -notmatch "^[A-Za-z0-9_]+$") {
    Stop-Deploy "Database name can contain only letters, numbers, and underscores."
}
$Country = $Country.ToUpperInvariant()
if ($Country -notmatch "^[A-Z]{2}$") {
    Stop-Deploy "Country must be a two-letter ISO code, for example IN."
}

Write-Host ""
Write-Host "FibraFRP new client deploy" -ForegroundColor Cyan
Write-Host "Mode: create fresh database, install CE/custom modules, start app"

if (-not $NoPull) {
    Write-Host ""
    Write-Host "==> Pulling latest code" -ForegroundColor Cyan
    git pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Error "git pull failed. Fix the Git state, or rerun with -NoPull if the code is already correct."
    }
}

Write-Host ""
Write-Host "==> Checking addon folders and dependencies" -ForegroundColor Cyan
python deploy\audit_addons_ready.py
if ($LASTEXITCODE -ne 0) {
    Stop-Deploy "Addon audit failed. Fix the listed issue before creating a client database."
}

Write-Host ""
Write-Host "==> Starting PostgreSQL" -ForegroundColor Cyan
docker compose up -d db
if ($LASTEXITCODE -ne 0) {
    Stop-Deploy "Could not start PostgreSQL. Start Docker Desktop and run again."
}

$dbExists = docker compose exec -T db psql -U $PostgresUser -d postgres -Atc `
    "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$DbName');" 2>&1
if ($dbExists.Trim() -eq "t") {
    Stop-Deploy "Database '$DbName' already exists. Use .\deploy-prod.ps1 for existing client data."
}

Write-Host ""
Write-Host "A new admin password is required for this client database." -ForegroundColor Yellow
$securePassword = Read-Host "New admin password" -AsSecureString
$adminPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
)
if (-not $adminPassword) {
    Stop-Deploy "Admin password cannot be empty."
}

Write-Host ""
Write-Host "==> Building Odoo image" -ForegroundColor Cyan
docker compose build odoo
if ($LASTEXITCODE -ne 0) {
    Stop-Deploy "Odoo image build failed."
}

Write-Host ""
Write-Host "==> Resolving CE application profile" -ForegroundColor Cyan
$profile = docker compose run --rm -T --no-deps --entrypoint python3 odoo `
    /opt/odoo/deploy/ce_module_profile.py --applications --country $Country --format csv
if ($LASTEXITCODE -ne 0 -or -not $profile.Trim()) {
    Stop-Deploy "Could not resolve CE module profile."
}
$installModules = "$($profile.Trim()),elsx_client_restrictions,elsx_rebrand"

Write-Host ""
Write-Host "==> Creating database '$DbName'" -ForegroundColor Cyan
docker compose run --rm -T --no-deps `
    --entrypoint /bin/bash `
    -e TARGET_DB=$DbName `
    -e TARGET_COUNTRY=$Country `
    -e TARGET_ADMIN_LOGIN=$AdminLogin `
    -e TARGET_ADMIN_LANGUAGE=$AdminLanguage `
    -e TARGET_ADMIN_PASSWORD=$adminPassword `
    odoo -lc 'exec python3 /opt/odoo/odoo-bin db -c "${ODOO_RC}" --db_host="${DB_HOST}" --db_port="${DB_PORT}" --db_user="${DB_USER}" --db_password="${DB_PASSWORD}" init "${TARGET_DB}" --country "${TARGET_COUNTRY}" --language "${TARGET_ADMIN_LANGUAGE}" --username "${TARGET_ADMIN_LOGIN}" --password "${TARGET_ADMIN_PASSWORD}"'
if ($LASTEXITCODE -ne 0) {
    Stop-Deploy "Database creation failed."
}

Write-Host ""
Write-Host "==> Installing CE/custom modules" -ForegroundColor Cyan
docker compose run --rm -T --no-deps -e ELSX_NATIVE_ADMIN_CLEANUP=NO odoo `
    python3 /opt/odoo/odoo-bin `
    -c /etc/odoo/odoo.conf `
    -d $DbName `
    -i $installModules `
    --without-demo=True `
    --stop-after-init `
    --no-http
if ($LASTEXITCODE -ne 0) {
    Stop-Deploy "Module installation failed."
}

Write-Host ""
Write-Host "==> Starting app" -ForegroundColor Cyan
docker compose up -d odoo sidecar
docker compose ps

Write-Host ""
Write-Host "New client database is ready: $DbName" -ForegroundColor Green
Write-Host "Admin login: $AdminLogin"
Write-Host "Open: http://localhost:8069"
