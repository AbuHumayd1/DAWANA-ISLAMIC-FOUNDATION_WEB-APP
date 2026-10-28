# DIC 2026 — Phase 1 safe backend validation

Date: 25 October 2026. Scope: validation only. The launch-readiness audit was read in full, including its migration and test-runner cautions.

**Result: partially validated; backend runtime validation remains blocked.** The Python failure is an access restriction at the base-interpreter path under the Codex execution identity. Both local database identities and their migration state were verified using read-only PostgreSQL queries. All 137 frontend tests and lint passed again. No backend test started. Source inspection is explicitly distinguished below from executed checks.

Only this report was added. No application files, dependencies, settings, security settings, records or schemas were changed. No database was created, cleared, migrated or dropped. No email worker, OTP request, Paystack transaction or live payment verification was invoked. Existing uncommitted application changes predate this task and were left alone.

## 1. Python execution diagnosis and resolution status

### Observed now

| Check | Actual result |
|---|---|
| `whoami` | `abu-humayd\codexsandboxoffline` |
| `backend/.venv/pyvenv.cfg` | Python 3.13.7, base executable `C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe` |
| Virtual environment launcher | `backend/.venv/Scripts/python.exe` exists, 255,320 bytes; no link target reported |
| Launcher ACL | Owned by `ABU-HUMAYD\hp`; CodexSandboxUsers has Modify/Synchronize; launcher itself is readable |
| Base executable metadata/ACL | `Get-Item` and `Get-Acl` return Access is denied; subsequent path-not-found diagnostics are not proof the executable is missing |
| Virtual environment `--version` | Launcher reports: `did not find executable at 'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.` |
| Existing Python processes | Process paths include the same `.venv/Scripts/python.exe` and user-profile Python313 executable |
| `py -0p` | Launcher lists an installed Microsoft Store Python 3.13 under Program Files/WindowsApps |
| `py -3.13 -B -c ...` | Cannot create the Store Python process: Access is denied |

**Diagnosis:** the environment launcher resolves to the expected base interpreter, but this Codex identity cannot inspect/execute that interpreter. The failure occurs before Django or dependencies load. Existing processes using those same paths support the distinction between the user's usable environment and the restricted Codex process. The Store installation is also inaccessible, so selecting it is not a demonstrated solution.

The exact denying security layer cannot be established from an ACL that Codex cannot read: filesystem/sandbox policy or another Windows execution restriction may be responsible. There is no evidence here of a corrupted virtual environment, a missing package or a Django error. I did not inspect unrelated protected profile directories, copy an executable elsewhere, grant permissions, disable security, reinstall or download Python.

**Resolution status: unresolved inside Codex.** Least disruptive next action is to run the read-only/database-free commands in section 7 in the user's normal PowerShell. The process-path comparison is observed; successful execution under the user's current terminal must still be confirmed by those commands. Do not recreate the environment based on this failure alone.

## 2. Database identities and safeguards

Effective local database selection was derived from process variables taking precedence over `backend/.env`, matching the settings precedence. The parser was used only to obtain connection values in memory; credentials were never printed. The connection was refused unless the configured application database was exactly `dawana_dev` on loopback.

PostgreSQL client: `C:\Program Files\PostgreSQL\18\bin\psql.exe`. Connections used `-X -w`, `ON_ERROR_STOP=1`, a five-second connection timeout and:

```text
PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5000
```

For both connections, SQL reported `transaction_read_only=on`, server address `127.0.0.1`, port `5432` and the expected `current_database()`. Temporary PostgreSQL environment overrides were restored afterward. No private contact data was queried.

| Verified fact | `dawana_dev` | `test_dic_portal_2026_local` |
|---|---|---|
| Purpose | Configured development database; protected | Existing isolated unpaid OTP fixture; also protected |
| Applied DIC migrations | 0001 through 0026 | 0001 through 0026 |
| `dic_scoring.0001_activity_award` | Applied; table present | Not applied; table absent |
| `dic.0027_feedback_welfare` | Not applied | Not applied |
| Feedback response/welfare report tables checked | Absent | Absent |
| DIC 2026 registration | Draft; opening/closing dates NULL | Draft; opening/closing dates NULL |
| Camp end date | 2027-01-01 | 2027-01-01 |
| Bookings / campers | 0 / 0 | 1 / 1 |
| Booking state | None | Submitted; payment pending |
| Allocations / check-ins / house ledger entries | 0 / 0 / 0 | 0 / 0 / 0 |

Queries selected database/server identity, `django_migrations`, `to_regclass(...)`, edition registration fields and aggregate counts/statuses. No records were modified.

### Suitability decision

The existing OTP database is **not a disposable full-suite test database**. It contains an existing booking that must be preserved, and its scoring schema is absent. It can support narrowly scoped read-only checks, but not complete scoring integration or destructive Django test setup/flush.

`base.py` rejects a `DB_TEST_NAME` equal to the application database and otherwise derives a separate test database name. `scripts/portal_test_booking.py` forces `test_dic_portal_2026_local` for the application and `test_dic_portal_2026_runner` as its test name. Neither is authorisation to create that runner database. `--keepdb` prevents dropping a database but does not prevent migration or test cleanup/flush within it.

`scripts/validate_dic_backend.py` explicitly creates a fresh database and uses `DiscoverRunner`, whose normal setup may migrate all installed app heads. Selecting a suite or first inspecting a target plan does not prohibit 0027. It was therefore **not run**.

**Additional isolation is required for database-backed tests.** Stop before creation. A separately approved disposable PostgreSQL database and reviewed runner/migration configuration must exclude 0027 while including the required scoring schema. Do not repurpose, flush or overwrite the existing OTP fixture.

Source verification: `backend/dic_scoring/migrations/0001_activity_award.py` depends exactly on `('dic', '0026_house_score_transaction')`. Its targeted prerequisite chain does not require 0027. No runtime Django migration-plan command succeeded because Python cannot start; applied migration state above was verified directly through read-only SQL instead.

## 3. Commands executed and actual results

| Command/check | Result |
|---|---|
| Read complete `scripts/DIC_2026_LAUNCH_READINESS_AUDIT.md` | Completed; long output read in sections |
| Read `scripts/PORTAL_OTP_TEST_BOOKING.md`, helper, settings, relevant frontend/backend services and tests | Completed; source evidence only |
| `whoami`, `Get-Item`, `Get-Acl`, `.venv/pyvenv.cfg` | Confirms separate Codex identity, readable launcher and inaccessible base executable |
| `Get-Process python*,py` selecting only ID/name/path | Existing processes use the recorded interpreter paths; command arguments/secrets not collected |
| `.\backend\.venv\Scripts\python.exe -B --version` | Failed before Python starts: access denied |
| `py -0p` | Listed Store Python; no installation performed |
| `py -3.13 -B -c "import sys; print(sys.executable); print(sys.version)"` | Failed: access denied creating process |
| `.\backend\.venv\Scripts\python.exe -B backend/manage.py check --settings=config.settings.development` | Failed before Django starts; no system-check result |
| `.\backend\.venv\Scripts\python.exe -B backend/manage.py test dic.test_activity_scoring.ActivityPolicyTests --verbosity 2` | Failed before Django starts; the selected class has 15 source-defined test methods, none executed |
| Read-only `psql` identity/schema/count queries against the two named local databases | Succeeded; results in section 2 |
| `npm.cmd test` from `dawana-platform` | 137 tests passed; 0 failures, 0 skipped; approximately 15.5 seconds |
| `npm.cmd run lint` from `dawana-platform` | Passed, exit 0 |
| `git diff --stat`, targeted `git status` | Inspection only; pre-existing changes left untouched |

No Django `migrate`, `flush`, `createsuperuser`, fixture loader, helper seed/create/worker/serve action, HTTP authentication workflow or provider call was run. No build or visual-browser acceptance was performed in this phase.

## 4. Backend validation coverage and counts

**Backend tests executed: 0. Backend test failures: not measurable; this was an execution blocker, not a passing or failing test run. Django system checks: not executed. Database-backed tests: deliberately not attempted.**

| Area | Source inspected / existing test coverage | Runtime status |
|---|---|---|
| Registration and booking calculations | `dic/models.py`, `views.py`, `tests.py::RegistrationApiTests`, price revision/early-bird gates; frontend registration/estimate tests | Frontend calculations tested; backend calculations not executed |
| Paystack mocked client and settlement | `payments.py`, `payment_views.py`; `tests.py::PaystackClientTests` uses mocked `urlopen` and test credentials; payment API/hardening/return suites | Not executed; no network call |
| Camper authentication and scope | `participant_api.py::authorized_grant/scoped_orders`, challenge/verify/logout, `test_participant_portal.py`, remediation tests | Source only; no OTP sent or grant created |
| House assignment | Allocation/housing services, policy and tests | Source only; no assignment/queue action |
| Scoring invariants | `activity_scoring.py`, catalogue, ledger services; `ActivityPolicyTests`, `HouseScoringTests`, `dic_scoring/tests.py` | Source only; no award/reversal created |
| Digital ID issue/download | Participant eligibility, identity/card/printing services; identity, portal and printing suites | Source only; no ID issued/download workflow invoked |
| Operations permissions | `OperationsSessionPermission`, permission flags, campsite staff gates; Operations/campsite/check-in test classes | Source only on backend; frontend shell/navigation tests pass |
| Reporting consistency | `_verified_payment`, `_verified_order_queryset`, `_report_rows`, report filtering and `_order_data` | Source-confirmed concerns in section 6; no export invoked because exports audit-write |

Scoring source checks retain fixed catalogue values, per-camper service/character caps, prayer exclusions, stable occurrence/task duplicate claims, eligible checked-in participants, documented exemptions, exact fraction thresholds and one-time verified milestones. `ActivityAward` links a single existing house ledger transaction; house totals continue to use the ledger. Original credited-house history and reversal logic exist. These observations are **not** substitutes for database uniqueness/concurrency tests.

## 5. React/Django integration findings

| Concern | Observed implementation | Evidence limit / remaining validation |
|---|---|---|
| API address/proxy | `vite.config.js` proxies `/api`, `/admin`, `/static` to `DJANGO_API_PROXY_TARGET` or `http://127.0.0.1:8000`. API services default to `/api/v1`, with `VITE_API_BASE_URL` override | Same-origin development setup is coherent in source. The running API process's actual settings/database were not proven; no live request was sent |
| Cookies/CSRF | Participant requests use `credentials: include`; POST fetches CSRF and sends `X-CSRFToken`. Portal cookie is HttpOnly, SameSite Lax, scoped to `/api/v1/dic/participant/`. Staff APIs use Django session/CSRF separately | Actual browser cookie acceptance, reverse-proxy HTTPS and origin configuration remain untested. Keep localhost vs 127.0.0.1 usage consistent |
| Cookie path constraint | Participant cookie path is hardcoded to `/api/v1/dic/participant/` | Customising the external API prefix without matching cookie configuration can break authenticated requests; not observed in the default proxy setup |
| Refresh/persistence | Startup `auth/me` restores the server grant; fixed approximately 30-minute portal expiry; no remembered-device implementation. Frontend session markers contain no credentials | Reload/expiry/logout behaviour is covered in mocked frontend tests, not a real Django/browser session |
| Handoff | DIC confirmation supplies validated UUID booking context to `/dic/participant`; OTP remains necessary | Handoff prefill tests pass; no security bypass found through source review |
| Throttling/errors | Shared in-flight startup requests, 60-second non-sensitive channel cache, submission guard, parsed retry time/cooldown and single error presentation | Regression tests pass. Server throttles unchanged. Cross-worker production enforcement still depends on cache/proxy deployment |
| Payment confirmation | Return UI consumes server payment state; verification/return/webhook services check provider evidence, not redirect query claims | Pending/failure/unavailable states exist. Settlement and replay handling need database-backed tests. Paystack code remains test-only |
| ID eligibility/download | Profile requires eligible current issue; card URLs use the existing participant endpoint and supported formats. Server checks grant scope, paid/source eligibility and dependent relationships | Unpaid fixture cannot prove successful issue/download. No camper self-issue action should be added |
| Camper selection/data isolation | Selected registration item scopes scoring; selection changes invalidate/abort stale requests; own-house ranking differs from overall house totals | Relevant frontend tests pass; unrelated-booking rejection still needs backend execution |
| Operations accuracy | Existing permissions gate API domains; overview/registration/payment/report data derive from existing records | Specific status/report inconsistencies remain, below. No live staff session/API acceptance claimed |

`backend/.env` is loaded by `base.py` through django-environ; existing process variables take precedence. API and worker must start with the same settings module, isolated database and Fernet/Gmail values. This phase did not start/restart either process or inspect their secret environment blocks. An idle worker or available-channel response does not demonstrate delivery. Real email is explicitly outside this validation run.

## 6. Reporting and Operations inconsistencies retained for approval

These are source-confirmed and **not fixed**, because the task requires separate approval before application changes:

1. `operations_api.py::_verified_payment` and `_verified_order_queryset` mean confirmed + paid + at least one successful attempt. `participant_services.py::eligibility` checks stronger source/payment evidence, accepted pricing, verification metadata and reconciliation. A displayed “verified” label can imply different guarantees across screens.
2. `_report_rows('payments', ...)` evaluates `_verified_payment(attempt.order)` for each attempt. A failed attempt on an otherwise paid order can display “Verified paid: Yes”. This is order-level information in an attempt-level report and must not be used as receipt totals.
3. Participant reports select the first edition registration item, rather than consistently using reviewed source resolution. Multiple booking sources need an explicit tested policy.
4. `_order_data` includes active allocations across editions in each participant's list. This is labelled with edition years, but it is not strictly the current order edition's house assignment; screens need clear scope or filtering.
5. Category/house report branches ignore shared date/order filters; payment dates use attempt creation. Filter semantics are not consistent across report types.
6. `campsite_api.py` sets attendance to `None` and says camp check-in is not implemented, despite the existing check-in service. The overview explanation is stale; it is not proof that the check-in endpoint is missing.

No paid local records exist in either inspected database, so these were not reproduced against actual paid data. There is no evidence from this phase of lost money or duplicate ledger posting.

## 7. Exact manual PowerShell commands

Run from repository root in the user's **normal PowerShell**, not through a newly elevated/security-modified terminal. These commands do not create databases or apply migrations.

### A. Confirm the working interpreter

```powershell
$phasePython = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
whoami
& $phasePython -B -c 'import sys; print(sys.executable); print(sys._base_executable); print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'Interpreter still blocked. Stop; do not reinstall or change ACLs.' }
```

Compare `sys._base_executable` with the recorded Python313 path. Share only identity/path/version and redacted test summaries; do not share `.env` contents or debug dumps.

### B. Read-only Django check and targeted migration-plan inspection

This uses the existing helper's `configure()` only, not its `main()` or write actions. It forces the existing isolated database, checks its identity and refuses non-development settings. `MigrationExecutor` below only reads plans; it never executes them. The plan for scoring is informational, not approval to migrate the OTP fixture.

```powershell
$phaseOldPgOptions = $env:PGOPTIONS
try {
    $env:PGOPTIONS = '-c default_transaction_read_only=on -c statement_timeout=5000'
    @'
import runpy
ns = runpy.run_path('scripts/portal_test_booking.py', run_name='phase1_inspection')
ns['configure']()
from django.conf import settings
from django.db import connection
from django.core.management import call_command
from django.db.migrations.executor import MigrationExecutor
assert settings.SETTINGS_MODULE == 'config.settings.development' and settings.DEBUG
assert connection.settings_dict['NAME'] == 'test_dic_portal_2026_local'
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_setting('transaction_read_only')")
    identity = cursor.fetchone()
assert identity == ('test_dic_portal_2026_local', 'on'), identity
print('Confirmed isolated database; read-only connection.')
call_command('check', verbosity=1)
executor = MigrationExecutor(connection)
applied = executor.loader.applied_migrations
assert ('dic', '0027_feedback_welfare') not in applied
for target in [('dic', '0026_house_score_transaction'), ('dic_scoring', '0001_activity_award')]:
    plan = executor.migration_plan([target])
    assert not any(backwards for _, backwards in plan)
    assert all((migration.app_label, migration.name) != ('dic', '0027_feedback_welfare') for migration, _ in plan)
    print('Read-only target:', '.'.join(target))
    print('Pending:', [migration.app_label + '.' + migration.name for migration, _ in plan])
connection.close()
'@ | & $phasePython -B -
    if ($LASTEXITCODE -ne 0) { throw 'Read-only Django validation failed; stop here.' }
} finally {
    $env:PGOPTIONS = $phaseOldPgOptions
}
```

### C. Database-free backend tests only

This explicit allowlist uses `unittest` rather than Django database setup. It refuses any discovered test that is not a database-free `SimpleTestCase`, blocks network connections during the run and uses in-memory email. No database-backed suite, test database creation or migration is requested. This command has been source-reviewed but **not executed here**; its eventual count/result must be recorded from normal PowerShell.

```powershell
@'
import runpy, socket, sys, unittest
from unittest.mock import patch
ns = runpy.run_path('scripts/portal_test_booking.py', run_name='phase1_unit_tests')
ns['configure']()
from django.test import SimpleTestCase, override_settings
from django.test.runner import iter_test_cases
from django.test.utils import setup_test_environment, teardown_test_environment
labels = [
    'dic.test_activity_scoring.ActivityPolicyTests',
    'dic.test_scoring.HouseScoringTests',
    'dic.test_checkin.CampCheckInTests',
    'dic.test_campsite_foundation.CampsiteFoundationTests',
    'dic.tests.PaystackClientTests',
]
def deny_network(*args, **kwargs):
    raise RuntimeError('Network disabled for Phase 1 database-free tests')
with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                       DIC_EMAIL_RECOVERY_ENABLED=False,
                       DIC_RECOVERY_DELIVERY_WORKER_ENABLED=False):
    with patch.object(socket.socket, 'connect', deny_network), \
         patch.object(socket, 'create_connection', deny_network):
        setup_test_environment()
        try:
            suite = unittest.defaultTestLoader.loadTestsFromNames(labels)
            tests = list(iter_test_cases(suite))
            assert tests and all(isinstance(test, SimpleTestCase) and not test.databases for test in tests), 'Non-database-free test or import error; stopped.'
            print('Database-free tests discovered:', len(tests))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            teardown_test_environment()
sys.exit(0 if result.wasSuccessful() else 1)
'@ | & $phasePython -B -
if ($LASTEXITCODE -ne 0) { throw 'Database-free tests failed or were blocked. Retain the output for review.' }
```

No `manage.py test` command for database-backed classes is supplied yet: without a reviewed constrained runner it could create/reuse a database, migrate 0027 or flush existing data. Do not run `create-db`, `seed`, `migrate`, `worker`, unrestricted tests or `--keepdb` as a workaround.

Frontend reproduction, separately:

```powershell
Push-Location .\dawana-platform
try {
    npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    npm.cmd run lint
    if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed.' }
} finally { Pop-Location }
```

## 8. Remaining blockers and exact recommended next phase

1. Codex cannot execute either identified Python installation. Run section 7 in normal PowerShell and retain actual results. No installation/security change is currently justified.
2. Full backend validation requires **additional approved disposable isolation**. Preserve `test_dic_portal_2026_local` and its existing unpaid booking. Review a dedicated database name, migration targets including scoring but excluding 0027, no-email/no-provider-network controls and concurrency-test requirements before any creation. Stop at that approval boundary.
3. Backend system checks, actual ORM/payment settlement, auth, permissions, allocations, scoring concurrency and ID issuance/download remain unverified until those execution/isolation blockers are cleared.
4. Browser-to-Django session/cookie/CSRF/refresh and authenticated portal acceptance remain unverified. Real Gmail delivery is outside the present no-email constraint.
5. The six reported accuracy issues remain unchanged and need separately approved narrow fixes with regression coverage; this report does not authorise Reporting implementation.

**Recommended next phase: Phase 1B — complete constrained backend and browser validation, not new features.** First obtain the normal-PowerShell read-only/database-free results. Then approve the disposable test database and constrained test runner before running registration/payment mocks, booking-isolation/permission tests, allocation/check-in/scoring invariants and ID lifecycle tests. Only after evidence is available should narrow accuracy fixes be approved individually. Finance, comprehensive Reporting, Feedback, Certificates, Games and live-payment implementation remain outside this phase.

Validation stopped at the Python/isolation boundaries. No automatic database creation or application fix follows this report.
