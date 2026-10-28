param([string]$PythonExe = '', [switch]$Restore, [switch]$DemoFormatsReviewed,
      [switch]$AuthorizeLegacyShutdown)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if (-not $PythonExe) { $PythonExe = Join-Path $root 'backend/.venv/Scripts/python.exe' }
$state = Join-Path $root '.local-preview'
$manifestPath = Join-Path $state 'servers.json'
$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($AuthorizeLegacyShutdown -and (-not $Restore -or -not $DemoFormatsReviewed)) {
    throw 'Legacy shutdown authorization requires both -Restore and -DemoFormatsReviewed. Nothing stopped.'
}
$all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue)
if ($listeners.Count -eq 0) { throw 'No listeners found. Nothing stopped; start the normal preview with -NoMigrations after validation.' }
$backend = @($all | Where-Object { $_.ProcessId -eq $manifest.backendLauncherPid })
$frontend = @($all | Where-Object { $_.ProcessId -eq $manifest.frontendPid })
if ($backend.Count -ne 1 -or $frontend.Count -ne 1) { throw 'Saved launchers are absent or changed. Nothing stopped; inspect current ownership manually.' }
$demoHelper = [IO.Path]::GetFullPath((Join-Path $root 'scripts/id_demo.py'))
$vite = [IO.Path]::GetFullPath((Join-Path $root 'dawana-platform/node_modules/vite/bin/vite.js'))
$venvPython = [IO.Path]::GetFullPath((Join-Path $root 'backend/.venv/Scripts/python.exe'))
$basePythonLine = Get-Content -LiteralPath (Join-Path $root 'backend/.venv/pyvenv.cfg') | Where-Object { $_ -match '^executable\s*=' } | Select-Object -First 1
if (-not $basePythonLine) { throw 'Cannot establish the project virtual environment interpreter. Nothing stopped.' }
$basePython = [IO.Path]::GetFullPath(($basePythonLine -replace '^executable\s*=\s*', '').Trim())
$pythonPaths = @($venvPython, $basePython) | Sort-Object -Unique
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$conhostPath = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32/conhost.exe'
function Normalize-CommandPath([string]$value) { return $value.Replace('/', [IO.Path]::DirectorySeparatorChar.ToString()) }
function Quoted-PathPattern([string]$value) {
    $escaped = [regex]::Escape((Normalize-CommandPath $value))
    return '(?:"' + $escaped + '"|' + $escaped + ')'
}
$pythonCommand = '^\s*(?:' + (($pythonPaths | ForEach-Object { Quoted-PathPattern $_ }) -join '|') + ')\s+(?:(?:-B|-u|-W\S+|-X\S+)\s+)*' + (Quoted-PathPattern $demoHelper) + '\s+serve\s*$'
$viteCommand = '^\s*' + (Quoted-PathPattern $nodePath) + '\s+' + (Quoted-PathPattern $vite) + '\s+--host\s+127\.0\.0\.1\s+--port\s+5173\s+--strictPort\s*$'
$conhostCommand = '^\s*' + (Quoted-PathPattern $conhostPath) + '(?:\s+(?:0x[0-9a-f]+|[0-9]+|-ForceV1))*\s*$'
function Process-Kind($process, [string]$branch) {
    if (-not $process.ExecutablePath -or -not $process.CommandLine -or -not $process.CreationDate) { return 'unknown' }
    $exe = Normalize-CommandPath $process.ExecutablePath
    $command = (Normalize-CommandPath $process.CommandLine) -replace '^\\\?\?\\', ''
    if ($branch -eq 'backend' -and $exe -in $pythonPaths -and $command -match $pythonCommand) { return 'python' }
    if ($branch -eq 'frontend' -and $exe -ieq $nodePath -and $command -match $viteCommand) { return 'vite' }
    if ($exe -ieq (Normalize-CommandPath $conhostPath) -and $command -match $conhostCommand) { return 'console' }
    return 'unknown'
}
$legacyManifest = $false
foreach ($entry in @(@{Process=$backend[0]; Field='backendStartedAtUtc'; Log=$manifest.backendLog}, @{Process=$frontend[0]; Field='frontendStartedAtUtc'; Log=$manifest.frontendLog})) {
    $saved = $manifest.($entry.Field)
    if ($saved) {
        if ([Math]::Abs(($entry.Process.CreationDate.ToUniversalTime() - ([DateTimeOffset]::Parse($saved)).UtcDateTime).TotalMilliseconds) -gt 1) { throw 'Saved launcher creation time differs: possible PID reuse. Nothing stopped.' }
    } else {
        # Old manifests retain a launch timestamp in their log filename, but not
        # exact process creation times. This is an audit cross-check, not proof.
        $legacyManifest = $true
        $stampMatch = [regex]::Match([IO.Path]::GetFileName($entry.Log), '^(\d{8}-\d{6})-')
        if (-not $stampMatch.Success) { throw 'Legacy manifest has no usable launch timestamp. Nothing stopped.' }
        $stampTime = [datetime]::ParseExact($stampMatch.Groups[1].Value, 'yyyyMMdd-HHmmss', [Globalization.CultureInfo]::InvariantCulture)
        $delta = ($entry.Process.CreationDate.ToLocalTime() - $stampTime).TotalSeconds
        if ($delta -lt 0 -or $delta -gt 30) { throw 'Launcher creation time conflicts with saved launch log timestamp. Nothing stopped.' }
    }
}
if ((Process-Kind $backend[0] 'backend') -ne 'python' -or (Process-Kind $frontend[0] 'frontend') -ne 'vite') { throw 'Saved launchers do not match exact project interpreter/script/arguments. Nothing stopped.' }
function Get-OwnedTree($snapshot) {
    $tree = @()
    $pending = @(@{Process=$backend[0]; Branch='backend'; Depth=0}, @{Process=$frontend[0]; Branch='frontend'; Depth=0})
    while ($pending.Count) {
        $item = $pending[0]
        $pending = @($pending | Select-Object -Skip 1)
        $process = $item.Process
        if ($tree | Where-Object { $_.Process.ProcessId -eq $process.ProcessId }) { throw 'Process ancestry cycle or duplicate. Nothing stopped.' }
        $kind = Process-Kind $process $item.Branch
        if ($kind -eq 'unknown') { throw "Unrecognized $($item.Branch) process PID $($process.ProcessId), parent $($process.ParentProcessId). Nothing stopped." }
        $tree += [pscustomobject]@{Process=$process; Branch=$item.Branch; Depth=$item.Depth; Kind=$kind}
        $descendants = @($snapshot | Where-Object { $_.ParentProcessId -eq $process.ProcessId })
        if ($kind -eq 'console' -and $descendants.Count) { throw 'Console host has unexpected descendants. Nothing stopped.' }
        foreach ($child in $descendants) {
            if (-not $child.CreationDate -or $child.CreationDate -lt $process.CreationDate) { throw 'Child predates its current parent: possible PID reuse. Nothing stopped.' }
            $pending += @{Process=$child; Branch=$item.Branch; Depth=$item.Depth+1}
        }
    }
    return $tree
}
function Assert-PortOwners($ports, $tree) {
    foreach ($port in @(8000,5173)) {
        $portEntries = @($ports | Where-Object { $_.LocalPort -eq $port })
        if (-not $portEntries.Count) { throw "Required port $port is not listening. Nothing stopped." }
        $expected = if ($port -eq 8000) { @($tree | Where-Object { $_.Branch -eq 'backend' -and $_.Kind -eq 'python' } | ForEach-Object { $_.Process.ProcessId }) } else { @($frontend[0].ProcessId) }
        foreach ($listener in $portEntries) {
            if ($listener.OwningProcess -notin $expected -or $listener.LocalAddress -notin @('127.0.0.1','::1')) { throw "Port $port ownership/address mismatch. Nothing stopped." }
        }
    }
}
$tree = @(Get-OwnedTree $all)
Assert-PortOwners $listeners $tree
$owned = @($tree | ForEach-Object { $_.Process })
if ($legacyManifest) { Write-Warning 'Legacy manifest: creation times agree with timestamped launch logs, but exact saved creation times are absent. Normal restoration is refused; a separately authorized legacy shutdown/restart is required.' }
# Inspection prints only these narrowly verified project commands, not arbitrary processes.
$owned | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | Format-List
$tokenFile = Join-Path $state 'diagnostic-token'
if (-not (Test-Path -LiteralPath $tokenFile)) { throw 'Running-app diagnostic is unavailable; restart the demo from its original console before restoration. Nothing stopped.' }
$headers = @{'X-Dawana-Local-Diagnostic'=(Get-Content -Raw -LiteralPath $tokenFile).Trim()}
$before = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/dic/local-preview/database/' -Headers $headers
$viaFrontend = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/v1/dic/local-preview/database/' -Headers $headers
if (-not $before.synthetic -or $before.database -ne $viaFrontend.database) { throw 'Backend/frontend are not using the same confirmed demo database. Nothing stopped.' }
Write-Output ('CONFIRMED running database via Django SELECT and Vite proxy: ' + $before.database)
$edition = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/v1/dic/registration-options/'
Write-Output ('Current edition supplied by backend: ' + $edition.name)
if (-not $Restore) { Write-Output 'READ-ONLY AUDIT COMPLETE. No process stopped and no database modified.'; return }
if ($legacyManifest -and -not $AuthorizeLegacyShutdown) { throw 'Restoration blocked: legacy manifest lacks exact saved process creation times. No process stopped. A separately authorized legacy shutdown/restart is required; never backfill historical metadata.' }
if ($AuthorizeLegacyShutdown -and -not $legacyManifest) { throw 'This is not a legacy manifest. Use normal restoration; no process stopped.' }
if (-not $DemoFormatsReviewed) { throw 'Review both synthetic formats before using -DemoFormatsReviewed. Nothing stopped.' }
# Rerun all identification/security checks before any process termination.
& (Join-Path $PSScriptRoot 'validate-dic-backend.ps1') -PythonExe $PythonExe -IdsOnly
if ($LASTEXITCODE -ne 0) { throw 'Focused validation failed. Demo preserved and running.' }
# Read-only normal preparation proves the target and refuses pending migrations.
& $PythonExe -B (Join-Path $PSScriptRoot 'local_preview.py') prepare --no-migrations
if ($LASTEXITCODE -ne 0) { throw 'Normal dawana_dev prerequisite failed; no process stopped. Pending migrations require separate approved backup-gated handling.' }
if ($legacyManifest) {
    # This is authorization of a CURRENT verified tree, never a claim that its
    # exact creation times were recorded at original launch.
    if ($before.database -ne 'dawana_ids_demo_c936c26ba558429eb4b4fda3b5c62668') {
        throw 'The running demo database differs from the legacy session approved for recovery. Nothing stopped; review the new identity separately.'
    }
    Write-Warning 'Historical creation timestamps are unavailable. This authorizes a one-time shutdown of the currently verified demo tree, followed by a fresh normal launch. All databases are preserved.'
    $owned | Select-Object ProcessId,ParentProcessId,CreationDate,ExecutablePath,CommandLine | Format-List
    $phrase = 'STOP VERIFIED DEMO AND RESTORE dawana_dev'
    if ((Read-Host "Type exactly '$phrase' to authorize shutdown of only the displayed verified processes") -cne $phrase) {
        throw 'Legacy shutdown not confirmed. Nothing stopped.'
    }
}
# Rebuild and compare the entire tree and port ownership after validation gates.
$freshAll = @(Get-CimInstance Win32_Process -ErrorAction Stop)
$freshTree = @(Get-OwnedTree $freshAll)
if ((($freshTree.Process.ProcessId | Sort-Object) -join ',') -ne (($tree.Process.ProcessId | Sort-Object) -join ',')) { throw 'Process tree changed during validation. Nothing stopped.' }
Assert-PortOwners @(Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction Stop) $freshTree
foreach ($process in $owned) {
    $fresh = @($freshAll | Where-Object { $_.ProcessId -eq $process.ProcessId })
    if ($fresh.Count -ne 1 -or $fresh[0].CreationDate -ne $process.CreationDate -or $fresh[0].ParentProcessId -ne $process.ParentProcessId -or $fresh[0].ExecutablePath -ne $process.ExecutablePath -or $fresh[0].CommandLine -ne $process.CommandLine) { throw 'Process identity changed. Nothing stopped.' }
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash -ne $manifestHash) {
    throw 'Preview manifest changed during review. Nothing stopped; audit the new session.'
}
$currentDatabase = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/dic/local-preview/database/' -Headers $headers
$currentProxyDatabase = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/v1/dic/local-preview/database/' -Headers $headers
if ($currentDatabase.database -ne $before.database -or $currentProxyDatabase.database -ne $before.database) {
    throw 'Running database identity changed during review. Nothing stopped.'
}
if ($legacyManifest) {
    # Preserve the original manifest bytes. A separate file labels observed
    # timestamps as recovery-time evidence, not historical launch metadata.
    $recoveryId = [guid]::NewGuid().ToString('N')
    $archivePath = Join-Path $state ('legacy-manifest-' + $recoveryId + '.json')
    [IO.File]::Copy($manifestPath, $archivePath, $false)
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash -ne $manifestHash) {
        throw 'Legacy manifest archive verification failed. Nothing stopped.'
    }
    $snapshot = @{
        observedAtUtc=[datetime]::UtcNow.ToString('o')
        evidenceType='Current process observation authorized for shutdown; NOT reconstructed launch metadata'
        originalManifestArchive=$archivePath; originalManifestSha256=$manifestHash
        databaseBefore=$before.database; intendedDatabaseAfter='dawana_dev'
        authorizedBy=[Environment]::UserName
        processes=@($tree | ForEach-Object { @{
            pid=$_.Process.ProcessId; parentPid=$_.Process.ParentProcessId
            observedCreationTimeUtc=$_.Process.CreationDate.ToUniversalTime().ToString('o')
            executable=$_.Process.ExecutablePath; commandLine=$_.Process.CommandLine
            kind=$_.Kind; branch=$_.Branch; depth=$_.Depth
        } })
    }
    $snapshotPath = Join-Path $state ('legacy-recovery-observation-' + $recoveryId + '.json')
    $stream = [IO.File]::Open($snapshotPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($snapshot | ConvertTo-Json -Depth 6))
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
    Write-Output ('Original manifest preserved and hash-verified: ' + $archivePath)
}
# Stop only verified Python/Vite processes, deepest first. Windows owns console
# host lifetime; never terminate a conhost explicitly.
foreach ($item in $tree | Where-Object { $_.Kind -ne 'console' } | Sort-Object Depth -Descending) {
    $process = $item.Process
    $fresh = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $process.ProcessId) -ErrorAction Stop
    if (-not $fresh) { continue }
    if ($fresh.CreationDate -ne $process.CreationDate -or $fresh.ParentProcessId -ne $process.ParentProcessId -or $fresh.CommandLine -ne $process.CommandLine -or $fresh.ExecutablePath -ne $process.ExecutablePath) { throw 'PID reused or ownership changed; refusing termination.' }
    Stop-Process -Id $fresh.ProcessId -ErrorAction Stop
}
$report = @{before=$before.database; demoPreserved=$true; stopped=@($tree | Where-Object { $_.Kind -ne 'console' } | ForEach-Object {$_.Process.ProcessId}); expectedAfter='dawana_dev'; legacyRecovery=[bool]$legacyManifest}
$reportPath = Join-Path $state ('restoration-'+[guid]::NewGuid().ToString('N')+'.json')
$report | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding utf8
& (Join-Path $PSScriptRoot 'start-local-preview.ps1') -PythonExe $PythonExe -NoMigrations
$after = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/dic/local-preview/database/' -Headers $headers
$proxy = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/v1/dic/local-preview/database/' -Headers $headers
if ($after.database -ne 'dawana_dev' -or $proxy.database -ne 'dawana_dev') { throw 'Restoration target check failed. Inspect before further action.' }
$actual = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/v1/dic/registration-options/'
$report.after=$after.database
$report.frontendProxyDatabase=$proxy.database
$report.actualEdition=$actual.name
$report.databaseRecordsModified=$false
$report | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Output ('RESTORED database: ' + $after.database + '; actual configured edition: ' + $actual.name)
if ($actual.name -match 'SYNTHETIC') { Write-Warning 'dawana_dev itself contains synthetic-labelled configuration. No records changed; review manually.' }
foreach ($route in @('/dic','/media','/')) { Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:5173'+$route) | Out-Null }
Write-Output 'Frontend routes and backend/proxy identity responded. Review real fee, venue, deadline and status in the browser; no replacement values were written.'
