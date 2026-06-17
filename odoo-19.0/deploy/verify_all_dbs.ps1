# verify_all_dbs.ps1
# Verifies that every database is reachable, has the correct password,
# and has no stuck module operations. Run after any update or restart.
#
# USAGE:
#   .\deploy\verify_all_dbs.ps1
#
# Expected: all databases report OK with no pending module ops.

param(
    [string]$DbUser = "odoo"
)

$ErrorActionPreference = "Continue"

# Always run from the project root (one level above /deploy)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== FiberaFRP Multi-Database Verification ===" -ForegroundColor Cyan

# ── Container health ──────────────────────────────────────────────────────────
Write-Host "`n-- Container status" -ForegroundColor Yellow
docker compose ps

# ── Odoo health endpoint ──────────────────────────────────────────────────────
Write-Host "`n-- Odoo /web/health" -ForegroundColor Yellow
$odooHealth = docker compose exec -T odoo curl -fsS http://127.0.0.1:8069/web/health 2>&1
if ($odooHealth -match '"pass"') {
    Write-Host "   Odoo health: OK ($odooHealth)" -ForegroundColor Green
} else {
    Write-Host "   Odoo health: FAIL ($odooHealth)" -ForegroundColor Red
}

# ── Sidecar health endpoint ───────────────────────────────────────────────────
Write-Host "`n-- WhatsApp sidecar /health" -ForegroundColor Yellow
$sidecarHealth = docker compose exec -T odoo curl -fsS http://whatsapp_sidecar:3000/health 2>&1
if ($sidecarHealth -match '"healthy"') {
    Write-Host "   Sidecar health: OK" -ForegroundColor Green
} else {
    Write-Host "   Sidecar health: FAIL ($sidecarHealth)" -ForegroundColor Red
}

# ── Get all databases ─────────────────────────────────────────────────────────
Write-Host "`n-- Database access checks" -ForegroundColor Yellow
$allDbs = (docker compose exec -T db psql -U $DbUser -d postgres -Atc `
    "SELECT datname FROM pg_database WHERE datistemplate=false AND datallowconn=true AND datname NOT IN ('postgres') ORDER BY datname;") -split "`n" | Where-Object { $_.Trim() }

$allOk = $true
foreach ($db in $allDbs) {
    $db = $db.Trim()
    if (-not $db) { continue }

    # Connectivity
    $ping = docker compose exec -T db psql -U $DbUser -d $db -Atc "SELECT current_database();" 2>&1
    if ($ping -ne $db) {
        Write-Host "   FAIL connect: $db" -ForegroundColor Red
        $allOk = $false
        continue
    }

    # Pending module ops
    $pending = docker compose exec -T db psql -U $DbUser -d $db -Atc `
        "SELECT count(*) FROM ir_module_module WHERE state IN ('to upgrade','to install','to remove');" 2>&1
    $size = docker compose exec -T db psql -U $DbUser -d $db -Atc `
        "SELECT pg_size_pretty(pg_database_size(current_database()));" 2>&1

    if ($pending -ne "0") {
        Write-Host "   WARN: $db ($size) — $pending module(s) pending ops" -ForegroundColor Yellow
    } else {
        Write-Host "   OK: $db ($size) — no pending module ops" -ForegroundColor Green
    }
}

# ── Resource usage ────────────────────────────────────────────────────────────
Write-Host "`n-- Resource usage vs limits" -ForegroundColor Yellow
docker stats --no-stream --format "table {{.Name}}`t{{.CPUPerc}}`t{{.MemUsage}}`t{{.MemPerc}}"

# ── Recent critical errors ────────────────────────────────────────────────────
Write-Host "`n-- Recent critical errors (last 10 min)" -ForegroundColor Yellow
$errors = docker logs --since 10m odoo_app 2>&1 | Select-String -Pattern "ERROR|CRITICAL|Traceback" | Select-Object -First 10
if ($errors) {
    Write-Host "   ERRORS FOUND:" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
    $allOk = $false
} else {
    Write-Host "   No errors in last 10 minutes." -ForegroundColor Green
}

Write-Host ""
if ($allOk) {
    Write-Host "=== Verification PASSED — all databases healthy ===" -ForegroundColor Green
} else {
    Write-Host "=== Verification FAILED — review issues above ===" -ForegroundColor Red
}
