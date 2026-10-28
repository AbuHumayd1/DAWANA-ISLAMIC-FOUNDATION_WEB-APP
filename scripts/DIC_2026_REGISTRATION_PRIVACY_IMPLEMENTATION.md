# DIC 2026 Phase 2 — registration privacy implementation

26 October 2026. **Implemented in source; migration prepared, not applied. Backend runtime acceptance is pending.** No operational participant/payment records, credentials, permissions or feature activation changed. No connections were made to the six legacy validation DBs, staging or production. Existing uncommitted work was preserved.

## Behavior

The existing public `/dic/register` form, also used by walk-in campers, offers minor (under 18, DOB required), adult disclosing DOB, and adult withholding exact DOB. Selecting withholding clears DOB from the current form; the payload sends null, never a synthetic date. Adult-with-DOB must be at least 18; minor mode requires an under-18 DOB; future/invalid dates are rejected. Academic status remains independent. Historical exact-DOB clients/drafts remain supported through the default `exact` declaration.

Height and Weight now have the requested optional labels and explanatory text. Either, both or neither can be supplied. UI blank values map to JSON null; the API also accepts omitted/null measurements. Supplied values must retain existing positive minimum (0.01), two-decimal precision and size validation. Blank API strings are rejected; clients must send null/omit them. Zero/nonfinite/negative values are not substitutes for missing data.

New Participant fields: `age_declaration` (`exact`, `minor`, `adult`, default exact) and nullable server-controlled `adult_declared_on`. Withheld DOB requires adult declaration plus its server date; ordinary DOB records have no assertion date. API callers cannot supply the audit date. This is a **self-declaration, not verified documentary age evidence**. Existing full DOB records and measurements are preserved. Database constraints enforce declaration values and valid DOB/assertion nullness; time-dependent age consistency is validated in serializers/model clean rather than a changing current-date database constraint.

The existing order service retains category fees, accepted revisions, multiple campers and trusted payment fulfillment. An adult declaration alone proves no exact age: categories with a finite maximum or a minimum above 18 still require qualifying exact DOB. No pricing or age-limit bypass is introduced. The self-declared adult may choose another eligible existing category or disclose DOB; no category is invented. Private-adult retries fingerprint only stable request data; the server assertion date is not part of client input. Default exact mode is excluded from the fingerprint to preserve legacy exact-DOB request compatibility.

New snapshots and Operations DTOs use real nulls for missing DOB/measurements; historical immutable snapshots are untouched. Legacy exact-mode snapshot shape is retained; explicit adult/minor snapshots additionally record declaration provenance. Review shows disclosed/withheld DOB and missing measurements plainly. Checkout, confirmation and recovery totals use existing order/category data and do not calculate prices from DOB or measurements; their null-safe snapshot/DTO inputs are preserved. Operations participant views remain subject to the existing contact-information permission. Django Admin includes declaration and a read-only server date; model clean validates declarations.

## Age-dependent safety and remaining policy limitation

Exact-age housing/guardian calculations return a controlled ValidationError when DOB is withheld, rather than comparing None or returning a fabricated age. Existing housing allocation and ID housing display handlers convert this to review/pending behavior. No automatic housing or guardian approval is granted from an adult declaration. DOB-free allocation requires a later approved age-evidence/review policy; this increment does not silently infer one. Nullable DOB ordering is deterministic with existing PostgreSQL ascending date ordering and UUID tie-breaker; no guessed birth date is assigned.

Private portal card access may exclude the <=5 dependent branch only for a stored adult declaration dated on/before the applicable housing reference date. Otherwise existing age/review handling remains. This does not grant guardianship, movement departure authorization, house eligibility or new booking scope. Existing trusted-payment ID eligibility and authorized QR issuance remain unchanged; unpaid registrations cannot gain admission or QR from these optional fields. The field merely records self-report, just as the existing public DOB is supplied rather than document-verified; new documentary verification is not claimed.

## Migration and graph

Prepared: `backend/dic/migrations/0028_registration_privacy_measurements.py`.

```text
dependencies = [('dic', '0026_house_score_transaction')]
run_before   = [('dic', '0027_feedback_welfare')]

dic.0001 → … → dic.0026 → dic.0028_registration_privacy_measurements → dic.0027_feedback_welfare
                         Phase 2 target                            deferred Phase 5

dic.0026 → dic_finance.0001_initial
dic.0026 → dic_movement.0001_initial
dic.0026 → dic_scoring.0001_activity_award
dic.0026 → dic_assistance.0001_initial
```

Existing auth/account dependencies are retained (accounts initial, auth through 0012, contenttypes through 0002). Static traversal including installed Django migration source found no cycles, one dic leaf (0027) and a Phase 2 target closure containing dic 0001–0026 plus 0028, excluding 0027. This is **not executed Django MigrationLoader validation**; the guarded preflight below must confirm it locally before any application. Earlier source-only traversal initially lacked installed auth nodes; that check was corrected to include installed Django sources and passed.

The migration alters only Participant DOB/height/weight nullability, adds the two declaration fields and constraints. Existing DOBs/measurements are not rewritten; existing rows receive the descriptive default exact mode. Existing positive-measurement constraints remain. No RunPython/RunSQL/fake, migration rename or core-record backfill is used. `0027_feedback_welfare.py` is untouched; its inspected SHA256 is `269a8935f68dd660c8bf1d82ddcf44c1a574fa0262d4efb06fa9c94292a59aed`.

The six retained validation DBs with 0027 applied must remain on their original code/graph for evidence inspection. No attempt was made to repair or use them. Inserting this prerequisite makes their histories inconsistent with the new graph; do not point new migration/test commands at them. Unverified staging/production are not rollout targets. The existing unrestricted `render-migrate.sh` remains unsuitable while Phase 5 is deferred and was not changed here.

## Checks actually executed

- **11 focused frontend tests passed**, no failures/skips: six new privacy/payload/render checks, three existing registration-control checks and two category-price checks. Cases cover minor/adult DOB, eighteenth birthday, stale DOB omission, all measurement combinations, invalid numeric values, legacy drafts and multi-camper estimates.
- Affected JSX/JS oxlint passed.
- Production build passed; existing >500 kB bundle warning remains.
- Targeted Git whitespace checks passed.
- Source-level graph cycle/leaf/target checks passed as described above.
- Direct **read-only psql** query verified `dawana_dev`, 127.0.0.1:5432, transaction_read_only=on: 0026 and Assistance applied; 0027 and 0028 absent. DOB/height/weight remain NOT NULL; declaration columns are absent. No record data was read or modified.

**Not executed:** backend tests, Django system/model-drift/graph checks, fresh disposable schema setup, and runtime MigrationExecutor development plan. The configured Python invocation for privacy preflight failed before interpreter startup (`Python313\python.exe: Access is denied`). Do not interpret SQL history plus source traversal as an executed Django plan. No test database was provisioned and no migration ran here.

Prepared **19 database-free policy/preparation tests** (9 new privacy + 10 adjusted existing preparation), and **8 PostgreSQL integration checks** (7 new plus the existing public multi-camper pricing/snapshot regression). Coverage includes minors/adults, required DOB, optional measurement combinations, category limits, admin/model validation, controlled housing review, legacy fingerprints, input override rejection, public order roundtrip/replay, multi-camper regular/early-bird pricing, null snapshots/constraints, unchanged earlier snapshots and unpaid QR issuance denial. Tests use synthetic data/provider isolation only. They are not claimed passed until run.

## Exact local verification commands (normal VS Code PowerShell)

The new guarded runner has no deletion/flush action, forces assisted booking off, blocks external provider/delivery calls and refuses protected/legacy database names for write/testing actions. `development-plan` is the sole operational DB action and requires a read-only connection with exactly 0028 pending for its target. `create` generates a fresh `test_dic_privacy_<timestamp>_<8 hex>` database; `schema` requires an empty schema, verified marker/owner/OID receipt and exact allowed prerequisites. It uses MigrationExecutor, not unrestricted migrate/post_migrate. Tests roll back via TestCase transactions. Failed/partial DBs and receipts are retained; do not reuse/reset them. Creation requires already-held local CREATEDB privileges; do not broaden privileges if absent.

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
$env:DIC_ASSISTED_BOOKING_ENABLED = 'False'
$privacyPython = Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
& $privacyPython -B .\scripts\validate_dic_registration_privacy.py preflight
if ($LASTEXITCODE -ne 0) { throw 'Privacy graph/model preflight failed; stop.' }
& $privacyPython -B .\scripts\validate_dic_registration_privacy.py policy
if ($LASTEXITCODE -ne 0) { throw 'Privacy policy checks failed; stop.' }
& $privacyPython -B .\scripts\validate_dic_registration_privacy.py development-plan
if ($LASTEXITCODE -ne 0) { throw 'Read-only development plan failed; stop.' }

$privacyReceipt = Join-Path (Get-Location) ('output\acceptance\privacy-' + [guid]::NewGuid().ToString('N') + '.json')
& $privacyPython -B .\scripts\validate_dic_registration_privacy.py create --receipt $privacyReceipt
if ($LASTEXITCODE -ne 0) { throw 'Fresh disposable creation failed; retain receipt.' }
& $privacyPython -B .\scripts\validate_dic_registration_privacy.py schema --receipt $privacyReceipt
if ($LASTEXITCODE -ne 0) { throw 'Disposable-only schema failed; stop.' }
& $privacyPython -B .\scripts\validate_dic_registration_privacy.py integration --receipt $privacyReceipt
if ($LASTEXITCODE -ne 0) { throw 'Isolated integration failed; retain database for diagnosis.' }
& $privacyPython -B .\scripts\validate_dic_registration_privacy.py verify --receipt $privacyReceipt
if ($LASTEXITCODE -ne 0) { throw 'Read-only disposable verification failed.' }
```

These commands do not apply development migrations. Expected local results: conflict-free graph/model parity, 19 policy checks, read-only target plan exactly 0028, then 8 isolated integration checks and empty retained business tables. Do not use ordinary manage.py test: it may migrate the deferred leaf.

## Eventual development migration approval

Only after local backend checks, actual target-plan verification and browser acceptance on an approved migrated isolated setup: request explicit approval to apply **only** the Phase 2 target to verified dawana_dev. Proposed commands, **not executed or currently approved**:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP\backend"
& .\.venv\Scripts\python.exe manage.py migrate dic 0028_registration_privacy_measurements --plan --settings=config.settings.development
# STOP: inspect target identity and plan; obtain explicit approval before the next command.
& .\.venv\Scripts\python.exe manage.py migrate dic 0028_registration_privacy_measurements --settings=config.settings.development
```

The reviewed default target must be dawana_dev/loopback, exactly one pending dic node, never 0027. Normal Django post_migrate can update content-type/permission definitions for installed apps; it must not be described as zero incidental metadata writes. No automatic permission grants are introduced. Do not reverse nullability once withheld records exist without a separately approved evidence-backed data plan. Deploy source and schema together; **current source requires 0028 and must not be served against the unchanged development schema yet**.

## Exact files changed in this task

1. `backend/dic/models.py`: nullable fields, declaration provenance/constraints/model validation and null-safe new snapshots.
2. `backend/dic/serializers.py`: backward-compatible conditional DOB and optional numeric validation.
3. `backend/dic/views.py`: unchanged shared creation/pricing flow with age-range gate, server declaration date and legacy fingerprint compatibility.
4. `backend/dic/registration_age.py`: exact-age/declaration/category policies; no invented ages.
5. `backend/dic/housing_policy.py`: controlled review when exact DOB is unavailable.
6. `backend/dic/participant_api.py`: scoped private-adult card handling; no guardian/scope expansion.
7. `backend/dic/operations_api.py`: authorized null-safe DTOs and declaration labels.
8. `backend/dic/admin.py`: age declaration and read-only assertion date.
9. `backend/dic/migrations/0028_registration_privacy_measurements.py`: prepared Phase 2 schema and run_before edge.
10. `backend/dic/test_registration_privacy.py`: 9 policy and 7 isolated integration checks.
11. `backend/dic/test_assisted_preparation.py`: current required-field check allows now-optional measurements; no assisted activation.
12. `dawana-platform/src/pages/DIC.jsx`: existing public form integration, validation, payload and review display.
13. `dawana-platform/src/components/dic/RegistrationPrivacyFields.jsx`: age/disclosure choices and optional controls/help.
14. `dawana-platform/src/services/registrationPrivacy.js`: field validation and null-safe payload/summary.
15. `dawana-platform/src/services/registrationPrivacy.test.js`: six focused checks.
16. `dawana-platform/src/pages/Operations.jsx`: protected participant optional-field display.
17. `scripts/validate_dic_registration_privacy.py`: guarded focused testing/provisioning and read-only development planning.
18. `scripts/DIC_2026_REGISTRATION_PRIVACY_IMPLEMENTATION.md`: this evidence and handover.

No new staff registration form was added. Existing dormant assistance UI/infrastructure stays preserved and disabled. Earlier unrelated workspace changes remain outside this task.

## Remaining acceptance

Backend Python execution and fresh PostgreSQL tests, runtime graph/model state, exact read-only development plan, and real browser acceptance remain pending. Test public single/multiple camper entry, toggling disclosure without stale DOB, minor/adult errors, all optional measurements, summary/edit/back/refresh, checkout/recovery/confirmation with synthetic provider responses, permission-protected participant/Admin rendering, housing review messages, keyboard and mobile scrolling/navigation. No real payment or production readiness is claimed. Stop before any development/staging/production migration.
