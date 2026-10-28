param([string]$PythonExe = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $PythonExe) { $PythonExe = Join-Path $root 'backend/.venv/Scripts/python.exe' }
$source = Get-Content -Raw -LiteralPath (Join-Path $root 'dawana-platform/src/components/layout/SiteChrome.jsx')
$logoUrl = [regex]::Match($source, "const logoSrc = '([^']+)'").Groups[1].Value
if (-not $logoUrl.StartsWith('https://lh3.googleusercontent.com/aida-public/')) { throw 'Existing official website logo source changed. Review it before caching; no substitute will be used.' }
$destination = [IO.Path]::GetFullPath((Join-Path $root 'backend/dic/static/dic/dawana-official-logo.img'))
if (-not $destination.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Logo target is outside the repository.' }
$validate = "import sys; from pathlib import Path; from PIL import Image; p=Path(sys.argv[1]); assert 0 < p.stat().st_size <= 2*1024*1024; image=Image.open(p); assert image.format in ('PNG','JPEG','WEBP'); assert image.width*image.height <= 20000000; image.verify()"
if (Test-Path -LiteralPath $destination) {
    & $PythonExe -B -c $validate $destination
    if ($LASTEXITCODE -ne 0) { throw 'Existing logo asset is invalid. It was preserved; restore an approved original rather than overwriting automatically.' }
    Write-Output 'Official website logo already cached and readable.'
    return
}
$privateDir = Join-Path $root '.local-preview'
New-Item -ItemType Directory -Force -Path $privateDir | Out-Null
$temporary = Join-Path $privateDir ('logo-download-' + [guid]::NewGuid().ToString('N') + '.img')
try {
    Invoke-WebRequest -UseBasicParsing -Uri $logoUrl -OutFile $temporary -TimeoutSec 30
    & $PythonExe -B -c $validate $temporary
    if ($LASTEXITCODE -ne 0) { throw 'The original website logo could not be validated; no asset installed.' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    if (Test-Path -LiteralPath $destination) { throw 'Logo target appeared during download; preserved without overwrite.' }
    Move-Item -LiteralPath $temporary -Destination $destination
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
    @{source=$logoUrl; sha256=$hash; note='Unmodified official asset referenced by SiteChrome.jsx'} | ConvertTo-Json | Set-Content -LiteralPath ($destination + '.json') -Encoding utf8
    Write-Output 'Cached the exact existing website logo. Cards embed it without external image requests.'
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
}
