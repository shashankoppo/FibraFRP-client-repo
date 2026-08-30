# One-command production update.
# Keeps existing client databases and Docker volumes. Does not run docker compose down.
#
# Usage:
#   .\deploy-prod.ps1
#   .\deploy-prod.ps1 -DbName qwerty
#   .\deploy-prod.ps1 -DbName qwerty -Install my_module

param(
    [string]$DbName = "",
    [string]$Install = "",
    [switch]$NoPull,
    [switch]$AuditOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host ""
Write-Host "FibraFRP production deploy" -ForegroundColor Cyan
Write-Host "Mode: keep client data, update code, build/start containers"
Write-Host "Module lock: update installed modules only unless -Install is used"

if ($AuditOnly) {
    Write-Host ""
    Write-Host "==> Checking addon folders and manifest dependencies" -ForegroundColor Cyan
    python deploy\audit_addons_ready.py
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Addon audit failed."
    }
    Write-Host ""
    Write-Host "Audit complete. No code pull, Docker build, or database changes were made." -ForegroundColor Green
    exit 0
}

if (-not $NoPull) {
    Write-Host ""
    Write-Host "==> Pulling latest code" -ForegroundColor Cyan
    git pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Error "git pull failed. Fix the Git state, or rerun with -NoPull if the code is already correct."
    }
}

if ($DbName) {
    $env:ODOO_AUTO_UPDATE_DB_NAME = $DbName
}
if ($Install) {
    $env:ODOO_AUTO_INSTALL_MODULES = $Install
    $env:ODOO_AUTO_UPDATE_MODULES = "all,$Install"
    $env:ODOO_AUTO_ALLOW_INSTALL = "YES"
}

Write-Host ""
Write-Host "==> Building and starting app" -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose up failed. Check Docker Desktop and the logs."
}

docker compose ps
Write-Host ""
Write-Host "Done. Odoo startup refreshes Apps and upgrades installed modules only." -ForegroundColor Green
