param(
    [Parameter(Mandatory=$true)][string]$DatabaseName,
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
    [switch]$Apply
)
# Controlled setup equivalent to a management command. Default is read-only.
# Never migrates, creates participants, approves allocation or changes permissions.
$ErrorActionPreference = 'Stop'
$repo = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { (Get-Location).Path }
$configPath = Join-Path $repo 'backend/dic/config/dic_2026_houses.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($config.year -ne 2026 -or $config.houses.Count -ne 8 -or
    @($config.houses | Where-Object gender -eq 'male').Count -ne 4 -or
    @($config.houses | Where-Object gender -eq 'female').Count -ne 4 -or
    @($config.houses.name | Sort-Object -Unique).Count -ne 8) { throw 'Invalid approved house inventory.' }
foreach ($house in $config.houses) {
    if ($house.capacity -ne 30 -or $house.status -ne 'active' -or $house.purpose -ne 'participants' -or
        $house.badge_colour -notmatch '^#[0-9A-Fa-f]{6}$' -or !$house.arabic_name -or !$house.motto) { throw 'Invalid approved house details.' }
}
$psql = Join-Path $PgBin 'psql.exe'
$restore = Join-Path $PgBin 'pg_restore.exe'
$archive = Get-Item -LiteralPath $BackupPath
if ($archive.Length -le 5) { throw 'A nonempty PostgreSQL custom backup is required.' }
$listing = & $restore --list $archive.FullName 2>&1
if ($LASTEXITCODE -ne 0 -or !($listing -match ('dbname:\s*' + [regex]::Escape($DatabaseName) + '\s*$'))) { throw 'Backup listing failed or backup belongs to another database.' }
$discard = & $restore --file=NUL $archive.FullName 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Full backup archive read failed.' }

$settings = @{}
foreach ($line in [IO.File]::ReadAllLines((Join-Path $repo 'backend/.env'))) {
    if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) { $value = $value.Substring(1,$value.Length-2) }
        $settings[$Matches[1]] = $value
    }
}
foreach ($key in @('DATABASE_URL','DB_HOST','DB_PORT','DB_NAME','DB_USER','DB_PASSWORD')) {
    $inherited = [Environment]::GetEnvironmentVariable($key)
    if ($inherited) { $settings[$key] = $inherited }
}
$dbHost = $settings['DB_HOST']; if (!$dbHost) { $dbHost = '127.0.0.1' }
$dbPort = $settings['DB_PORT']; if (!$dbPort) { $dbPort = '5432' }
$dbName = $settings['DB_NAME']; if (!$dbName) { $dbName = 'dawana_dev' }
$dbUser = $settings['DB_USER']; $dbPassword = $settings['DB_PASSWORD']
if ($settings['DATABASE_URL']) {
    $uri = [Uri]$settings['DATABASE_URL']; $dbHost = $uri.Host; $dbPort = $uri.Port
    if ($dbPort -lt 1) { $dbPort = 5432 }
    $dbName = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    $parts = $uri.UserInfo.Split(':',2); $dbUser = [Uri]::UnescapeDataString($parts[0])
    if ($parts.Length -gt 1) { $dbPassword = [Uri]::UnescapeDataString($parts[1]) }
}
if ($dbName -cne $DatabaseName -or $dbHost -notin @('localhost','127.0.0.1','::1')) { throw 'Target must match the explicitly named, configured LOCAL database.' }
$saved = @{}
foreach ($key in @('PGPASSWORD','PGOPTIONS','PGCONNECT_TIMEOUT','PGCLIENTENCODING')) { $saved[$key] = [Environment]::GetEnvironmentVariable($key) }
$oldEncoding = $OutputEncoding
try {
    $env:PGPASSWORD = $dbPassword; $env:PGCONNECT_TIMEOUT = '5'; $env:PGCLIENTENCODING = 'UTF8'
    $env:PGOPTIONS = '-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=5000'
    $OutputEncoding = [Text.UTF8Encoding]::new($false)
    $connectionArgs = @('-X','-w','-h',$dbHost,'-p',"$dbPort",'-d',$dbName,'-v','ON_ERROR_STOP=1','-t','-A','-P','pager=off')
    if ($dbUser) { $connectionArgs += @('-U',$dbUser) }
    function Invoke-CheckedSql([string]$sql) {
        $ErrorActionPreference = 'Continue'
        $result = $sql | & $psql @connectionArgs -f - 2>&1
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -ne 0) { throw 'Database preflight/setup failed. Transaction was not committed; connection details withheld. Inspect existing configuration before retrying.' }
        return ($result | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
    }
    $preflight = Invoke-CheckedSql @'
SELECT json_build_object('edition_id', (SELECT id FROM dic_campedition WHERE year=2026),
 'house_count',(SELECT count(*) FROM dic_house),
 'allocations',(SELECT count(*) FROM dic_houseallocation),
 'migrations',(SELECT json_agg(name ORDER BY name) FROM django_migrations WHERE app='dic' AND name>='0022'),
 'houses',coalesce((SELECT json_agg(json_build_object('id',id,'edition_id',edition_id,'name',name,'capacity',capacity,'colour',badge_colour)) FROM dic_house),'[]'::json));
'@
    Write-Output ('Read-only preflight: ' + $preflight)
    $state = $preflight | ConvertFrom-Json
    if ($state.edition_id -ne 1 -or '0024_house_badge_colour' -notin $state.migrations) { throw 'Expected edition ID 1 and applied colour schema. No changes made.' }
    if (!$Apply) { Write-Output 'Dry run only. No database changes. Review any existing records before explicit -Apply.'; return }
    # Recheck configuration under the same edition lock used by House.save().
    # Insert missing exact matches; never update or delete existing identities.
    $json = ($config.houses | ConvertTo-Json -Depth 4 -Compress).Replace("'", "''")
    $env:PGOPTIONS = '-c statement_timeout=15000 -c lock_timeout=5000'
    $sql = @'
BEGIN;
SELECT id FROM dic_campedition WHERE id=1 AND year=2026 FOR UPDATE;
CREATE TEMP TABLE approved_houses ON COMMIT DROP AS
SELECT *, 'Arabic: ' || arabic_name || E'\nColour: ' || colour_name || E'\nMotto: ' || motto AS notes
FROM jsonb_to_recordset('__CONFIG__'::jsonb) AS h(name text,arabic_name text,colour_name text,badge_colour text,capacity integer,motto text,gender text,purpose text,status text);
DO $setup$
DECLARE created_count integer;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM dic_campedition WHERE id=1 AND year=2026) THEN RAISE EXCEPTION 'Edition conflict'; END IF;
 IF EXISTS(SELECT 1 FROM dic_house WHERE edition_id<>1) THEN RAISE EXCEPTION 'Unexpected existing houses in another edition'; END IF;
 IF EXISTS(SELECT 1 FROM dic_house h LEFT JOIN approved_houses a ON a.name=h.name WHERE h.edition_id=1 AND
 (a.name IS NULL OR h.gender<>a.gender OR h.capacity IS DISTINCT FROM a.capacity OR h.purpose<>a.purpose OR h.status<>a.status OR h.badge_colour<>a.badge_colour OR h.eligibility_notes<>a.notes OR h.eligibility_rules<>'{}'::jsonb OR h.reserve_designation)) THEN RAISE EXCEPTION 'Existing house configuration conflict'; END IF;
 INSERT INTO dic_house(edition_id,name,gender,purpose,capacity,status,badge_colour,eligibility_rules,eligibility_notes,reserve_authorization_reason,reserve_designation,created_at,updated_at)
 SELECT 1,a.name,a.gender,a.purpose,a.capacity,a.status,a.badge_colour,'{}'::jsonb,a.notes,'',false,now(),now() FROM approved_houses a
 WHERE NOT EXISTS(SELECT 1 FROM dic_house h WHERE h.edition_id=1 AND h.name=a.name) ORDER BY a.gender DESC,a.name;
 GET DIAGNOSTICS created_count = ROW_COUNT;
 IF created_count>0 THEN
 INSERT INTO dic_dicadminauditevent(actor_id,action,target_type,target_id,details,created_at)
 VALUES(NULL,'approved_house_configuration_applied','CampEdition','1',jsonb_build_object('created',created_count,'year',2026,'source','dic_2026_houses.json','capacity',240),now());
 END IF;
 IF (SELECT count(*) FROM dic_house WHERE edition_id=1)<>8 OR (SELECT sum(capacity) FROM dic_house WHERE edition_id=1)<>240 THEN RAISE EXCEPTION 'Post-setup inventory validation failed'; END IF;
END $setup$;
SELECT json_build_object('houses',(SELECT json_agg(json_build_object('id',id,'name',name,'gender',gender,'capacity',capacity,'colour',badge_colour) ORDER BY id) FROM dic_house WHERE edition_id=1),'total_capacity',(SELECT sum(capacity) FROM dic_house WHERE edition_id=1),'score_transactions',(SELECT count(*) FROM dic_housescoretransaction WHERE edition_id=1),'allocations',(SELECT count(*) FROM dic_houseallocation WHERE edition_id=1),'setup_audit_events',(SELECT count(*) FROM dic_dicadminauditevent WHERE action='approved_house_configuration_applied' AND target_id='1'));
COMMIT;
'@
    Write-Output (Invoke-CheckedSql ($sql.Replace('__CONFIG__',$json)))
    Write-Output 'Approved house configuration committed. No migration, participant, payment, allocation, score or permission changes.'
} finally {
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key]) }
    $OutputEncoding = $oldEncoding
}
