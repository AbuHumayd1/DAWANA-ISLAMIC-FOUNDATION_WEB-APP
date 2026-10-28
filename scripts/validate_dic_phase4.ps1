param([switch]$FrontendOnly)
$ErrorActionPreference = 'Stop'
$phase4Results = [ordered]@{
    'Django checks; timetable validation, import, amendments, permissions, access, timezone; migration graph; Phase 3/5/6/7 regressions (database-free)' = 'NOT RUN'
    'Frontend tests' = 'NOT RUN'
    'Frontend lint' = 'NOT RUN'
    'Production build' = 'NOT RUN'
    'Database-writing acceptance tests (separate authorization required)' = 'NOT RUN'
}
$phase4BackendName = @($phase4Results.Keys)[0]
function Invoke-Phase4Step {
    param([string]$Name, [scriptblock]$Command)
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) { throw "Exit $LASTEXITCODE" }
        $phase4Results[$Name] = 'PASS'
    } catch {
        $phase4Results[$Name] = 'FAIL'
        Write-Host ($Name + ': ' + $_.Exception.Message)
    }
}
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (-not $FrontendOnly) {
        Invoke-Phase4Step $phase4BackendName { & .\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase4_policy.py }
    }
    Push-Location dawana-platform
    try {
        Invoke-Phase4Step 'Frontend tests' { & npm.cmd test }
        Invoke-Phase4Step 'Frontend lint' { & npm.cmd run lint }
        Invoke-Phase4Step 'Production build' { & npm.cmd run build }
    } finally { Pop-Location }
} finally {
    Pop-Location
    Write-Host "`nPhase 4 validation summary"
    foreach ($phase4Entry in $phase4Results.GetEnumerator()) { Write-Host ('{0}: {1}' -f $phase4Entry.Value, $phase4Entry.Key) }
}
if (@($phase4Results.Values | Where-Object { $_ -eq 'FAIL' }).Count) { exit 1 }
if (-not $FrontendOnly -and $phase4Results[$phase4BackendName] -ne 'PASS') { exit 1 }
exit 0
