param([string]$PythonExe = '', [switch]$IdDemo, [switch]$IdsOnly,
      [string]$PgDumpPath = 'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if (-not $PythonExe) { $PythonExe = Join-Path $root 'backend/.venv/Scripts/python.exe' }
# Installs only qrcode, only when absent, only in the selected project venv.
$validation = @{PythonExe=$PythonExe; InstallIdDependency=$true}
if ($IdsOnly) { $validation.IdsOnly=$true } else { $validation.Phase2And3=$true }
& (Join-Path $PSScriptRoot 'validate-dic-backend.ps1') @validation
if ($LASTEXITCODE -ne 0) { throw 'Complete focused validation did not pass; no application startup or migration attempted.' }
& (Join-Path $PSScriptRoot 'cache-id-logo.ps1') -PythonExe $PythonExe
if ($IdDemo) {
    & (Join-Path $PSScriptRoot 'start-local-preview.ps1') -PythonExe $PythonExe -IdDemo
} else {
    # Preparation now requires dawana_dev and still prompts for exact confirmation.
    & (Join-Path $PSScriptRoot 'start-local-preview.ps1') -PythonExe $PythonExe -PgDumpPath $PgDumpPath
}
