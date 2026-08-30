# Easy Odoo update/install helper for FibraFRP on Docker Desktop.
#
# Common use:
#   .\deploy\easy_update.ps1
#   .\deploy\easy_update.ps1 -Install my_module
#   .\deploy\easy_update.ps1 -DbName qwerty -Install my_module

param(
    [string]$DbName = "",
    [string]$Install = "",
    [string]$Upgrade = "all",
    [string]$BackupDir = "secure_backups",
    [string]$DbUser = "odoo",
    [switch]$AuditOnly
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Stop-WithHelp {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Quick checks:" -ForegroundColor Yellow
    Write-Host "  1. Start Docker Desktop"
    Write-Host "  2. From this folder, run: docker compose up -d db"
    Write-Host "  3. Then run this helper again"
    exit 1
}

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Action
}

function Get-ApplicationDatabases {
    param([string]$DatabaseUser)
    $raw = docker compose exec -T db psql -U $DatabaseUser -d postgres -Atc `
        "SELECT datname FROM pg_database WHERE datistemplate=false AND datallowconn=true AND datname NOT IN ('postgres') ORDER BY datname;" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Stop-WithHelp "Could not read database list. Docker/PostgreSQL is not ready. Details: $raw"
    }
    return @($raw -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Resolve-DatabaseName {
    param(
        [string]$RequestedName,
        [string[]]$Databases
    )
    if ($RequestedName) {
        if ($Databases -notcontains $RequestedName) {
            Stop-WithHelp "Database '$RequestedName' was not found. Available databases: $($Databases -join ', ')"
        }
        return $RequestedName
    }

    if ($Databases.Count -eq 0) {
        Stop-WithHelp "No application databases were found."
    }
    if ($Databases.Count -eq 1) {
        Write-Host "Using database: $($Databases[0])" -ForegroundColor Green
        return $Databases[0]
    }

    Write-Host ""
    Write-Host "Available databases:" -ForegroundColor Yellow
    for ($index = 0; $index -lt $Databases.Count; $index++) {
        Write-Host "  $($index + 1). $($Databases[$index])"
    }

    $choice = Read-Host "Type the number to update"
    $choiceNumber = 0
    if (-not [int]::TryParse($choice, [ref]$choiceNumber)) {
        Stop-WithHelp "Invalid database choice."
    }
    if ($choiceNumber -lt 1 -or $choiceNumber -gt $Databases.Count) {
        Stop-WithHelp "Invalid database choice."
    }
    return $Databases[$choiceNumber - 1]
}

function Ensure-BackupPassphrase {
    if ($env:BACKUP_PASSPHRASE) {
        return
    }

    Write-Host ""
    Write-Host "A backup password is required before modules are changed." -ForegroundColor Yellow
    $secure = Read-Host "Backup password" -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
    if (-not $plain) {
        Stop-WithHelp "Backup password cannot be empty."
    }
    $env:BACKUP_PASSPHRASE = $plain
}

Invoke-Step "Checking addon folders and manifest dependencies" {
    python deploy\audit_addons_ready.py
    if ($LASTEXITCODE -ne 0) {
        Stop-WithHelp "Addon audit failed. Fix the listed manifest/path issue before installing modules."
    }
}

if ($AuditOnly) {
    Write-Host ""
    Write-Host "Audit complete. No database changes were made." -ForegroundColor Green
    exit 0
}

Invoke-Step "Starting PostgreSQL if needed" {
    docker compose up -d db
    if ($LASTEXITCODE -ne 0) {
        Stop-WithHelp "Could not start PostgreSQL. Is Docker Desktop running?"
    }
}

$databases = Get-ApplicationDatabases -DatabaseUser $DbUser
$targetDb = Resolve-DatabaseName -RequestedName $DbName -Databases $databases
Ensure-BackupPassphrase

$args = @(
    "-DbName", $targetDb,
    "-UpgradeModules", $Upgrade,
    "-BackupDir", $BackupDir,
    "-DbUser", $DbUser
)
if ($Install) {
    $args += @("-ExtraInstall", $Install, "-ExtraUpgrade", $Install)
}

Invoke-Step "Backing up, rebuilding, and updating modules" {
    & "$PSScriptRoot\safe_update_windows.ps1" @args
}

Write-Host ""
Write-Host "Done. Apps list and installed modules are updated for '$targetDb'." -ForegroundColor Green
if ($Install) {
    Write-Host "Installed/upgraded module(s): $Install" -ForegroundColor Green
}
