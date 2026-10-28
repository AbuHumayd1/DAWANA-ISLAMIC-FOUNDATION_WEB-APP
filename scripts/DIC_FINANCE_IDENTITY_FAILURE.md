# Finance integration identity failure — 25 October 2026

## Confirmed cause and migration state

The failure was in `scripts/validate_dic_finance.py::verify_database()` immediately after `executor.migrate([TARGET], plan=plan)` and before `tests('integration')`.

The old query selected `inet_server_addr()::text`, which includes an inet prefix. Its result was compared literally with `127.0.0.1` / `::1`.

Read-only PostgreSQL inspection of the reported database confirmed:

| Value | Expected | Observed |
|---|---|---|
| Database | `test_dic_finance_20261025223457_c8e898d0` | Matches |
| Server address from old cast | Bare loopback address | `127.0.0.1/32` — fails old string comparison |
| `host(inet_server_addr())` | `127.0.0.1` or `::1` | `127.0.0.1` |
| Server port | 5432 | 5432 |
| Diagnostic transaction mode | Read-only | `on` |

The configured host is `127.0.0.1` and port 5432. The helper resolves process settings before `.env` fallbacks, reads `DATABASE_URL` if present, validates the host, then pins its disposable database and explicit loopback host/hostaddr/port. Django's port setting is a string and was already converted to int in the comparison. The port conversion and database selection were correct; only the address representation failed.

**Migrations were applied before this error.** Read-only migration history shows accounts 1, auth 12, contenttypes 2, dic 26 and dic_finance 1: **42 applied migrations**, including `dic_finance.0001_initial`. `dic.0027_feedback_welfare` is absent. Integration tests were not reached. This database is not empty and must not be resumed as a fresh integration target.

## Narrow correction

- Use PostgreSQL `host(inet_server_addr())` to obtain a bare IPv4/IPv6 address.
- Preserve the exact expected database, exact allowed loopback addresses and exact configured port comparisons.
- Report the failing component with non-secret expected/observed values.
- Invoke the same identity check **before** applying disposable migrations, as well as afterward.
- Correct the same cast in the prepared future development-application documentation.
- Add five standard-library regression tests for valid IPv4/IPv6 and rejection of unexpected/protected databases, remote/missing addresses and wrong ports.

Changed only validation scripts/documentation. No Finance logic, environment file, historical migration or database was changed during diagnosis. Five new identity tests are prepared but **not executed inside Codex**; Python remains restricted here. The developer's earlier 19-policy-test pass is user-reported evidence, not a new run.

## Read-only diagnostic command

Run from repository root in normal VS Code PowerShell. This prints no username, password, key, URL or DSN. It does not run tests or migrations.

```powershell
$financePython = (Resolve-Path -LiteralPath '.\backend\.venv\Scripts\python.exe').Path
@'
import runpy
name = 'test_dic_finance_20261025223457_c8e898d0'
ns = runpy.run_path('scripts/validate_dic_finance.py', run_name='finance_identity_diagnostic')
ns['configure'](name, readonly=True)
from django.db import connection
print('Expected:', {'database': name, 'host': connection.settings_dict['HOST'], 'port': int(connection.settings_dict['PORT'])})
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), inet_server_addr()::text, host(inet_server_addr()), inet_server_port(), current_setting('transaction_read_only')")
    row = cursor.fetchone()
    if row[0] != name or row[4] != 'on':
        raise RuntimeError('Unexpected database or non-read-only connection; stop.')
    print('Observed:', dict(zip(['database','old_cast_address','host_address','server_port','read_only'],row)))
    cursor.execute('SELECT app, count(*) FROM django_migrations GROUP BY app ORDER BY app')
    print('Applied counts:', cursor.fetchall())
    cursor.execute("SELECT app,name FROM django_migrations WHERE app='dic_finance' OR (app='dic' AND name='0027_feedback_welfare')")
    print('Finance / forbidden migration records:', cursor.fetchall())
connection.close()
'@ | & $financePython -B -
if ($LASTEXITCODE -ne 0) { throw 'Read-only diagnosis failed. Stop.' }
```

## Fresh validation attempt — commands for developer execution only

No commands below were executed during diagnosis. Keep the old database for inspection until you decide to clean it up. Do not substitute its name into the fresh run.

```powershell
$ErrorActionPreference = 'Stop'
$financePython = (Resolve-Path -LiteralPath '.\backend\.venv\Scripts\python.exe').Path
$financeRunner = (Resolve-Path -LiteralPath '.\scripts\validate_dic_finance.py').Path

& $financePython -B .\scripts\test_validate_dic_finance_identity.py
if ($LASTEXITCODE -ne 0) { throw 'Identity regression tests failed. Stop.' }

$financeStamp = [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
$financeSuffix = [Guid]::NewGuid().ToString('N').Substring(0,8)
$financeDb = "test_dic_finance_${financeStamp}_${financeSuffix}"
$financeReceipt = Join-Path ([IO.Path]::GetTempPath()) "$financeDb.receipt.json"
if ($financeDb -eq 'test_dic_finance_20261025223457_c8e898d0') { throw 'Existing failed-run database refused.' }
Write-Host "Fresh disposable database: $financeDb"
Write-Host "Receipt: $financeReceipt"

& $financePython -B $financeRunner preflight --database $financeDb
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. Stop before creation.' }
& $financePython -B $financeRunner policy --database $financeDb
if ($LASTEXITCODE -ne 0) { throw 'Policy tests failed. Stop before creation.' }

# Review the printed target plan before this explicit fresh creation step.
& $financePython -B $financeRunner create --database $financeDb --receipt $financeReceipt
if ($LASTEXITCODE -ne 0) { throw 'Fresh creation failed. Do not reuse another database.' }
& $financePython -B $financeRunner integration --database $financeDb --receipt $financeReceipt
if ($LASTEXITCODE -ne 0) { throw 'Integration failed. Retain this run; do not resume it.' }
& $financePython -B $financeRunner verify --database $financeDb --receipt $financeReceipt
if ($LASTEXITCODE -ne 0) { throw 'Final verification failed. Stop.' }
```

Expected, not yet observed: five identity tests, 19 policy tests and four integration tests pass; exact targeted migration set present; 0027 absent.

## Existing failed-run cleanup

The database can be explicitly cleaned up **if its original creation receipt still matches its name, host, port, user, owner, OID and marker**, and it has no active connections. Its applied schema does not prevent cleanup of this marked disposable database. The cleanup action already verifies these conditions and refuses both protected database names. It does not require an empty database, verify a fresh-run schema or resume tests. No cleanup occurred during diagnosis.

Run only when you have finished diagnosis and explicitly want to delete this disposable run:

```powershell
$financeOldDb = 'test_dic_finance_20261025223457_c8e898d0'
$financeOldReceipt = Join-Path ([IO.Path]::GetTempPath()) "$financeOldDb.receipt.json"
if (-not (Test-Path -LiteralPath $financeOldReceipt)) {
    throw 'Original receipt missing. Locate its recorded path; do not fabricate a receipt or guess a target.'
}
if ((Read-Host 'Type the exact failed-run disposable name to approve deletion') -cne $financeOldDb) {
    throw 'Cleanup not approved.'
}
& $financePython -B $financeRunner cleanup --database $financeOldDb --receipt $financeOldReceipt
if ($LASTEXITCODE -ne 0) { throw 'Cleanup refused. Do not force-drop or alter receipt checks.' }
```

If the receipt was originally stored elsewhere, use that exact original path. If the owner/OID/marker changed, stop for manual review. No `DROP ... FORCE`, active-session termination, protected-database changes or development migration is needed to fix this failure.
