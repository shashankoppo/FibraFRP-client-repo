# Safely uninstall elsx_saas from one Odoo database on Docker Desktop.
# This script never deletes Docker volumes, drops databases, or removes filestore data.

param(
    [Parameter(Mandatory=$true)]
    [string]$DbName,

    [switch]$Confirm,

    [string]$BackupDir = "secure_backups",
    [string]$DbUser = "odoo",
    [string]$RepairModules = "elsx_client_restrictions,elsx_ai_ocr"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not $Confirm) {
    Write-Error "ERROR: rerun with -Confirm to uninstall elsx_saas from '$DbName'."
}

if (-not $env:BACKUP_PASSPHRASE) {
    Write-Error "ERROR: set `$env:BACKUP_PASSPHRASE before running this script. Refusing to continue without a backup guard."
}

Write-Host "==> Safe SaaS uninstall for database: $DbName" -ForegroundColor Cyan

Write-Host "==> Ensuring PostgreSQL is running" -ForegroundColor Cyan
docker compose up -d db | Out-Null

$dbExists = docker compose exec -T db psql -U $DbUser -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$DbName';" 2>&1
if ($dbExists.Trim() -ne "1") {
    Write-Error "ERROR: Database '$DbName' does not exist. Aborting."
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$dumpFile = Join-Path $BackupDir "${DbName}_${timestamp}_pre_saas_uninstall.pg_dump"

Write-Host "==> Backing up $DbName to $dumpFile" -ForegroundColor Cyan
docker compose exec -T db pg_dump -U $DbUser -d $DbName --format=custom | Set-Content -Path $dumpFile -AsByteStream
if (-not (Test-Path $dumpFile) -or (Get-Item $dumpFile).Length -eq 0) {
    Write-Error "ERROR: Backup failed or produced an empty file. Refusing to uninstall."
}

Write-Host "==> Building Odoo image" -ForegroundColor Cyan
docker compose build odoo
if ($LASTEXITCODE -ne 0) { Write-Error "ERROR: docker compose build failed." }

Write-Host "==> Stopping Odoo and optional sidecars" -ForegroundColor Cyan
docker compose stop sidecar 2>$null | Out-Null
docker compose stop odoo 2>$null | Out-Null

Write-Host "==> Applying repair modules: $RepairModules" -ForegroundColor Cyan
docker compose run --rm -T --no-deps odoo `
    python3 /opt/odoo/odoo-bin `
        -c /etc/odoo/odoo.conf `
        -d $DbName `
        -u $RepairModules `
        --stop-after-init
if ($LASTEXITCODE -ne 0) { Write-Error "ERROR: repair module upgrade failed. Database is intact." }

$python = @"
module = env['ir.module.module'].search([('name', '=', 'elsx_saas')], limit=1)
if not module:
    print('elsx_saas module record not found; nothing to uninstall.')
elif module.state == 'uninstalled':
    print('elsx_saas is already uninstalled.')
else:
    env['ir.config_parameter'].sudo().set_param('elsx_saas.enabled', '0')
    module.with_context(elsx_allow_protected_module_uninstall=True).button_immediate_uninstall()
    env.cr.commit()
    refreshed = env['ir.module.module'].search([('name', '=', 'elsx_saas')], limit=1)
    print('elsx_saas state=' + (refreshed.state or '<missing>'))
"@

Write-Host "==> Uninstalling elsx_saas" -ForegroundColor Cyan
$python | docker compose run --rm -T --no-deps odoo `
    python3 /opt/odoo/odoo-bin shell `
        -c /etc/odoo/odoo.conf `
        -d $DbName `
        --no-http
if ($LASTEXITCODE -ne 0) { Write-Error "ERROR: elsx_saas uninstall failed. Backup is available at $dumpFile." }

Write-Host "==> Module states" -ForegroundColor Cyan
docker compose exec -T db psql -U $DbUser -d $DbName -c "SELECT name, state, latest_version FROM ir_module_module WHERE name IN ('elsx_saas','elsx_client_restrictions','elsx_ai_ocr') ORDER BY name;"

Write-Host "==> Starting Odoo and WhatsApp sidecar" -ForegroundColor Cyan
docker compose up -d odoo sidecar

Write-Host "==> SaaS uninstall complete. Backup: $dumpFile" -ForegroundColor Green
Write-Host "    Check logs: docker logs --tail 250 odoo_app"
