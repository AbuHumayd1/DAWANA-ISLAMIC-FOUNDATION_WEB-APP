# DIC 2026 movement runtime verification and migration approval gate

26 October 2026. **Blocked before Django execution. Development migration is not approved or applied.** No frontend tests, application-feature work, database connections, disposable provisioning, migrations or staff grants were performed in this task.

## 1. Runtime findings

- Intended project executable: `backend\.venv\Scripts\python.exe`. The existing `start-local-preview.ps1` defaults to it; no alternate interpreter is pinned in `.vscode/settings.json`.
- `backend/.venv/pyvenv.cfg` records Python **3.13.7**, based at `C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe`. The project venv launcher exists.
- Invoking that venv fails before Python starts: `did not find executable ... Python313\python.exe: Access is denied.` Direct file inspection of the base executable also raises UnauthorizedAccessException. This does not prove the environment is corrupt or missing; Codex cannot distinguish the denying Windows/sandbox layer.
- `C:\Windows\py.exe -0p` separately discovers Microsoft Store Python 3.13 at `C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe`. A version probe through `py -3.13` also fails with Access is denied. It is not a verified substitute for the project venv/dependencies.
- Installed venv metadata exists for Django 5.2.18, DRF 3.18.3, django-environ 0.14.0, psycopg 3.3.6, cryptography 46.0.7, qrcode 8.2, Pillow 12.3.0 and boto3 1.43.118. Metadata presence is not a successful import check. `backend/requirements.txt` remains unchanged.
- Development settings are `config.settings.development`; `manage.py` defaults to them. No Python installation, venv, dependency, credential, execution policy or filesystem permission was changed.

## 2. Actual verification status

| Check | Result |
| --- | --- |
| Project Python/dependency import probe | Failed before Python started. |
| Movement preflight invocation | Failed before Python started; no Django system check executed. |
| Complete Django migration graph/model parity | Not executed. Validator now prints the full installed file graph/leaves, direct dependency assertion and drift labels when runnable. |
| Movement dependency source inspection | Prepared movement 0001 directly depends on dic 0026 and swappable user; earlier static dependency traversal excludes dic 0027. This is not runtime graph evidence. |
| 16 database-free movement policy tests | Not executed. |
| Five disposable PostgreSQL movement integration tests | Not executed; no disposable database created or contacted. |
| Development migration | Not applied; approval gate remains closed. |

The complete installed graph is expected to **contain** postponed dic 0027 as a leaf. The safety assertion is that the **movement target's prerequisite plan excludes it**, not that the installed graph hides it. No historical migration was edited. A normal broad `migrate` or standard test-database runner could include that leaf and must not be used here.

## 3. Normal VS Code PowerShell: runtime, graph and policy

Run at the repository root in normal VS Code PowerShell, where the backend previously ran. Stop on any error. These commands do not provision or connect to an application database:

```powershell
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
$movementPython = (Resolve-Path -LiteralPath '.\backend\.venv\Scripts\python.exe').Path
& $movementPython -B -c 'import sys; import django, rest_framework, environ, psycopg, cryptography, qrcode, PIL, boto3; print(sys.executable); print(sys.version); print("Django", django.get_version())'
if ($LASTEXITCODE -ne 0) { throw 'Runtime/import check failed. Stop; do not reinstall or replace the venv automatically.' }

& $movementPython -B .\scripts\validate_dic_movement.py preflight
if ($LASTEXITCODE -ne 0) { throw 'Django/graph/model preflight failed. No provisioning or migration allowed.' }

& $movementPython -B .\scripts\validate_dic_movement.py policy
if ($LASTEXITCODE -ne 0) { throw 'Movement policy tests failed. Stop before database provisioning.' }
```

Expected, **not yet observed**: executable/import success, Django system checks pass, direct dependencies exactly dic 0026 plus accounts first, movement model parity, movement prerequisite plan excluding 0027, and **16 policy tests passed without skips**. Full-graph and other-app drift labels are printed for review; do not automatically generate migrations to resolve unrelated drift. If normal VS Code also denies the interpreter, stop and identify the existing working interpreter from the backend's actual terminal/VS Code interpreter selection. Do not blindly switch to the registered Store Python or install dependencies again.

## 4. Disposable PostgreSQL provisioning and integration only

Added `scripts/provision_dic_movement_test.py` because the prepared integration runner required an already provisioned test schema. This is verification tooling, not a new product feature. **Its Python execution has not been validated here.** It reuses the established Finance helper's synthetic configuration, loopback/network guards and owner/OID/comment receipt checks. It accepts only `test_dic_movement_<UTC timestamp>_<random hex>` names, refuses existing databases, checks the exact target dependency allowlist and model parity, fingerprints migration files, and refuses a nonempty database before targeted schema application. It never changes PostgreSQL roles/grants, runs post_migrate or accepts `dawana_dev`/the protected OTP database. No development action or unrestricted migrate action exists.

After section 3 passes, inspect the printed plan and the new helper. Run in the same PowerShell session:

```powershell
$movementStamp = [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
$movementSuffix = [Guid]::NewGuid().ToString('N').Substring(0,8)
$movementDatabase = "test_dic_movement_${movementStamp}_${movementSuffix}"
$movementReceipt = Join-Path ([IO.Path]::GetTempPath()) "$movementDatabase.receipt.json"
if (Test-Path -LiteralPath $movementReceipt) { throw 'Receipt already exists; use a fresh run.' }
Write-Host "Disposable target: $movementDatabase"
Write-Host "Receipt: $movementReceipt"

& $movementPython -B .\scripts\provision_dic_movement_test.py create --database $movementDatabase --receipt $movementReceipt
if ($LASTEXITCODE -ne 0) { throw 'Disposable creation failed; do not substitute a protected or existing database.' }

& $movementPython -B .\scripts\provision_dic_movement_test.py schema --database $movementDatabase --receipt $movementReceipt
if ($LASTEXITCODE -ne 0) { throw 'Targeted disposable schema failed. Retain database/receipt; do not clear or reuse it.' }

& $movementPython -B .\scripts\provision_dic_movement_test.py verify --database $movementDatabase --receipt $movementReceipt
if ($LASTEXITCODE -ne 0) { throw 'Disposable identity/schema verification failed.' }
$movementMarker = (Get-Content -Raw -LiteralPath $movementReceipt | ConvertFrom-Json).marker

& $movementPython -B .\scripts\validate_dic_movement.py integration --database $movementDatabase --marker $movementMarker
if ($LASTEXITCODE -ne 0) { throw 'Movement integration tests failed. Retain isolated evidence; no development migration.' }

& $movementPython -B .\scripts\provision_dic_movement_test.py verify --database $movementDatabase --receipt $movementReceipt
if ($LASTEXITCODE -ne 0) { throw 'Post-test schema verification failed.' }
```

Expected, **not yet observed**: one newly owned/marked disposable database; exact target prerequisites and movement 0001 only; no dic 0027/welfare tables; **five integration tests passed without skips**; unchanged migration set afterward. Synthetic users/registrations/IDs/check-in/movements exist only within disposable TestCase transactions. These tests mock settlement eligibility to isolate movement persistence and do not certify payment verification or full concurrent/browser behavior.

The configured local role must already have CREATEDB. If it does not, the helper stops with `Local configured role lacks CREATEDB`; request an approved disposable facility from its owner rather than granting privileges or switching to development. The integration runner requires the exact marked schema/ownership and prerequisite migration set. A creation/receipt failure is a stop condition; retain the exact name for owner review. There is no automatic drop/cleanup or forced disconnect. Do not run `manage.py test`, `flush`, `loaddata`, `--keepdb` or unrestricted migrate as substitutes.

## 5. Read-only development plan, after successful isolated checks

This block opens only the known local `dawana_dev` connection in read-only mode, prints applied migration history and verifies that the pending target plan is exactly one movement node. It does **not apply** anything:

```powershell
@'
from contextlib import ExitStack
import importlib.util
from pathlib import Path
path = Path('scripts/validate_dic_finance.py').resolve()
spec = importlib.util.spec_from_file_location('movement_readonly_plan', path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
credentials = helper.configure('dawana_dev', readonly=True)
with ExitStack() as stack:
    helper.guards(stack, credentials)
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    helper.verify_connection_identity('dawana_dev', connection)
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), current_setting(%s)', ['transaction_read_only'])
        assert cursor.fetchone() == ('dawana_dev', 'on')
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    assert ('dic', '0027_feedback_welfare') not in executor.loader.applied_migrations
    print('Applied history:', sorted(executor.loader.applied_migrations))
    plan = executor.migration_plan([('dic_movement', '0001_initial')])
    names = [(migration.app_label, migration.name, backwards) for migration, backwards in plan]
    print('Pending target plan:', names)
    assert names == [('dic_movement', '0001_initial', False)], 'Unexpected plan: stop.'
    connection.close()
print('READ-ONLY PLAN PASSED. No migration applied.')
'@ | & $movementPython -B -
if ($LASTEXITCODE -ne 0) { throw 'Development plan not as expected. Stop without applying anything.' }
```

Preserve this output and the isolated test outputs for approval. This read-only plan has **not** been executed here.

### Approval gate — closed

Only if runtime checks, policy/integration tests and the read-only development plan pass may the following exact target command be proposed for approval:

```text
& $movementPython -B .\backend\manage.py migrate dic_movement 0001_initial --database default --settings=config.settings.development --noinput
```

**Do not execute it yet.** Intended database: local `dawana_dev`, verified from the same management-command configuration immediately before application. The read-only helper explicitly selects development; do not assume that a separate terminal's default database overrides match it. Retain existing approved connection credentials, independently confirm its default database is `dawana_dev`, and recheck the one-node target plan in that actual application environment before seeking approval.

Expected new application table: **`dic_movement_movement`**, with PostgreSQL indexes/constraints for UUID identity, participant/edition sequence, idempotent request, type and departure authorization reference. `django_migrations` receives the applied node. Normal Django `migrate` also runs post_migrate handlers: content-type/permission definitions may be created for installed apps (potentially including other unapplied model definitions); that is **not** an automatic user/group grant, and must not be described as zero additional database writes. The disposable schema helper deliberately avoids those handlers. No unrelated **schema migrations** should run if the approved plan contains exactly the single movement node; dic 0027 must remain unapplied.

The command above is prepared information, **not an approved execution instruction**. Since tests have not run, no development application recommendation is issued yet. No rollback is assumed harmless once movement history exists; agree backup/recovery arrangements before approval.

## 6. Minimum permission assignments — instructions only

Use active ordinary staff accounts with `is_superuser=False`. In existing Django Admin `/admin/`, an authorized administrator can create narrowly scoped groups and assign selected officials through their existing UserAdmin groups field. Select only the explicit permissions below; do not select every `dic` or `dic_movement` permission. No accounts/grants were changed by this task.

| Suggested operational group | Explicit permissions in addition to active staff |
| --- | --- |
| Movement viewers | `dic.can_view_dic_operations`, `dic_movement.can_view_movements` |
| Arrival officers | `dic.can_view_dic_operations`, `dic.can_check_in_dic_participants`; add `dic.can_view_dic_ids` for QR scanning |
| Return recorders | Operations + `dic_movement.can_view_movements` + `dic_movement.can_record_movements`; add ID view for QR scanning |
| Designated release officers | Return-recorder permissions + **`dic_movement.can_authorize_departure`**; add ID view for QR scanning |

Movement recording permission alone does not authorize departures. Every departure additionally requires the release permission, explicit confirmation/authorization checkbox and reference to checked external release evidence. The current Phase 1 policy requires this for all campers. It is an external-authorization attestation by the release officer, not a two-officer in-app approval chain or automatic validation of guardianship/collection documents.

Movement view does not grant recording. Recording through these endpoints also requires movement view. Initial arrival uses the existing check-in permission/service and does not require movement recording. Generic audit-log access is optional and separate; its movement events additionally require movement view. No Finance, ID-management, source-review or unrelated permissions are needed for these operational groups.

Django superusers inherently pass `has_perm()` checks, including departure authority; do not use shared superuser accounts as camp operational roles. Creating a group as a superuser does not give the group superuser rights. If organizational policy must deny operational departures even to superusers, that would require an explicit separately approved policy change; it is not silently implemented here. After approved grants, use a fresh login and verify the direct-API role matrix in isolation. Permission definitions need to exist after the separately approved schema/permission setup before Admin can assign them.

## 7. Changes in this verification task and remaining blockers

Files changed:

1. `scripts/validate_dic_movement.py`: print complete migration file graph/leaves, assert exact direct prerequisites and report drift labels. No schema action added.
2. `scripts/provision_dic_movement_test.py`: new guarded disposable-only creation/target-schema/verification helper. Prepared but not executed; no development path or role grants.
3. `scripts/DIC_2026_MOVEMENT_RUNTIME_VERIFICATION.md`: this status, commands and approval gate.
4. `scripts/DIC_2026_QR_MOVEMENT_PHASE1.md`: link to this follow-up procedure.

Remaining blockers are exact: Codex cannot launch either discovered Python runtime; therefore Django checks/runtime graph/model parity and all 21 prepared backend tests remain unexecuted. PostgreSQL connectivity/CREATEDB entitlement, disposable helper execution and schema application have not been tested. Normal VS Code execution/output is required to resolve those gates. No new application defect has been established by these blocked commands. Real smartphone/HTTP permission/concurrency acceptance and prior routing reachability remain subsequent operational gates; frontend checks were not repeated.
