# Stage 1 security and validation remediation

Status: implemented in source; backend execution, PDF visual QA and browser
acceptance remain blocked/pending. Stage 1 is not signed off. No Stage 2 work.

## Root cause and compatibility decision

The participant enrollment POST called `id_command(..., 'issue')` without an actor.
The service permitted actorless issue operations, and the model generated a QR
automatically on insertion. Together these allowed a verified paid booking to
self-issue through the API despite the frontend hiding that action.

The shared service now requires an authenticated, active staff actor with
`dic.can_manage_dic_ids` for issue, reissue and revoke. Payment/source eligibility,
locking, idempotence, reasons and expiry checks remain. New credential generation
occurs in authorized issuance only. A model insertion must receive an explicit
authorized actor, match that actor to issued_by, contain the service-prepared
credential and pass payment eligibility. Model saves no longer mint QR tokens.
Existing identity/version/expiry fields are immutable; token replacement requires
reissue; eligible legacy activation requires staff authority; revocation is
permanent and requires the responsible actor. Source-review staff retain their
existing permission to invalidate IDs during authorized source/restriction review.
These application guards do not replace trusted database-administrator controls;
raw SQL and bulk ORM writes are not participant-facing issuance interfaces.

Compatibility conflict: older participant tests and clients expected self-issuance
from POST participant/enrollments. That conflicts with the explicitly approved
staff-only policy. The safest retained interface is enrollment preparation only:
the ordinary POST remains available but creates no ID issue and no QR, while
requests containing action/operation are denied. Existing issues, payment status,
download scope, and guardian authorization remain unchanged. Operations and Admin
use the same staff command, including explicit legacy activation. Former self-issue
test flows now prepare first and use an authorized staff actor separately.

## Print-history design: no schema migration

New export audit details retain all original fields and add:

```json
{"cards": [{"enrollment_id": "uuid", "issue_id": "uuid", "version": 2,
            "participant_number": "existing participant number"}]}
```

Only identifiers and version metadata are included, never raw QR values, digests,
encrypted QR secrets or authentication credentials. Physical-print confirmation
copies the export snapshot, even when a replacement has since been issued.
Directory exported/printed flags match the CURRENT issue UUID. Previous badge
history is shown separately. Legacy audit JSON is not rewritten or inferred from
timestamps: its version remains unknown, and it cannot mark a current ID printed.
Reprints create another export; repeated print confirmation remains idempotent.
The existing immutable audit model supports this design; no new schema is proposed.

## Validation corrections and regression coverage

- Module/class/method test selection now uses a boundary-aware label matcher.
  Missing or skipped required labels still fail; a database-free standard-library
  test file covers these cases. ID runs include participant portal/remediation tests.
- Cutting guides are checked as standalone stroked paths against each expected
  corner coordinate and 1–2.5 mm extent, excluding rounded-panel paths.
- The house-colour fixture has capacity 25 and the participant's correct house sex.
- The download fixture sets the housing reference date required for scoped access.
- Added service/model denial cases (actorless, non-staff, missing permission,
  inactive); portal/guardian booking-scope preparation without issuance, including
  a coexisting staff session; successful staff API issue/reissue/revoke without
  secret leakage; late print confirmation after reissue; unversioned history;
  and missing PDF dependency handling. Existing concurrency and ID lifecycle
  tests now use authorized staff actors, preserving their original invariants.

## Dependencies and startup

Production requirements already declare ReportLab, qrcode and Pillow. ID test
requirements declare pypdf, PyMuPDF, OpenCV and now explicitly NumPy. ReportLab is
loaded lazily during PDF generation, so its absence no longer breaks unrelated
Django URL imports or the directory. PDF requests return a sanitized HTTP 503;
failed exports create no audit event. Focused validation checks all PDF/test
imports before creating a database. No dependency installation was performed here.

Python diagnosis remains an access restriction in the Codex context: the existing
venv launcher cannot access its configured user-profile base interpreter. This
does not establish a broken venv or Python installation. No interpreter, Windows
permission, system setting or global Python configuration was changed.

## Migration inspection and approvals

Reviewed chain: 0024 -> 0023 -> 0022 -> 0021 (0022 also depends on the user model).
0022 creates housing/guardian tables and constraints, adds housing policy fields,
and updates the DIC 2026 reference date and reserve-house designation flags.
0023 adds the private portrait and nullable QR digest/encrypted-secret fields.
0024 adds the optional house badge colour. 0024 alone is additive, but a full
pending-chain deployment includes the earlier data operation and constraints.
Actual applied status is UNKNOWN: no database was connected to during this task.
No migration was created, edited or applied by this remediation.

Approval is still required before creating any isolated validation/demo database
and applying its test schema, or applying pending migrations to development.
No real credentials, participant records, registration payments or eligibility
evidence were changed. Existing Git changes were preserved.

## Files changed by this remediation

- backend/dic/models.py, participant_services.py, participant_api.py, identity_cards.py
- backend/dic/portrait_pdf.py, identity_views.py, printing_api.py
- backend/dic/test_id_printing.py, test_participant_portal.py, test_participant_remediation.py
- backend/requirements-test-ids.txt, ID_PRINTING_STAGE1.md, this report
- scripts/validate_dic_backend.py, validate-dic-backend.ps1, test_validation_helpers.py (new)
- dawana-platform/src/pages/ParticipantIDPrinting.jsx

## Checks actually executed

- Frontend service tests: 64 passed, 0 failed.
- Frontend production build: passed.
- Frontend oxlint: passed.
- git diff --check: passed (line-ending notices only).
- Python interpreter probe: blocked with access denied to the configured base
  executable. No Python tests or Django checks were executed.
- Backend regressions, migration parity/SQL, generated PDF geometry/decoding,
  visual inspection, browser acceptance and physical printing remain unexecuted.

## Exact PowerShell commands

From the existing activated environment, at the repository root:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
python -I -B -c "import sys; print(sys.executable); print(sys.prefix); print(sys.base_prefix)"
python -B -c "import django, reportlab, qrcode, pypdf, fitz, cv2, numpy; print('Imports OK')"
python -m pip check
python -B scripts\test_validation_helpers.py
```

If imports are missing, install declared project packages in the EXISTING venv
only (no Python reinstall, venv recreation or global configuration changes):

```powershell
python -c "import sys; assert sys.prefix != sys.base_prefix, 'Activate the existing project venv first'"
if ($LASTEXITCODE -ne 0) { throw 'Existing virtual environment required' }
python -m pip install -r backend\requirements-test-ids.txt
```

Read-only checks (the migration-plan/SQL commands read the configured database):

```powershell
python -B backend\manage.py check
python -B backend\manage.py makemigrations --check --dry-run
python -B backend\manage.py showmigrations dic --plan
python -B backend\manage.py sqlmigrate dic 0022
python -B backend\manage.py sqlmigrate dic 0023
python -B backend\manage.py sqlmigrate dic 0024
```

ONLY AFTER APPROVAL for uniquely named local test databases and their schema
migrations, run the existing guarded workflow (databases retained, not dropped):

```powershell
python -B scripts\validate_dic_backend.py --ids-only
python -B scripts\validate_dic_backend.py --phase2-and3
```

Do not substitute a default `manage.py test` run, which may use an existing test
database name. Inspect validation-results JSON and redacted logs for full execution.
The ID suite now includes registration and participant portal security regressions.

For a fresh isolated browser/PDF demo, also ONLY AFTER APPROVAL for creation,
migration and synthetic seeding of that isolated demo database:

```powershell
python -B scripts\id_demo.py prepare
python -B scripts\id_demo.py serve
```

In another terminal:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP\dawana-platform"
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

Open `/dic/operations/id-printing`, check current-version filters and old-batch
confirmation after reissue, and inspect actual PDFs. Check participant/guardian
downloads, non-Latin names, portrait/logo fit, QR scans and 100% print dimensions.
No approval to modify development data or start Stage 2 is implied by these steps.
