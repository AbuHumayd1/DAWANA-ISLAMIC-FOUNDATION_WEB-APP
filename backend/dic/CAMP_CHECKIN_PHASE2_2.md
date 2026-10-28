# Phase 2.2 — Simple Camp Check-in

Implementation is prepared. Database approval, backend execution and browser acceptance remain pending. No migration or database mutation was performed during implementation.

## Behaviour

The existing Operations shell now has **Camp Check-in** at `/dic/operations/check-in`. Staff can select an edition, search names/registration numbers, inspect registration/payment eligibility and house assignments, and record physical arrival. Existing participant ID numbers are also searchable. The registration number is the existing order public UUID; no new registration numbering system is created. Names shared by different people remain separate records. Results are paginated in groups of 25.

Totals cover distinct registered participants in the entire edition, independent of search: Registered, Checked In, Not Yet Arrived and Needs Attention. Cancelled registrations remain visible and are ineligible. Needs Attention includes every currently ineligible participant and can overlap with Checked In if eligibility changes after arrival. Historical arrivals remain intact. An absent house assignment does not prevent eligible check-in. No issued ID or QR scan is required.

The server reuses `participant_services.eligibility`, including confirmed/paid registration, trusted settlement evidence, reconciliation checks, source review and identity restrictions. Read-only candidates support participants without an existing CampEnrollment. Check-in does not prepare an enrollment, issue a credential or change payment/registration records.

## Access and API

- GET `/api/v1/dic/operations/check-in/?edition=<id>&search=<text>&page=1`: existing active staff Operations access. Same authenticated session, CSRF and no-store response base as existing endpoints.
- POST the same path with an explicit edition and JSON `{"participant_id":"<uuid>"}`: additionally requires `dic.can_check_in_dic_participants`. Server supplies the timestamp and actor; clients cannot choose them.
- GET with `&print=1`: private, no-store printable HTML for all matching rows, beyond the current page. Requires the existing `dic.can_export_dic_reports` permission. Names and other values are escaped by Django templates. Browser Print provides the basic paper list.
- Missing check-in table produces a 503 setup-pending message before querying participant data. Existing dashboard endpoints do not depend on that table.

Existing permission grants and staff accounts were not changed. The new navigation item is visible to campsite readers; the action appears only with the new check-in permission. Superusers retain Django's existing permission semantics.

## Proposed database change — approval required before applying

`0025_camp_check_in.py`, depending on `0024_house_badge_colour` and the configured auth model, creates one `CampCheckIn` table:

| Field | Purpose |
| --- | --- |
| id | BigAutoField primary key |
| participant | Protected reference to the existing Participant |
| edition | Protected reference to CampEdition |
| checked_in_at | Server timestamp, not editable through the API |
| checked_in_by | Required, protected staff reference |

A database unique constraint on `(participant, edition)` prevents duplicate arrivals. There are no update/delete check-in endpoints. A repeat request returns the existing arrival without replacing its timestamp/staff or adding another audit event. The transaction locks source orders, then the participant, rechecks source stability and eligibility, creates the arrival and writes `participant_checked_in` to the existing audit log atomically. The unique constraint additionally guards races.

The migration creates the explicit check-in permission; default model add/change/delete/view permissions are disabled. It contains no data migration and assigns no user/group permissions. After schema approval and application, an authorised administrator must separately grant the new permission to designated arrival staff. No automatic account changes are proposed.

Actual database migration status was not queried. Do not assume only 0025 is pending: 0022 contains a policy-initialisation data migration, followed by 0023 and 0024. Review the full pending plan and target database before approving any application. No apply command is executed or prescribed here.

## Files changed for this phase

Backend:

- `backend/dic/models.py` — new arrival model only.
- `backend/dic/migrations/0025_camp_check_in.py` — proposed, unapplied schema.
- `backend/dic/checkin_services.py` — eligibility, directory, transaction, deduplication and audit.
- `backend/dic/checkin_api.py` — authenticated read/write/print endpoint.
- `backend/dic/templates/dic/checkin_list.html` — simple printable list.
- `backend/dic/urls.py` — check-in route.
- `backend/dic/operations_api.py` — expose new permission in existing user response.
- `backend/dic/test_checkin.py` — 13 database-free regression methods.
- `backend/dic/CAMP_CHECKIN_PHASE2_2.md` — this handover.

Frontend:

- `dawana-platform/src/pages/CampCheckIn.jsx` — responsive search, totals and arrival controls.
- `dawana-platform/src/services/checkIn.js` — safe edition/search/page query construction and Lagos-time display.
- `dawana-platform/src/services/checkIn.test.js` — five regression tests.
- `dawana-platform/src/services/operationsApi.js` — printable URL through existing API base; POST uses existing CSRF client.
- `dawana-platform/src/services/operationsNavigation.js` — grouped navigation item.
- `dawana-platform/src/pages/Operations.jsx` — campsite-guarded page route.
- `dawana-platform/src/pages/CampsiteFoundation.jsx` — quick link.
- `dawana-platform/src/pages/Operations.css` — scoped responsive check-in styles.
- `dawana-platform/src/services/operationsRefinement.test.js` — expected route count 15, with explicit assertion for the new route; existing permission/grouping checks retained.

## Verification

Executed:

- `npm.cmd test`: 81 passed, zero failed (five new check-in tests).
- `npm.cmd run lint`: passed without lint warnings after correcting two initial React state/ref warnings.
- `npm.cmd run build`: passed; existing >500 kB bundle warning remains (about 521 kB).
- Targeted `git diff --check`: passed; only existing line-ending conversion warnings.

The initial frontend run reported an old assertion expecting exactly 14 navigation entries. It now expects 15 and checks the new route explicitly; all original permission-combination and route-uniqueness assertions remain.

Backend execution was attempted with the existing virtual-environment Python and the two SimpleTestCase classes. The launcher failed before Django started: `did not find executable at 'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.` No interpreter/virtual-environment/permission changes were made. The 13 new backend methods and six existing foundation methods are unexecuted here.

Database-free backend coverage prepared: denied/inactive/non-staff users; new permission enforcement; real session CSRF rejection; edition/search/pagination scoping; print permission and escaping; invalid write inputs; authorised and repeated POST responses; eligibility rejection; timestamp/actor/audit writes; idempotent existing arrival; changed sources; schema metadata; distinct totals independent of search; missing-table response; no enrollment creation. ORM calls are mocked in these unit tests, and only the transaction decorator is bypassed for service unit branches. These are not proof of actual database concurrency or rollback behaviour.

Browser automation again failed to initialise (`failed to write kernel assets`, OS error 3). Visual acceptance at 1440×900, 768×1024, 390×844 and 360×800 remains pending. Responsive CSS stacks participant cards below 900 px; forms wrap and registration numbers break naturally. No visual pass is claimed.

## Remaining local checks

From repository root in your existing activated PowerShell environment:

```powershell
# These classes are SimpleTestCase with no database access allowed;
# Django should report unused databases skipped, not create a test database.
python -B backend\manage.py test dic.test_checkin.CampCheckInTests dic.test_campsite_foundation.CampsiteFoundationTests --verbosity 2

# Read-only schema/migration review; neither command applies migrations.
python -B backend\manage.py showmigrations --plan
python -B backend\manage.py makemigrations dic --check --dry-run --noinput

Set-Location .\dawana-platform
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

If the test runner unexpectedly proposes creating a database, stop; no database-based suite is authorised. No migration may be applied without approval.

Before schema approval, confirm the page presents its setup-pending message and existing dashboard pages remain usable. After separately approved migration and permission assignment, test with designated staff: edition switching, name/registration search, ineligible records disabled, eligible pending-house arrival, refresh, repeated/double submission preserving actor/time, totals and filtered multipage print output. Check all four viewport sizes, long names, keyboard access and mobile scrolling. Real check-in writes and any isolated database integration/concurrency tests require separate approval; no synthetic records should be inserted into the normal development database.

This phase does not implement daily attendance, QR check-in, finance, scoring or feedback, and starts no subsequent phase.
