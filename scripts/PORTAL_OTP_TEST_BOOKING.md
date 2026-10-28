# One isolated unpaid Camper Portal booking

Prepared only. No database creation, migration or fixture insertion has been executed.

Database: `test_dic_portal_2026_local`, on loopback PostgreSQL only. The helper forces
this exact database for every action, refuses non-development settings, retains Gmail
and Fernet values from backend/.env (process values take precedence), and never uses
the local-preview launcher. It does not connect to dawana_dev. Creation refuses an
existing database; fixture insertion refuses nonempty/unrecognised data. Repeated seed
calls return the same booking without modifying it. An advisory transaction lock also
prevents concurrent duplicate seeding.

Schema plan: only prerequisites of `dic.0026_house_score_transaction`, including the
existing participant OTP/check-in tables and auth dependencies. `dic.0027_feedback_welfare`
and `dic_scoring.0001_activity_award` are excluded. No unrestricted migrate or schema
changes on API/worker startup. Inspect the exact names with `plan` before `migrate`.

The existing category FK cannot be omitted from an order item. Therefore only the
isolated fixture creates one INACTIVE category with NULL regular/early-bird prices.
The required numeric item snapshot is zero, explicitly NOT a payable quote. The isolated
edition remains draft with no registration dates; the existing edition/categories/prices
in dawana_dev are untouched. No paid status, payment attempt, price revision, enrollment,
Digital ID, house, check-in or award is created. OTP can verify an unpaid booking; payment
eligibility remains false. House and check-in show unassigned/not checked in. Activity
scoring shows setup pending because its schema is deliberately not installed.

## Commands — run only when ready to approve isolated database changes

From repository root in normal PowerShell (not the agent's restricted Python process):

```powershell
$portalPython = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
$portalDb = 'test_dic_portal_2026_local'

# Explicit database creation; fails if that name already exists.
& $portalPython -B scripts/portal_test_booking.py create-db --confirm-database $portalDb
if ($LASTEXITCODE -ne 0) { throw 'Database creation stopped.' }

# Read-only plan. Review it: no dic.0027 or dic_scoring migration may appear.
& $portalPython -B scripts/portal_test_booking.py plan
if ($LASTEXITCODE -ne 0) { throw 'Migration plan stopped.' }

# Only after reviewing/approving that isolated plan:
& $portalPython -B scripts/portal_test_booking.py migrate --confirm-database $portalDb
if ($LASTEXITCODE -ne 0) { throw 'Isolated migration stopped.' }

# Prompts for authorised email with hidden input unless DIC_PORTAL_TEST_EMAIL is set.
& $portalPython -B scripts/portal_test_booking.py seed --confirm-database $portalDb
if ($LASTEXITCODE -ne 0) { throw 'Fixture loading stopped.' }

# Record the printed booking UUID. Stop the existing port-8000 server manually first.
& $portalPython -B scripts/portal_test_booking.py serve
```

In a second normal PowerShell terminal at the same repository root:

```powershell
$portalPython = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
$portalDb = 'test_dic_portal_2026_local'
while ($true) {
    & $portalPython -B scripts/portal_test_booking.py worker --confirm-database $portalDb
    if ($LASTEXITCODE -ne 0) { throw 'Participant worker stopped.' }
    Start-Sleep -Seconds 5
}
```

Both commands use the same helper and backend/.env: identical database selection and
Fernet/Gmail settings. Avoid conflicting process-level overrides in either terminal.
Restart the API and worker after changing configuration. The worker sends real messages
only to the authorised test contact when requested; it is not run during preparation.

Keep the frontend proxy pointing to port 8000. Visit `/dic/participant`, enter the printed
booking reference and authorised primary email, request the OTP and enter the delivered
code. Confirm one synthetic camper appears, registration is submitted/payment pending,
Digital ID is unavailable, house is unassigned, and paid-only actions remain denied.
Repeat seed with the same email to verify it reports the existing reference, not another
booking. Do not use direct SQL to mark the fixture paid or add fake settlement evidence.

## Validation limitations

Python execution from the agent remains blocked by the existing base-interpreter access
restriction. The helper is prepared for review; no runtime/database acceptance pass is
claimed. No secrets were printed, overwritten or embedded in command arguments.
