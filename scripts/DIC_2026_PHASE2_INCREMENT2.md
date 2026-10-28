# DIC 2026 — Phase 2 Increment 2: assisted booking creation

26 October 2026. **Implemented in source; disabled by default and not operationally accepted.** No migrations were applied, permissions granted, real bookings created, records edited, delivery sent or payment initiated. Existing workspace changes were preserved. Increment 1 and the architecture plan were read; invitations, DOB changes, academic allocation and Phase 3 remain out of scope.

## Local verification update and disposable provisioning

Subsequent user-reported normal PowerShell evidence: Django checks passed, **16/16 policy tests passed**, no model drift, read-only `dawana_dev` identity confirmed at `127.0.0.1:5432`, and exactly `dic_assistance.0001_initial` pending with 0027 excluded. These supersede the earlier pending status for those checks; they were run locally by the user, not executed in Codex. The nine PostgreSQL integration checks remain pending.

New `scripts/provision_dic_assistance.py` reuses the existing Finance isolation/configuration, network guards, receipt ownership checks and connection-identity checks. Actions:

- `create`: safely single-use; generates `test_dic_assistance_<UTC timestamp>_<8 hex>` and `dawana-assistance-validation:<32 hex>`, reserves a new receipt exclusively, creates only that absent database from `template0` on the local server, writes/verifies marker, owner and OID. No existing database is adopted. A failed/partial receipt is retained; choose a new receipt for a fresh attempt after diagnosing the failure.
- `schema`: requires the receipt identity, unchanged migration-file digest and an empty public schema; applies only the exact allowlisted target prerequisites plus `dic_assistance.0001_initial` via MigrationExecutor. No blanket migrate, post_migrate, permission seed/grant, operational data or 0027. A second schema invocation is refused, including after a partial failure.
- `verify`: read-only; verifies receipt marker/owner/OID, local database/server identity, exact applied migration set, absence of postponed tables, existence of assistance table, and reports counts. It permits retained synthetic test fixtures. No cleanup/drop/flush action exists.

All actions force `DIC_ASSISTED_BOOKING_ENABLED=False` only within the script process; configuration files and development permissions are untouched. The configured local role must already have CREATEDB. If it does not, stop and request an approved test facility; do not broaden its privileges as part of this task. The `postgres` maintenance connection is used only for checking and creating/commenting the newly generated database, never for operational table writes. Operational database names cannot be supplied to this script.

**Exact PowerShell sequence from normal VS Code:** do not rerun the already passed policy checks unnecessarily.

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
$env:DIC_ASSISTED_BOOKING_ENABLED = 'False'
$assistanceReceipt = Join-Path (Get-Location) ("output\acceptance\assistance-test-" + [guid]::NewGuid().ToString('N') + '.json')

& .\backend\.venv\Scripts\python.exe -B .\scripts\provision_dic_assistance.py create --receipt $assistanceReceipt
if ($LASTEXITCODE -ne 0) { throw 'Database creation failed; stop and retain receipt.' }

& .\backend\.venv\Scripts\python.exe -B .\scripts\provision_dic_assistance.py schema --receipt $assistanceReceipt
if ($LASTEXITCODE -ne 0) { throw 'Disposable schema failed; stop and retain database.' }

$assistanceTest = Get-Content -LiteralPath $assistanceReceipt -Raw | ConvertFrom-Json
& .\backend\.venv\Scripts\python.exe -B .\scripts\validate_dic_assistance.py integration --database $assistanceTest.database --marker $assistanceTest.marker
$assistanceIntegrationExit = $LASTEXITCODE

# Verify even after a test failure; this is read-only and retains diagnostics.
& .\backend\.venv\Scripts\python.exe -B .\scripts\provision_dic_assistance.py verify --receipt $assistanceReceipt
if ($LASTEXITCODE -ne 0) { throw 'Post-test database verification failed; retain database.' }
if ($assistanceIntegrationExit -ne 0) { throw 'Integration tests failed; retain database for diagnosis.' }
```

Expected integration result: **9 tests, no failures/errors/skips**. TestCase fixtures roll back; the final concurrency probe deliberately retains synthetic rows. No real delivery/provider call occurs. Do not reuse that tested database for another integration run; generate a fresh receipt/database instead. Keep the receipt for later separately authorized cleanup.

Provisioning preparation changed only this report and added `scripts/provision_dic_assistance.py`. Source-level review and whitespace checks were performed. **No provisioning action, database creation, migration or integration test was run in Codex**, where Python remains inaccessible. Runtime provisioning and nine-test success are not claimed.

## Access and integration

Existing page: `/dic/operations/assisted-registration`. Its preparation-only use remains available to active Operations staff. Creation requires all of: authenticated session, active user, `is_staff`, `dic.can_view_dic_operations`, and **`dic_assistance.can_assist_registration`**. Standard Django superuser semantics remain intact; no groups/users are changed or seeded. Session authentication, CSRF and Operations no-store responses are reused.

New configuration `DIC_ASSISTED_BOOKING_ENABLED` defaults to **False**. Until migration and acceptance approval, leave it false: the page remains preparation-only and direct authorized creation returns 503 before storage. Unauthorized requests are still denied. No `.env` file was changed. Eventually enable only after the checks below pass, required delivery works and separately approved officials have the explicit permission. Portal access alone never grants creation.

`GET /api/v1/dic/operations/assisted-registration/` exposes the caller's creation capability. Existing POST there still only validates fields. New **POST `/api/v1/dic/operations/assisted-registration/create/`** accepts exactly `{request_id: UUIDv4, registration: <existing registration payload>}`. Caller-supplied actor, order identity, payment status, fees, exemption or tokens are not accepted.

## Booking creation, audit and duplicate boundaries

New supporting model `dic_assistance.RegistrationAssistance` is the durable creation audit event: UUID, protected initiating staff FK, protected one-to-one existing order FK, protected edition FK, server creation time, globally unique request UUID and keyed payload fingerprint, unique per edition. No participant, registration, payment or fulfillment records are duplicated as supporting data. The model refuses ordinary updates and mismatched order editions; Django Admin exposes audits read-only to active superusers with add/change/delete disabled. Payment lifecycle status remains in the existing order/payment models rather than a competing status machine.

The service reuses `dic.views._create_order` in its existing transaction/pricing/validation path. Current mandatory DOB and all camper fields, category/edition rules, age limits, registration windows, immutable fee snapshots and multiple participants remain intact. Existing public creation source is untouched.

Creation locks edition rows in stable order before inspecting the request or candidate registrations. A same-actor/same-payload retry returns the same assistance receipt without calling order creation again. Different actor or payload on that request returns 409. The internal order key is namespaced, so public idempotency requests cannot replay an officer's key. Transactions and unique constraints protect concurrent retries. A recoverable delivery channel matching the payer's supplied email/phone must be configured before first creation; replay does not need fresh delivery.

Repeated name+DOB entries in one payload and current-edition existing registration candidates with the same case-insensitive trimmed submitted name and DOB are blocked for private payer recovery/authorized identity review. No match is disclosed or automatically merged, edited or claimed. **This is a conservative candidate gate, not universal person identity proof**: spelling changes or inaccurate DOB can evade it, and coincident names/DOB can require review. This increment does not introduce automatic existing-person reuse or an override. Family/shared contacts are not treated as unique people. Retry/double-click protection is stronger and uses the durable request identity, independent of that candidate heuristic.

The mobile form supports multiple campers, plain explicit creation confirmation and clearing private fields. Intake and request references live in memory only. Double submissions reuse the same request/payload; uncertain responses lock editing and offer retry of that exact request. Definite validation rejection permits correction. After saving, private form values are cleared and only the receipt remains. Refresh/navigation loses an uncertain in-memory reference: use payer recovery before trying any new registration. No draft or payer credential is stored in officer local/session storage or URLs.

## Payer-owned handoff

No new bearer link/authentication system is introduced. The response contains assistance reference, creation timestamp, replay marker and generic `/dic/register/recover` path; **no order UUID, order token, OTP, participant payload, Paystack reference or private payment status**. The initial order capability generated internally by the existing service is discarded and replaced with an unshared digest whose expiry is immediate. Administrative revocation is not set, so legitimate recovery remains available.

On the payer's own device, open the approved reachable website's `/dic/register/recover`, privately request/receive the existing contact OTP, list the authorized booking and restore it once, then review pricing and use the existing checkout. The OTP expires after ten minutes; existing recovery grants expire after five minutes, and each grant/order restore is single-use. The assistance UUID is audit identification only and confers no recovery authority. No handoff credential or officer session crosses devices. Existing recovery accepts its established authorized primary/participant contact scopes; no scope expansion is introduced here. Authorized intake staff must accurately enter the real payer/camper contacts—this task does not independently establish documentary identity or contact ownership at intake.

Pending, failed, abandoned or retried payments remain in existing recovery/Paystack flows. No new payment initialization/verification/settlement path exists. Screenshots, redirects and assistance receipts never mark payment successful. Internal enrollments created by the current order service remain **ineligible** until existing trusted-payment checks pass; no QR is issued by assistance. Existing webhook/reconciliation/fulfillment policies are unchanged and were not newly certified by a live provider test.

## Migration lineage and actual status

Prepared `dic_assistance.0001_initial` depends directly on **`dic.0026_house_score_transaction`** and the swappable user model (`accounts.__first__`). Its only schema operation creates **`dic_assistance_registrationassistance`** with its indexes/constraints. It does not alter core models or constraints, and does not depend on, merge, fake or rewrite `dic.0027_feedback_welfare`. Finance/movement/scoring migrations use the same independent-supporting-app pattern. Static dependency inspection supports this lineage; runtime graph/model-state confirmation is still pending.

**Actual current database schema/planning was not verified in Codex.** The configured Python launcher cannot open its base Python313 executable (Access is denied). No PostgreSQL query ran, and no claim is made that a successful source-level plan proves the live schema. The guarded read-only `development-plan` action verifies database/server identity, read-only mode, applied history, required core table columns, absent assistance table and exactly one pending assistance migration. It refuses an applied 0027 or additional pending target prerequisites.

Do not apply anything until preflight, isolated backend tests and the actual development plan pass. The eventual separately approved command would be `python manage.py migrate dic_assistance 0001_initial --settings=config.settings.development` from `backend`, targeting verified `dawana_dev`. It is **not authorized/executed by this report**. A normal Django migration also creates the declared permission/content type via existing post-migrate handling; it does not assign that permission. Do not run blanket migrate. Disabling creation is the first rollback step; do not delete audit associations for bookings already created.

## Focused verification

Executed frontend checks:

- `node --test src/services/assistedRegistration.test.js src/services/operationsRefinement.test.js`: **14 passed**, no failures/skips. Seven assisted checks cover mandatory payload fields, multi-camper whitelisting, stable references, default preparation, permission-capability controls and locked retry rendering; seven existing navigation checks passed.
- Affected-file `oxlint`: passed.
- `npm.cmd run build`: passed, with the existing >500 kB bundle warning. Final small copy changes are included in the final focused rerun.
- Targeted Git whitespace check: passed.

Prepared backend checks, **not executed**:

- **16 policy/preparation checks** (6 new + 10 Increment 1) with DB/network access blocked: independent permission, denied creation before storage, safe response shape, strict input, disabled feature, authorized API actor and existing field validation.
- **9 isolated PostgreSQL checks**: actor/order audit, exact pricing, no premature eligibility/QR/payment, inaccessible anonymous order, replay preserving payer capability, foreign actor/payload conflict, candidate duplicate rejection, multi-camper/public compatibility, atomic validation/channel/authorization failure, assisted-order OTP/restore single use, OTP/grant expiry and concurrent same/new-key requests. Three recovery checks reuse selected existing recovery test methods against assisted orders; they do not run the full recovery suite.

The last concurrency probe commits synthetic fixtures only in an independently marked disposable DB and retains them for inspection; it never flushes. The runner refuses protected DB names, non-loopback connections, wrong owner/marker/history and reused databases containing orders. No DB creation, schema migration, flush or destruction is implemented by the runner. No external provider/delivery is allowed; recovery delivery uses existing test doubles.

Runtime attempt failed before interpreter startup: `Python313\python.exe: Access is denied`. **Zero backend tests executed.** Concurrency, recovery integration, system checks, model/migration drift and actual schema compatibility therefore remain acceptance blockers.

The alternative Windows `py -3.13` launcher was also checked. It discovers the Microsoft Store Python executable but cannot start it (`Access is denied`). Neither available launcher provides a usable runtime inside this execution environment. No runtime, virtual environment or dependency was installed or changed.

### Exact local PowerShell commands

Run these non-provisioning checks in normal VS Code:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
& .\backend\.venv\Scripts\python.exe -B .\scripts\validate_dic_assistance.py preflight
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; stop.' }
& .\backend\.venv\Scripts\python.exe -B .\scripts\validate_dic_assistance.py policy
if ($LASTEXITCODE -ne 0) { throw 'Policy checks failed; stop.' }
& .\backend\.venv\Scripts\python.exe -B .\scripts\validate_dic_assistance.py development-plan --database dawana_dev
if ($LASTEXITCODE -ne 0) { throw 'Read-only development plan failed; stop.' }
```

For integration, first have an approved disposable facility provision a fresh loopback PostgreSQL database named `test_dic_assistance_<14 digit timestamp>_<8 hex characters>`, owned by the configured local role, with exactly the preflight assistance target/prerequisite migrations and no 0027. Set its database comment to a newly generated `dawana-assistance-validation:<32 hex characters>` marker; independently supply that marker to the runner. **Provisioning/migrations are not performed by this task or runner.** Do not point tests at dawana_dev or the protected OTP DB. Once that facility exists:

```powershell
$assistanceTestDatabase = Read-Host 'Approved disposable assistance database name'
$assistanceTestMarker = Read-Host 'Independently verified disposable database comment marker'
& .\backend\.venv\Scripts\python.exe -B .\scripts\validate_dic_assistance.py integration --database $assistanceTestDatabase --marker $assistanceTestMarker
if ($LASTEXITCODE -ne 0) { throw 'Isolated integration failed; retain disposable database for diagnosis.' }
```

## Exact files created/changed in this increment

- `backend/config/settings/base.py`: register supporting app; default-off activation setting.
- `backend/dic/assisted_registration.py`: capability metadata and strictly authorized creation endpoint; preserve preparation.
- `backend/dic/urls.py`: new creation route.
- `backend/dic_assistance/__init__.py`, `apps.py`: supporting application.
- `backend/dic_assistance/models.py`: immutable creation association and explicit permission.
- `backend/dic_assistance/admin.py`: read-only audit inspection; no creation/edit/deletion.
- `backend/dic_assistance/migrations/__init__.py`, `migrations/0001_initial.py`: additive schema, prepared only.
- `backend/dic_assistance/services.py`: transactional creation/replay/candidate-review and safe receipt.
- `backend/dic_assistance/tests.py`: six DB-free policy/API checks.
- `backend/dic_assistance/test_integration.py`: nine disposable integration/concurrency checks including selected recovery coverage.
- `dawana-platform/src/pages/AssistedRegistration.jsx`: permission-gated multi-camper booking/confirmation/retry and payer recovery guidance.
- `dawana-platform/src/services/assistedRegistration.js`: multi-camper booking payload helper.
- `dawana-platform/src/services/assistedRegistration.test.js`: two additional focused checks (seven total).
- `scripts/validate_dic_assistance.py`: guarded preflight, policy, read-only development plan and disposable integration runner.
- `scripts/DIC_2026_PHASE2_INCREMENT2.md`: this report and commands.

## Remaining operational/security gates and browser acceptance

Keep creation disabled until backend checks, marked disposable integration and actual-schema plan pass; then obtain explicit development migration and permission-assignment approval. A working approved recovery provider/worker and reachable HTTPS website must be verified before use. No credentials or security configuration were weakened to bypass these gates.

After isolated acceptance setup, test in separate officer/payer browser profiles: nonstaff and Operations-only denial (including direct POST); authorized officer single/multiple-camper creation with actual server pricing/errors; double-click/network-loss exact-request retry; candidate duplicate rejection without identity disclosure; payer recovery with wrong/expired/reused OTP and grant; one-time restore of the same order; private payer checkout retry/pending/abandonment using test provider doubles; unchanged unpaid admission/QR denial; no officer portal access from the assistance reference; clean private fields on success/unmount; normal phone keyboard, scrolling and hamburger at 360/390 px and desktop. No browser pass or production-readiness claim is made.

Known-person ambiguity remains a deliberate fail-closed review gate, not an implemented merge/reuse workflow. False negatives from changed identity details cannot be eliminated without separately approved identity resolution. There is no unresolved need for a second authentication system. Current blockers are **unexecuted backend/runtime/schema verification, absent approved disposable schema, pending migration/permission approval, and real-browser/delivery acceptance**. No other Phase 2 features were started.
