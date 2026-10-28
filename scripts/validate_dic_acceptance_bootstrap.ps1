param(
    [switch]$SyntheticConfig,
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin'
)
$ErrorActionPreference = 'Stop'
$bootstrapExit = 1
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $bootstrapArgs = @('-B', 'scripts\validate_dic_acceptance_bootstrap.py', '--pg-bin', $PgBin)
    if ($SyntheticConfig) { $bootstrapArgs += '--synthetic-config' }
    & .\backend\.venv\Scripts\python.exe @bootstrapArgs
    $bootstrapExit = $LASTEXITCODE
    if ($bootstrapExit -ne 0) { Write-Host 'INCOMPLETE: bootstrap checks did not all pass; no provisioning is authorized by this runner.' }
} catch {
    Write-Host 'NOT RUN: Python/bootstrap could not execute; raw diagnostics suppressed.'
} finally {
    Pop-Location
    Write-Host 'Provisioning, database connections, migrations, fixture inserts, real payments and deliveries: NOT RUN.'
}
exit $bootstrapExit
