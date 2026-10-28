# Phase 2.3 — House Scoring handover (25 October 2026)

Implemented at code level. Schema approval/application, backend test execution and browser acceptance remain pending. No databases or staff permission grants were changed.

## Features

The existing House scoring route `/dic/operations/scoring` is now a live page, with camp selector, combined leaderboard, Award/Deduct Points form, recent history, accountable reversal form and two print controls. Existing Poppins, dashboard shell, navigation and scrolling are reused. Tables scroll within their container; the form becomes one column on mobile.

Houses come from the selected edition's existing `House` records with `purpose=participants`. Both genders and all statuses are included; administrative/fathers-only housing is not a competing participant house. Zero-point houses appear. No houses, names or colours are created. Configured `badge_colour` is used only when it is a valid six-digit hex colour; otherwise the UI explicitly says colour not configured. A count other than eight is flagged without manufacturing, truncating or hiding participant-house records.

Awarded and deducted totals are sums of positive-integer transactions; net = awarded − deducted. Negative net scores are allowed. Competition ranks are used (1, 1, 3); ties display by case-insensitive house name, then house ID. Authorised staff entries immediately affect the combined total as requested in Phase 2.3; no separate approval/verification workflow, fixed categories or points policies were invented. Activity/reason and optional note are free text; time and staff come from the server.

History is paginated (25 entries). Corrections retain the original and append equal opposing points with a required reason and link to the original. A transaction can be reversed once; reversals cannot themselves be reversed. Staff can enter a replacement transaction if needed. Gross awarded/deducted totals include original and reversal transactions; their net effect cancels. No edit/delete endpoints exist.

## API and security

All endpoints inherit existing Operations session authentication, CSRF enforcement and no-store response handling. Active staff Operations access and explicit score-view permission are required. There are no public scoring endpoints or participant/contact/QR fields in responses.

- GET `/api/v1/dic/operations/scoring/?edition=<id>&page=1`: combined leaderboard and recent history.
- POST same path with explicit edition and JSON `house`, `entry_type` (`award`/`deduction`), `points`, `activity`, optional `note`, and UUID `request_id`: requires record permission. Server validates data and selects the house within the edition.
- POST `/api/v1/dic/operations/scoring/<id>/reverse/?edition=<id>` with `reason` and UUID `request_id`: requires correction permission; original must belong to that edition.
- GET scoring with `&print=leaderboard` or `&print=history`: additionally requires existing `dic.can_export_dic_reports`. Reports are private/no-store printable HTML using the existing simple print convention. History print includes all entries, beyond the current UI page. Django templates escape names, notes and reasons.

Each write transaction locks the selected camp edition, checks its submission reference, appends the score and writes an event to the existing `DICAdminAuditEvent` log atomically. A repeated matching reference returns the existing entry (HTTP 200), without another write/audit; changed details with the same reference are rejected. New entries return HTTP 201. Client submission references survive an uncertain network result, and the form blocks concurrent submissions. Server uniqueness remains the final guard.

Until the table exists, authorised access returns a clear setup-pending 503 message. Existing dashboard modules do not query the new table and remain independent.

## Proposed migration — do not apply without approval

`0026_house_score_transaction.py` depends on `0025_camp_check_in` and the configured auth model. It creates one `HouseScoreTransaction` table with:

- Protected references to edition, house and responsible staff.
- Award/deduction type, positive points, activity, note and server timestamp.
- UUID request reference, unique within edition.
- Optional unique protected self-reference for one reversal per original.
- Database checks for valid type and points from 1 through 2147483647.

It contains no data migration, seeding, house creation or permission assignments. Default model CRUD permissions are disabled; the three explicit new permissions are:

- `dic.can_view_dic_scores` — leaderboard/history access.
- `dic.can_record_dic_scores` — awards and deductions, also requiring view access.
- `dic.can_correct_dic_scores` — reversals, also requiring view access.

After separately approved migration application, an authorised administrator must explicitly assign appropriate permissions. Existing Django superuser semantics are preserved. Nothing automatically updates staff accounts/groups.

Actual applied migration status was not queried. Review the full pending chain; do not assume only 0026 is pending. It depends on the check-in schema and earlier changes, including the 0022 policy data migration. No migration application command was executed.

## Files changed in this phase

Backend created:

- `backend/dic/scoring_services.py`
- `backend/dic/scoring_api.py`
- `backend/dic/migrations/0026_house_score_transaction.py`
- `backend/dic/templates/dic/scoring_list.html`
- `backend/dic/test_scoring.py`
- `backend/dic/HOUSE_SCORING_PHASE2_3.md`

Backend modified: `backend/dic/models.py` (score model), `backend/dic/urls.py` (scoring/reversal routes), `backend/dic/operations_api.py` (new permission flags).

Frontend created:

- `dawana-platform/src/pages/HouseScoring.jsx`
- `dawana-platform/src/services/houseScoring.js`
- `dawana-platform/src/services/houseScoring.test.js`

Frontend modified:

- `dawana-platform/src/pages/Operations.jsx` — guarded scoring route.
- `dawana-platform/src/pages/CampsiteFoundation.jsx` — permitted quick link.
- `dawana-platform/src/pages/Operations.css` — scoped score form, table and history styles.
- `dawana-platform/src/services/operationsApi.js` — print URLs using the existing API base.
- `dawana-platform/src/services/operationsNavigation.js` — existing item becomes live and score-permission guarded.
- `dawana-platform/src/services/campsiteModules.js` — remove obsolete scoring placeholder; other planned modules remain.
- `dawana-platform/src/services/campsiteFoundation.test.js` — scoring is no longer expected as a planned module; other planning assertions retained.
- `dawana-platform/src/services/operationsRefinement.test.js` — planned badge count updated from four to three, score-permission cases added to 128 navigation combinations; denied route checks retained and expanded.

Registration, payment, housing and check-in records/services were not modified. No unrelated module or Phase 2.4 work was started.

## Tests actually executed

- Frontend: **87 passed, zero failed**, including six new scoring tests covering input/query validation, retry references, tie/zero/negative display, configured colours, correction links, read-only actions, empty states and navigation access.
- Lint: passed without warnings.
- Production build: passed; existing >500 kB bundle warning remains (about 532 kB).
- Targeted `git diff --check`: passed, with an existing line-ending conversion warning.
- Backend attempted: the existing virtual-environment launcher failed before Django started: `did not find executable at 'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.` No Python/virtual-environment/system-permission changes were made.

The **17 new database-free backend tests are unexecuted here**. Coverage prepared: combined math, all eight houses/both genders, stable ties, zero/negative scores, edition scoping, staff and granular permissions, real session CSRF rejection on both write routes, server input validation, entry/audit creation, duplicate requests/conflicts, cross-edition rejection, reversal/cancellation math, repeat reversal idempotency, explicit write edition, print/export access, HTML escaping, setup-pending response and schema metadata. Service unit branches bypass only the transaction decorator and mock ORM calls; they do not prove database concurrency, rollback or actual unique-constraint behaviour.

Browser automation failed to initialise (`failed to write kernel assets`, OS error 3). Desktop/mobile visual and print acceptance remain pending; no screenshots or visual pass are claimed.

## Exact remaining local commands

From the repository root in the existing activated PowerShell environment:

```powershell
# Database-free SimpleTestCase classes only. No test database is authorised.
python -B backend\manage.py test dic.test_scoring.HouseScoringTests dic.test_checkin.CampCheckInTests dic.test_campsite_foundation.CampsiteFoundationTests --verbosity 2

# Read-only review; neither command applies migrations or writes migration files.
python -B backend\manage.py showmigrations --plan
python -B backend\manage.py makemigrations dic --check --dry-run --noinput

Set-Location .\dawana-platform
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

If any test runner asks to create a database, stop. Database-backed integration tests require separate approval.

Before schema approval: confirm setup-pending and permission-denied views, and verify other dashboard pages still work. After separately approved schema and explicit staff permissions, check at 1440×900, 768×1024, 390×844 and 360×800: combined houses, zero/tied/negative ranks, colour fallback, keyboard/form usability, long text, mobile menu, normal document scrolling and both print reports. Real entry/reversal tests, seeded fixtures and isolated-database concurrency/rollback tests require separate data-write approval. Do not use normal development data as disposable test fixtures.
