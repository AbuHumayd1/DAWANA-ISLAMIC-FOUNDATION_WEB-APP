$ErrorActionPreference = 'Stop'
$phase5Results = [ordered]@{
    'Backend policies and safe migration checks' = 'NOT RUN'
    'Frontend tests' = 'NOT RUN'
    'Frontend lint' = 'NOT RUN'
    'Frontend build' = 'NOT RUN'
}
$phase5Failed = $false

function Invoke-Phase5Step {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "`n--- $Name ---"
    $phase5Results[$Name] = 'FAIL'
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)." }
    $phase5Results[$Name] = 'PASS'
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Invoke-Phase5Step 'Backend policies and safe migration checks' {
        & .\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_policy.py
    }
    Push-Location dawana-platform
    try {
        Invoke-Phase5Step 'Frontend tests' { & npm.cmd test }
        Invoke-Phase5Step 'Frontend lint' { & npm.cmd run lint }
        Invoke-Phase5Step 'Frontend build' { & npm.cmd run build }
    } finally { Pop-Location }
} catch {
    $phase5Failed = $true
    Write-Host $_.Exception.Message
} finally {
    Pop-Location
    Write-Host "`nPhase 5 validation summary"
    foreach ($phase5Entry in $phase5Results.GetEnumerator()) {
        Write-Host ('{0}: {1}' -f $phase5Entry.Value, $phase5Entry.Key)
    }
    $phase5Complete = @($phase5Results.Values | Where-Object { $_ -ne 'PASS' }).Count -eq 0
    if ($phase5Failed -or -not $phase5Complete) { Write-Host 'OVERALL: FAIL / INCOMPLETE' }
    else { Write-Host 'OVERALL: PASS' }
}
if ($phase5Failed -or -not $phase5Complete) { exit 1 }
exit 0
