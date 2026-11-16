param(
    [Parameter(Mandatory=$true)][string]$InspectionReceipt,
    [Parameter(Mandatory=$true)][string]$ApprovedBy,
    [Parameter(Mandatory=$true)][string]$BackupReference,
    [Parameter(Mandatory=$true)][string]$RestoreProcedure,
    [Parameter(Mandatory=$true)][string]$RollbackDecision,
    [Parameter(Mandatory=$true)][string]$ReviewedPlanSha256,
    [Parameter(Mandatory=$true)][switch]$OwnerAuthorized,
    [Parameter(Mandatory=$true)][switch]$BackupRestoreVerified,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
if (-not $OwnerAuthorized -or -not $BackupRestoreVerified) { throw 'Explicit owner and recovery approvals required.' }
$receipt = Get-Content -LiteralPath $InspectionReceipt -Raw | ConvertFrom-Json
$manifest = $receipt.manifest
if ($receipt.status -ne 'INSPECTED_READ_ONLY' -or $manifest.state -ne 'missing' -or
    $manifest.plan_sha256 -cne $ReviewedPlanSha256 -or
    @($manifest.pending).Count -ne 1 -or $manifest.pending[0].app -ne 'dic' -or
    $manifest.pending[0].name -ne '0042_integrated_camp_2026' -or
    $manifest.target_source_sha256 -ne '3d94da0a3c5e2213fd01362686c72498d88cfc362f27e74cdef47612868648d0') {
    throw 'Receipt is not the reviewed missing-schema, exact-0042 plan.'
}
foreach ($value in @($ApprovedBy,$BackupReference,$RestoreProcedure,$RollbackDecision)) {
    if ([string]::IsNullOrWhiteSpace($value)) { throw 'Approval evidence must be nonblank.' }
}
$approval = [ordered]@{
    manifest = $manifest; release_commit = $manifest.release_commit
    reviewed_plan_sha256 = $ReviewedPlanSha256; owner_authorized = $true; backup_restore_verified = $true
    approved_by = $ApprovedBy; approved_at = [DateTime]::UtcNow.ToString('o')
    backup_reference = $BackupReference; restore_procedure = $RestoreProcedure; rollback_decision = $RollbackDecision
}
$destination = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $destination) { throw 'Use a new private output directory; existing files are preserved.' }
[void][System.IO.Directory]::CreateDirectory($destination)
$raw = [System.Text.UTF8Encoding]::new($false).GetBytes(($approval | ConvertTo-Json -Depth 100 -Compress))
$hash = [System.Security.Cryptography.SHA256]::Create()
try { $digest = -join ($hash.ComputeHash($raw) | ForEach-Object { $_.ToString('x2') }) } finally { $hash.Dispose() }
[System.IO.File]::WriteAllBytes((Join-Path $destination 'approval.json'),$raw)
[System.IO.File]::WriteAllText((Join-Path $destination 'DAWANA_0042_APPROVAL_B64.txt'),[Convert]::ToBase64String($raw))
[System.IO.File]::WriteAllText((Join-Path $destination 'DAWANA_0042_APPROVAL_SHA256.txt'),$digest)
Write-Output 'Approval files prepared locally. Review privately; no database connection or migration was performed.'
