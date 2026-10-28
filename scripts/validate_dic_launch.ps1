param([switch]$FrontendOnly)
$ErrorActionPreference='Stop'
$launchResults=[ordered]@{'Focused backend policy / guardian / QR / timetable / launch models and migrations'='NOT RUN';'Frontend tests'='NOT RUN';'Frontend lint'='NOT RUN';'Production build'='NOT RUN'}
$launchBackendName=@($launchResults.Keys)[0]
function Invoke-LaunchStep {
    param([string]$Name,[scriptblock]$Command)
    try { & $Command; if($LASTEXITCODE -ne 0){throw 'Check failed.'};$launchResults[$Name]='PASS' }
    catch {$launchResults[$Name]='FAIL';Write-Host ($Name+': check failed or runtime unavailable.')}
}
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if(-not $FrontendOnly){Invoke-LaunchStep $launchBackendName {& .\backend\.venv\Scripts\python.exe -B scripts\validate_dic_launch_policy.py}}
    Push-Location dawana-platform
    try {Invoke-LaunchStep 'Frontend tests' {& npm.cmd test};Invoke-LaunchStep 'Frontend lint' {& npm.cmd run lint};Invoke-LaunchStep 'Production build' {& npm.cmd run build}}
    finally {Pop-Location}
} finally {
    Pop-Location
    foreach($result in $launchResults.GetEnumerator()){Write-Host ($result.Value+': '+$result.Key)}
    Write-Host 'Database writes, imports/publication, live payments and deployment: NOT RUN.'
}
if(@($launchResults.Values | Where-Object {$_ -eq 'FAIL'}).Count){exit 1}
exit 0
