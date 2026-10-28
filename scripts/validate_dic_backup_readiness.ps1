param(
    [string]$PgBin = $env:DIC_PG_BIN,
    [string]$Username = $env:DIC_DEMO_PG_USER,
    [string]$Destination,
    [switch]$SkipPython
)
# Safe checks only. This wrapper NEVER requests --check-connection or reads credentials.
$ErrorActionPreference = 'Stop'
$stepBRoot = Split-Path -Parent $PSScriptRoot
$stepBResults = [ordered]@{
    'Pinned migration receipt and repository migration hashes' = 'NOT RUN'
    'PostgreSQL executable discovery and matching versions' = 'NOT RUN'
    'Focused database-free workflow unit tests' = 'NOT RUN'
    'Offline configured-target preflight' = 'NOT RUN'
    'Live read-only identity/version/space check' = 'NOT RUN'
    'Real backup / archive integrity / disposable restore' = 'NOT RUN'
}
Push-Location $stepBRoot
try {
    try {
        $stepBReceiptPath = Join-Path $stepBRoot 'output\acceptance\migration-verification-2c9499d80e584c1ca72fc04efe0d68b9.json'
        $stepBReceiptHash = (Get-FileHash -LiteralPath $stepBReceiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($stepBReceiptHash -ne 'c70fa32d1de80e6e426a2f90d8a030548cdf5bdd96c8063a822a076b05e27d9f') { throw 'Pinned receipt checksum mismatch.' }
        $stepBReceipt = Get-Content -LiteralPath $stepBReceiptPath -Raw | ConvertFrom-Json
        if ($stepBReceipt.identity.database -ne 'dic_2026_demo' -or $stepBReceipt.identity.host -ne '127.0.0.1' -or $stepBReceipt.identity.port -ne '5432' -or $stepBReceipt.identity.transaction_read_only -ne $true -or $stepBReceipt.database_writes -ne $false -or $stepBReceipt.applied.Count -ne 44 -or $stepBReceipt.pending.Count -ne 11) { throw 'Pinned receipt identity/count mismatch.' }
        foreach ($stepBMigration in $stepBReceipt.manifest.steps) {
            if ($stepBMigration.app -notmatch '^[a-z_]+$' -or $stepBMigration.name -notmatch '^[a-z0-9_]+$') { throw 'Unsafe receipt source path.' }
            $stepBMigrationPath = Join-Path $stepBRoot ('backend\' + $stepBMigration.app + '\migrations\' + $stepBMigration.name + '.py')
            if (Test-Path -LiteralPath $stepBMigrationPath -PathType Leaf) {
                if ((Get-FileHash -LiteralPath $stepBMigrationPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $stepBMigration.source_sha256) { throw 'Migration source differs from preserved receipt.' }
            }
        }
        $stepBResults['Pinned migration receipt and repository migration hashes'] = 'PASS'
    } catch { $stepBResults['Pinned migration receipt and repository migration hashes'] = 'FAIL'; Write-Host 'Receipt/source integrity check failed; preserved originals were not changed.' }

    try {
        $stepBFolders = @()
        if ($PgBin) { $stepBFolders = @($PgBin) }
        else {
            $stepBInstallRoot = Join-Path $env:ProgramFiles 'PostgreSQL'
            if (Test-Path -LiteralPath $stepBInstallRoot) {
                $stepBFolders = @(Get-ChildItem -LiteralPath $stepBInstallRoot -Directory | Where-Object Name -Match '^\d+$' | Sort-Object { [int]$_.Name } -Descending | ForEach-Object { Join-Path $_.FullName 'bin' })
            }
            $stepBPsqlCommand = Get-Command psql.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($stepBPsqlCommand) { $stepBFolders += Split-Path -Parent $stepBPsqlCommand.Source }
        }
        $stepBSelected = $null
        foreach ($stepBFolder in $stepBFolders) {
            if (-not [IO.Path]::IsPathRooted($stepBFolder)) { throw 'Absolute trusted PgBin is required.' }
            $stepBComplete = $true
            foreach ($stepBTool in @('pg_dump','pg_restore','psql')) {
                if (-not (Test-Path -LiteralPath (Join-Path $stepBFolder ($stepBTool + '.exe')) -PathType Leaf)) { $stepBComplete = $false }
            }
            if ($stepBComplete) { $stepBSelected = $stepBFolder; break }
        }
        if (-not $stepBSelected) { throw 'Toolset unavailable.' }
        $stepBVersions = @()
        foreach ($stepBTool in @('pg_dump','pg_restore','psql')) {
            $stepBExecutable = Join-Path $stepBSelected ($stepBTool + '.exe')
            # Only --version is executed; capture and never print raw diagnostics.
            $stepBVersionOutput = & $stepBExecutable --version 2>$null
            if ($LASTEXITCODE -ne 0 -or $stepBVersionOutput -notmatch ('^' + $stepBTool + ' \(PostgreSQL\) (\d+\.\d+)')) { throw 'Version check failed.' }
            $stepBVersions += $Matches[1]
        }
        if (@($stepBVersions | Select-Object -Unique).Count -ne 1) { throw 'Tool version mismatch.' }
        Write-Host ('Toolset: ' + $stepBSelected + ' (PostgreSQL ' + $stepBVersions[0] + '); server compatibility NOT RUN.')
        $stepBResults['PostgreSQL executable discovery and matching versions'] = 'PASS'
    } catch { $stepBResults['PostgreSQL executable discovery and matching versions'] = 'FAIL'; Write-Host 'Tool discovery/version check failed. Configure a trusted complete PgBin; no software was installed.' }

    if (-not $SkipPython) {
        try {
            & .\backend\.venv\Scripts\python.exe -B -m unittest discover -s scripts -p test_dic_backup_readiness.py -v
            if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed/unavailable.' }
            $stepBResults['Focused database-free workflow unit tests'] = 'PASS'
        } catch { $stepBResults['Focused database-free workflow unit tests'] = 'FAIL' }
        if ($Username) {
            try {
                $stepBArguments = @('-B', 'scripts\dic_backup_readiness.py', '--username', $Username)
                if ($PgBin) { $stepBArguments += @('--pg-bin', $PgBin) }
                if ($Destination) { $stepBArguments += @('--destination', $Destination) }
                & .\backend\.venv\Scripts\python.exe @stepBArguments
                if ($LASTEXITCODE -ne 0) { throw 'Preflight failed/unavailable.' }
                $stepBResults['Offline configured-target preflight'] = 'PASS'
            } catch { $stepBResults['Offline configured-target preflight'] = 'FAIL' }
        }
    }
} finally {
    Pop-Location
    Write-Host "`nStep B safe validation summary"
    foreach ($stepBResult in $stepBResults.GetEnumerator()) { Write-Host ('{0}: {1}' -f $stepBResult.Value, $stepBResult.Key) }
    Write-Host 'No backup, restore, migration, database write or production connection was requested.'
}
if (@($stepBResults.Values | Where-Object { $_ -eq 'FAIL' }).Count) { exit 1 }
if ($SkipPython -or -not $Username) { Write-Host 'OVERALL: INCOMPLETE (NOT RUN prerequisites remain)'; exit 2 }
Write-Host 'PASS: safe offline validation only; live and recovery evidence remain separate gates.'
exit 0
