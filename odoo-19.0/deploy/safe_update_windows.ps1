# safe_update_windows.ps1
# Production-safe update for FiberaFRP on Docker Desktop (Windows / PowerShell)
#
# USAGE:
#   $env:BACKUP_PASSPHRASE = "your-secret"
#   .\deploy\safe_update_windows.ps1 -DbName qwerty
#
# What it does (in order):
#   1. Verifies the database exists
#   2. Takes a plain pg_dump of every database into .\secure_backups\
#   3. Rebuilds the Odoo image
#   4. Stops Odoo + sidecar (DB stays running, data untouched)
#   5. Runs module install/upgrade --stop-after-init
#   6. Restarts Odoo + sidecar
#   7. Waits for healthy, prints module states
#
# What it NEVER does:
#   - Never runs docker compose down -v (volumes are never deleted)
#   - Never drops or truncates any database
#   - Never touches the filestore volume
#   - Never continues if backup fails

param(
    [Parameter(Mandatory=$true)]
    [string]$DbName,

    [string]$InstallModules = "",
    [string]$UpgradeModules = "all",
    [string]$ExtraInstall   = "",
    [string]$ExtraUpgrade   = "",
    [string]$BackupDir      = "secure_backups",
    [string]$DbUser         = "odoo"
)

$ErrorActionPreference = "Stop"

# Always run from the project root (one level above /deploy)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Join-Csv {
    param([string[]]$Items)
    return (($Items | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() }) -join ",")
}

function Expand-UpgradeModules {
    param(
        [string]$Csv,
        [string]$DatabaseName,
        [string]$DatabaseUser
    )

    $items = @($Csv -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($items -notcontains "all") {
        return (Join-Csv $items)
    }

    $installed = docker compose exec -T db psql -U $DatabaseUser -d $DatabaseName -Atc `
        "SELECT COALESCE(string_agg(name, ',' ORDER BY name), '') FROM ir_module_module WHERE state IN ('installed', 'to upgrade');" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ERROR: Could not read installed modules for '$DatabaseName'. $installed"
    }
    $installedItems = @($installed -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($installedItems.Count -eq 0) {
        Write-Error "ERROR: No installed modules found for '$DatabaseName'; refusing to run an empty upgrade."
    }

    $explicitItems = @($items | Where-Object { $_ -ne "all" })
    return (Join-Csv ($installedItems + $explicitItems))
}

Write-Host "==> Production-safe update for database: $DbName" -ForegroundColor Cyan

# 1. Validate backup passphrase
if (-not $env:BACKUP_PASSPHRASE) {
    Write-Error "ERROR: Set `$env:BACKUP_PASSPHRASE before running this script. Refusing to proceed without backup capability."
}

# 2. Validate database exists
$dbExists = docker compose exec -T db psql -U $DbUser -d postgres -Atc `
    "SELECT 1 FROM pg_database WHERE datname = '$DbName';" 2>&1
if ($dbExists -ne "1") {
    Write-Error "ERROR: Database '$DbName' does not exist. Aborting."
}
Write-Host "==> Database '$DbName' confirmed." -ForegroundColor Green

# 3. Backup ALL databases
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$allDbs = (docker compose exec -T db psql -U $DbUser -d postgres -Atc `
    "SELECT datname FROM pg_database WHERE datistemplate=false AND datallowconn=true AND datname NOT IN ('postgres') ORDER BY datname;") -split "`n" | Where-Object { $_.Trim() }

Write-Host "==> Backing up $($allDbs.Count) database(s) to .\$BackupDir" -ForegroundColor Cyan
$backupOk = $true
foreach ($db in $allDbs) {
    $db = $db.Trim()
    if (-not $db) { continue }
    $dumpFile = "$BackupDir\${db}_${timestamp}.pg_dump"
    Write-Host "    Dumping $db -> $dumpFile"
    docker compose exec -T db pg_dump -U $DbUser -d $db --format=custom | Set-Content -Path $dumpFile -AsByteStream
    if (-not (Test-Path $dumpFile) -or (Get-Item $dumpFile).Length -eq 0) {
        Write-Host "    FAILED backup for $db" -ForegroundColor Red
        $backupOk = $false
    } else {
        $size = [math]::Round((Get-Item $dumpFile).Length / 1MB, 2)
        Write-Host "    OK: $db ($size MB)" -ForegroundColor Green
    }
}

if (-not $backupOk) {
    Write-Error "ERROR: One or more backups failed. Refusing to continue."
}
Write-Host "==> All databases backed up successfully." -ForegroundColor Green

# 4. Build new Odoo image
Write-Host "==> Building Odoo image..." -ForegroundColor Cyan
docker compose build odoo
if ($LASTEXITCODE -ne 0) { Write-Error "ERROR: docker compose build failed." }

# 5. Stop Odoo + sidecar (DB stays up, data untouched)
Write-Host "==> Stopping Odoo and WhatsApp sidecar..." -ForegroundColor Cyan
docker compose stop sidecar 2>$null
docker compose stop odoo 2>$null

# 6. Install / upgrade modules
$allInstall = $InstallModules
if ($ExtraInstall) { $allInstall = Join-Csv @($allInstall, $ExtraInstall) }
$allUpgrade = $UpgradeModules
if ($ExtraUpgrade) { $allUpgrade = "$allUpgrade,$ExtraUpgrade" }
$allUpgrade = Expand-UpgradeModules -Csv $allUpgrade -DatabaseName $DbName -DatabaseUser $DbUser

Write-Host "==> Installing: $allInstall" -ForegroundColor Cyan
Write-Host "==> Upgrading:  $allUpgrade" -ForegroundColor Cyan

$moduleArgs = @()
if ($allInstall) {
    $moduleArgs += @("-i", $allInstall)
}
if ($allUpgrade) {
    $moduleArgs += @("-u", $allUpgrade)
}

docker compose run --rm -T --no-deps odoo `
    python3 /opt/odoo/odoo-bin `
        -c /etc/odoo/odoo.conf `
        -d $DbName `
        @moduleArgs `
        --stop-after-init
if ($LASTEXITCODE -ne 0) { Write-Error "ERROR: Module upgrade failed. DB is intact - restore not needed unless Odoo reports migration errors." }

# 7. Restart Odoo + sidecar
Write-Host "==> Starting Odoo and WhatsApp sidecar..." -ForegroundColor Cyan
docker compose up -d odoo sidecar

# 8. Wait for healthy
Write-Host "==> Waiting for Odoo to become healthy (up to 120s)..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(120)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep 5
    $status = (docker inspect --format="{{.State.Health.Status}}" odoo_app 2>$null)
    if ($status -eq "healthy") { $healthy = $true; break }
    Write-Host "    Still waiting... ($status)"
}
if (-not $healthy) { Write-Warning "Odoo did not become healthy within 120s. Check: docker logs --tail 100 odoo_app" }
else { Write-Host "==> Odoo is healthy." -ForegroundColor Green }

# 9. Module state report
Write-Host "==> Module states in $DbName :" -ForegroundColor Cyan
docker compose exec -T db psql -U $DbUser -d $DbName -c `
    "SELECT name, state, latest_version FROM ir_module_module WHERE name IN ('elsx_client_restrictions','elsx_rebrand','elsx_attendance_tracking','elsx_face_attendance','elsx_whatsapp_marketing','elsx_tally_integration','crm','account','hr_attendance') ORDER BY name;"

# 10. Container status
docker compose ps

Write-Host ""
Write-Host "==> Safe update complete." -ForegroundColor Green
Write-Host "    Backups in: .\$BackupDir"
Write-Host "    Check logs: docker logs --tail 250 odoo_app"
Write-Host "    Prune old backups (>7 days): Get-ChildItem $BackupDir\*.pg_dump | Where-Object LastWriteTime -lt (Get-Date).AddDays(-7) | Remove-Item"
