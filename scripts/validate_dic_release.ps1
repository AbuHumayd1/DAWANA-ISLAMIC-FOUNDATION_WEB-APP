param([switch]$FrontendOnly)
$ErrorActionPreference = 'Stop'
$phase7Results = [ordered]@{
    'Backend security, Paystack, Finance, Phase 5/6, production configuration and migration graph' = 'NOT RUN'
    'Frontend tests' = 'NOT RUN'
    'Frontend lint' = 'NOT RUN'
    'Frontend build' = 'NOT RUN'
}
$phase7Failed = $false
function Invoke-Phase7Step {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "`n--- $Name ---"
    $phase7Results[$Name] = 'FAIL'
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)." }
    $phase7Results[$Name] = 'PASS'
}
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (-not $FrontendOnly) {
        Invoke-Phase7Step 'Backend security, Paystack, Finance, Phase 5/6, production configuration and migration graph' {
            & .\backend\.venv\Scripts\python.exe -B scripts\validate_dic_release_policy.py
        }
    }
    Push-Location dawana-platform
    try {
        Invoke-Phase7Step 'Frontend tests' { & npm.cmd test }
        Invoke-Phase7Step 'Frontend lint' { & npm.cmd run lint }
        Invoke-Phase7Step 'Frontend build' { & npm.cmd run build }
    } finally { Pop-Location }
} catch {
    $phase7Failed = $true
    Write-Host $_.Exception.Message
} finally {
    Pop-Location
    Write-Host "`nFinal release validation summary"
    foreach ($phase7Entry in $phase7Results.GetEnumerator()) {
        Write-Host ('{0}: {1}' -f $phase7Entry.Value, $phase7Entry.Key)
    }
    $phase7Complete = @($phase7Results.Values | Where-Object { $_ -ne 'PASS' }).Count -eq 0
    if ($phase7Failed -or -not $phase7Complete) { Write-Host 'OVERALL: FAIL / INCOMPLETE' }
    else { Write-Host 'OVERALL: PASS' }
}
if ($phase7Failed -or -not $phase7Complete) { exit 1 }
exit 0


