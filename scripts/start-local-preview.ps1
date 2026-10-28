param([string]$PythonExe = '', [string]$LocalDatabase = '', [string]$PgDumpPath = '', [switch]$IdDemo, [switch]$NoMigrations)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if (-not $PythonExe) { $PythonExe = Join-Path $root 'backend/.venv/Scripts/python.exe' }
& $PythonExe -c 'import django, environ, psycopg, PIL, boto3, qrcode'
if ($LASTEXITCODE -ne 0) { throw 'Python/dependencies unavailable. Supply -PythonExe with your working interpreter. No database changes attempted.' }
$node = (Get-Command node.exe -ErrorAction Stop).Source
$vite = Join-Path $root 'dawana-platform/node_modules/vite/bin/vite.js'
if (-not (Test-Path -LiteralPath $vite)) { throw 'Vite is missing. No installation or database changes attempted.' }
foreach ($port in @(8000,5173)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is occupied. Identify the existing server; this script will not kill or replace it."
    }
}
$helper = Join-Path $PSScriptRoot 'local_preview.py'
if ($IdDemo) { $helper = Join-Path $PSScriptRoot 'id_demo.py' }
$prepareArgs = @('-B', $helper, 'prepare')
if ($LocalDatabase -and -not $IdDemo) { $prepareArgs += @('--database', $LocalDatabase) }
if ($PgDumpPath -and -not $IdDemo) { $prepareArgs += @('--pg-dump', $PgDumpPath) }
if ($NoMigrations -and -not $IdDemo) { $prepareArgs += '--no-migrations' }
& $PythonExe @prepareArgs
if ($LASTEXITCODE -ne 0) { throw 'Preparation/Admin verification did not pass. Servers were not started.' }
$state = Join-Path $root '.local-preview'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backendLog = Join-Path $state "$stamp-backend.log"
$backendError = Join-Path $state "$stamp-backend-error.log"
$frontendLog = Join-Path $state "$stamp-frontend.log"
$frontendError = Join-Path $state "$stamp-frontend-error.log"
$backend = Start-Process -FilePath $PythonExe -ArgumentList @('-B', ('"' + $helper + '"'), 'serve') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $backendLog -RedirectStandardError $backendError
$oldProxy = $env:DJANGO_API_PROXY_TARGET
$oldBase = $env:VITE_API_BASE_URL
try {
    $env:DJANGO_API_PROXY_TARGET = 'http://127.0.0.1:8000'
    $env:VITE_API_BASE_URL = '/api/v1'
    $frontend = Start-Process -FilePath $node -ArgumentList @(('"' + $vite + '"'), '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory (Join-Path $root 'dawana-platform') -WindowStyle Hidden -PassThru -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendError
} finally {
    if ($null -eq $oldProxy) { Remove-Item Env:DJANGO_API_PROXY_TARGET -ErrorAction SilentlyContinue } else { $env:DJANGO_API_PROXY_TARGET = $oldProxy }
    if ($null -eq $oldBase) { Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue } else { $env:VITE_API_BASE_URL = $oldBase }
}
$healthy = $false
for ($attempt=0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/v1/health/' -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $healthy=$true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
$manifestPath = Join-Path $state 'servers.json'
if (Test-Path -LiteralPath $manifestPath) {
    $previousHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash
    $previousArchive = Join-Path $state ('servers-before-launch-' + [guid]::NewGuid().ToString('N') + '.json')
    [IO.File]::Copy($manifestPath, $previousArchive, $false)
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $previousArchive).Hash -ne $previousHash) {
        throw 'Previous preview manifest backup verification failed. Existing manifest retained; identify the newly launched servers before further action.'
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash -ne $previousHash) {
        throw 'Preview manifest changed during archival. Refusing to overwrite another session; inspect the newly launched servers.'
    }
}
@{backendLauncherPid=$backend.Id;frontendPid=$frontend.Id;backendStartedAtUtc=$backend.StartTime.ToUniversalTime().ToString('o');frontendStartedAtUtc=$frontend.StartTime.ToUniversalTime().ToString('o');backendLog=$backendLog;backendErrorLog=$backendError;frontendLog=$frontendLog;frontendErrorLog=$frontendError} | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8
if (-not $healthy) { throw 'Backend health did not pass. Inspect the retained .local-preview logs before starting another server.' }
try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/dic' -TimeoutSec 10 | Out-Null } catch { throw 'Frontend is not responding. Inspect its retained logs.' }
Write-Output 'Local backend health and frontend response: PASS.'
Write-Output 'DIC: http://127.0.0.1:5173/dic'
Write-Output 'Media: http://127.0.0.1:5173/media'
Write-Output 'Admin: http://127.0.0.1:8000/admin/'
Write-Output 'Proxied Admin: http://127.0.0.1:5173/admin/'
Write-Output 'Participant records / digital IDs: http://127.0.0.1:8000/admin/dic/campenrollment/'
Write-Output 'QR verification: http://127.0.0.1:8000/api/v1/dic/ids/verify/'
Write-Output 'Both servers reload source edits. PIDs/log paths: .local-preview/servers.json'
