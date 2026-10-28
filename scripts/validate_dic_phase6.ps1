param([switch]$FrontendOnly)
$ErrorActionPreference = 'Stop'
$phase6Results = [ordered]@{
    'Backend reporting, reconciliation, authorization, QR, housing, feedback and migration checks' = 'NOT RUN'
    'Frontend tests' = 'NOT RUN'
    'Frontend lint' = 'NOT RUN'
    'Frontend build' = 'NOT RUN'
}
$phase6Failed = $false
function Invoke-Phase6Step {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "`n--- $Name ---"
    $phase6Results[$Name] = 'FAIL'
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)." }
    $phase6Results[$Name] = 'PASS'
}
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (-not $FrontendOnly) {
        Invoke-Phase6Step 'Backend reporting, reconciliation, authorization, QR, housing, feedback and migration checks' {
            & .\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase6_policy.py
        }
    }
    Push-Location dawana-platform
    try {
        Invoke-Phase6Step 'Frontend tests' { & npm.cmd test }
        Invoke-Phase6Step 'Frontend lint' { & npm.cmd run lint }
        Invoke-Phase6Step 'Frontend build' { & npm.cmd run build }
    } finally { Pop-Location }
} catch {
    $phase6Failed = $true
    Write-Host $_.Exception.Message
} finally {
    Pop-Location
    Write-Host "`nPhase 6 validation summary"
    foreach ($phase6Entry in $phase6Results.GetEnumerator()) {
        Write-Host ('{0}: {1}' -f $phase6Entry.Value, $phase6Entry.Key)
    }
    $phase6Complete = @($phase6Results.Values | Where-Object { $_ -ne 'PASS' }).Count -eq 0
    if ($phase6Failed -or -not $phase6Complete) { Write-Host 'OVERALL: FAIL / INCOMPLETE' }
    else { Write-Host 'OVERALL: PASS' }
}
if ($phase6Failed -or -not $phase6Complete) { exit 1 }
exit 0
