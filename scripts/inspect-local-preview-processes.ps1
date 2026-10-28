# Read-only process inventory. No database requests, server control or Git changes.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $root '.local-preview/servers.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'No saved preview manifest. Nothing changed.' }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue)
$wanted = @([uint32]$manifest.backendLauncherPid, [uint32]$manifest.frontendPid) + @($listeners | ForEach-Object { [uint32]$_.OwningProcess })
# Include the launchers' descendants, then their immediate parents. No termination.
do {
    $previousCount = $wanted.Count
    $wanted = @($wanted + @($all | Where-Object { $_.ParentProcessId -in $wanted } | ForEach-Object { [uint32]$_.ProcessId }) | Sort-Object -Unique)
} while ($wanted.Count -ne $previousCount)
$wanted = @($wanted + @($all | Where-Object { $_.ProcessId -in $wanted } | ForEach-Object { [uint32]$_.ParentProcessId }) | Sort-Object -Unique)
Write-Output ('Saved backend launcher: ' + $manifest.backendLauncherPid)
Write-Output ('Saved frontend launcher: ' + $manifest.frontendPid)
foreach ($savedId in @($manifest.backendLauncherPid, $manifest.frontendPid)) {
    if (-not ($all | Where-Object { $_.ProcessId -eq $savedId })) { Write-Output ("STALE: saved PID $savedId is absent.") }
}
$listeners | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
foreach ($process in $all | Where-Object { $_.ProcessId -in $wanted } | Sort-Object ProcessId) {
    $command = [string]$process.CommandLine
    # Preserve full process structure except potential credential-bearing values.
    $command = $command -replace '(?i)postgres(?:ql)?://\S+', '[REDACTED DATABASE URL]'
    $command = $command -replace '(?i)((?:--?|/|\b)(?:password|passwd|secret|token|api[-_]?key|access[-_]?key)\s*(?:=|:|\s)\s*)(?:"[^"]*"|''[^'']*''|\S+)', '$1[REDACTED]'
    [pscustomobject]@{
        ProcessId=$process.ProcessId; ParentProcessId=$process.ParentProcessId
        CreationDate=$process.CreationDate; ExecutablePath=$process.ExecutablePath
        CommandLine=$command
    } | Format-List
}
Write-Output 'READ-ONLY inspection complete. No processes stopped, servers restarted or databases accessed.'
