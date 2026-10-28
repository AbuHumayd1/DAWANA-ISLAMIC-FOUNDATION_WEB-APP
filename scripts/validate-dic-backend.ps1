param(
    [string]$PythonExe = '',
    [string]$FfprobePath = '',
    [switch]$InstallFfprobe,
    [switch]$HousingOnly,
    [switch]$IdsOnly,
    [switch]$Phase2And3,
    [switch]$InstallIdDependency
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if ((Get-Location).Path -ne $repoRoot) { Set-Location -LiteralPath $repoRoot }

# No Git mutations, dependency reinstall, database deletion or live services.
$candidates = @()
if ($PythonExe) { $candidates += @{Exe=$PythonExe; Prefix=@()} }
else {
    $candidates += @{Exe=(Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'); Prefix=@()}
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += @{Exe=$command.Source; Prefix=@()} }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) { $candidates += @{Exe=$launcher.Source; Prefix=@('-3.13')} }
}
$chosen = $null
foreach ($candidate in $candidates) {
    try {
        $prefix = $candidate.Prefix
        & $candidate.Exe @prefix -c 'import sys; print(sys.version.split()[0])' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $chosen = $candidate; break }
    } catch { }
}
if (-not $chosen) { throw 'No accessible Python interpreter. Supply -PythonExe with your working interpreter; nothing else was changed.' }
$prefix = $chosen.Prefix
& $chosen.Exe @prefix -c 'import django, environ, psycopg, PIL, boto3, cryptography, rest_framework'
if ($LASTEXITCODE -ne 0) { throw 'Required backend dependencies are missing from the selected interpreter. No installation or database change attempted.' }
Write-Output 'Python and required backend imports: PASS.'
if ($IdsOnly -or $Phase2And3) {
    $hasQr = $false
    try { & $chosen.Exe @prefix -c 'import qrcode' 2>$null; $hasQr = $LASTEXITCODE -eq 0 } catch { $hasQr = $false }
    if (-not $hasQr -and $InstallIdDependency) {
        & $chosen.Exe @prefix -c 'import sys; assert sys.prefix != sys.base_prefix, "Use the existing project virtual environment for dependency installation"'
        if ($LASTEXITCODE -ne 0) { throw 'Refusing a system-wide dependency installation.' }
        & $chosen.Exe @prefix -m pip --isolated install --index-url https://pypi.org/simple --no-input 'qrcode>=8.0,<9'
        if ($LASTEXITCODE -ne 0) { throw 'Local qrcode dependency installation failed. No database changes attempted.' }
    } elseif (-not $hasQr) { throw 'qrcode is missing. Rerun with -InstallIdDependency using the existing virtual environment.' }
}
if ($HousingOnly -or $IdsOnly -or $Phase2And3) {
    if ($IdsOnly -or $Phase2And3) {
        & $chosen.Exe @prefix -B -c 'import reportlab, pypdf, fitz, cv2, numpy'
        if ($LASTEXITCODE -ne 0) { throw 'ID validation dependencies are missing. Install backend/requirements-test-ids.txt in the existing environment. No database changes attempted.' }
    }
    $suiteOption = '--housing-only'
    if ($IdsOnly) { $suiteOption = '--ids-only' }
    if ($Phase2And3) { $suiteOption = '--phase2-and3' }
    & $chosen.Exe @prefix -B (Join-Path $PSScriptRoot 'validate_dic_backend.py') $suiteOption
    if ($LASTEXITCODE -ne 0) { throw 'Housing validation failed or was blocked. Read validation-results JSON and redacted log.' }
    Write-Output 'PASS: complete focused test execution and migration parity. Inspect actual counts in validation-results JSON; isolated test database retained.'
    return
}

if ($FfprobePath) {
    $FfprobePath = (Resolve-Path -LiteralPath $FfprobePath).Path
} else {
    $probe = Get-Command ffprobe.exe -ErrorAction SilentlyContinue
    if ($probe) { $FfprobePath = $probe.Source }
    $portableProbe = Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Links/ffprobe.exe'
    if (-not $FfprobePath -and (Test-Path -LiteralPath $portableProbe)) { $FfprobePath = $portableProbe }
}
if (-not $FfprobePath -and $InstallFfprobe) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'WinGet unavailable. Supply -FfprobePath to an existing trusted Windows FFmpeg bundle. No databases changed.' }
    Write-Output 'Installing free Gyan.FFmpeg portable tools for this Windows user only.'
    & $winget.Source install --id Gyan.FFmpeg --exact --source winget --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'Per-user FFmpeg installation did not succeed. No fallback to administrator/system installation; no databases changed.' }
    $probe = Get-Command ffprobe.exe -ErrorAction SilentlyContinue
    if ($probe) { $FfprobePath = $probe.Source }
    if (-not $FfprobePath -and (Test-Path -LiteralPath $portableProbe)) { $FfprobePath = $portableProbe }
    if (-not $FfprobePath) { throw 'FFmpeg installed but ffprobe link is unavailable in this session. Supply its executable using -FfprobePath. No databases changed.' }
}
$runnerArgs = @('-B', (Join-Path $PSScriptRoot 'validate_dic_backend.py'))
if ($FfprobePath) {
    & $FfprobePath -version 2>$null | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { throw 'ffprobe cannot execute. No databases changed.' }
    $runnerArgs += @('--ffprobe', $FfprobePath)
} else {
    Write-Output 'ffprobe missing: mocked tests will still run; genuine MP4 check will report BLOCKED.'
}
Write-Output 'Starting read-only inspection, migration parity check and isolated local backend tests.'
& $chosen.Exe @prefix @runnerArgs
$validationExit = $LASTEXITCODE
Write-Output 'Reports are under validation-results/. No existing database is dropped, overwritten or migrated.'
if ($validationExit -ne 0) { throw 'Backend validation did not fully pass. Read the JSON summary and redacted test log before any rerun.' }
Write-Output 'PASS: focused backend tests, migration parity and genuine MP4 check.'
