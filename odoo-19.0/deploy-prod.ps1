param([switch]$NoPull, [switch]$AuditOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($NoPull) { $env:NO_PULL = 'YES' }
if ($AuditOnly) {
    python deploy/client_deploy.py production --preflight
} else {
    python deploy/client_deploy.py production
}
exit $LASTEXITCODE
