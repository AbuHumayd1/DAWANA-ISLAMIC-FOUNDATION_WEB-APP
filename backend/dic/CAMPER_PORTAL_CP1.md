# Camper Portal CP-1 handover

Implemented read-only dashboard integration only. No migration files, development data, accounts, permissions, payment logic, house scoring or welfare postponement behaviour were changed. CP-2 and CP-3 were not started.

## Behaviour and API

The existing GET `/api/v1/dic/participant/enrollments/` retains its verified booking, primary-contact, expiry/revocation and eligibility controls. Each authorised registration item now adds:

```json
{"house_assignment":{"name":"existing assigned house","colour":"#147D64"},"checked_in":true}
```

`house_assignment` is null when there is no single active allocated participant-house record matching both participant and edition. Colours come from validated existing `House.badge_colour`; missing/invalid colours are null. Released/reassigned records and inactive/foreign-edition houses are excluded. Ambiguous assignments fail closed to the unassigned presentation. No house selection/editing controls or internal housing reasons are returned.

`checked_in` is the existence of the existing participant+edition CampCheckIn record. That model records a single physical arrival and has no additional arrival states; false means no arrival record. No staff, timestamps, notes or operational events are exposed. Neither projection depends on an issued ID or creates an enrollment. Existing booking-view audit behaviour remains; no new business-record writes occur.

The React dashboard has one clear camper selector, a separate selected-booking registration/payment summary, participant name/category/number, house, arrival status and existing ID action. Selection is derived from the current authorised orders snapshot; stale keys fall back to a current camper, never a saved previous object. Switching selection invalidates pending portal requests and clears card state; the selector is disabled during active operations. Existing expiration clearing also clears selection. Existing read-only PVC/A6/portrait links and backend guardian/ID safeguards remain.

Links reuse `/dic#showcase-activities-title`, `/dic/feedback` and `/dic/register/recover`. Activities remain the existing public published showcase, not a personalised timetable. Recovery still requires its existing contact verification/rate limits. No score or rank is displayed.

## Files

Created:

- `backend/dic/portal_dashboard.py` — minimal scoped housing/arrival projection.
- `backend/dic/test_portal_dashboard.py` — two database-free projection tests and four isolated-DB integration tests.
- `dawana-platform/src/components/dic/CamperDashboard.jsx` — selected-camper presentation.
- `dawana-platform/src/services/camperSelection.js` — current-snapshot selection helper.
- `dawana-platform/src/services/camperDashboard.test.js` — three frontend regression tests.
- `backend/dic/CAMPER_PORTAL_CP1.md` — this handover.

Modified:

- `backend/dic/participant_api.py` — add scoped projection to existing enrolment summary.
- `dawana-platform/src/pages/ParticipantPortal.jsx` — integrate selector/dashboard and recovery shortcut, preserve session/ID handlers.
- `dawana-platform/src/pages/ParticipantPortal.css` — wrapping responsive layout, select and colour swatch; normal document scrolling.
- `scripts/validate_dic_backend.py` — include CP-1 projection/portal tests and existing feedback/privacy/welfare-disabled boundaries in its existing isolated `--ids-only` suite.

No dependencies or model/schema changes. Existing check-in schema (0025) is required for arrival reads; no migration is applied here. Pending feedback 0027 remains unapplied to development by this task.

## Executed checks

- Frontend: **100 passed, zero failed**.
- Lint: passed without warnings after moving selection helpers out of the component module.
- Production build: passed; existing >500 kB bundle warning remains (about 545 kB).
- Targeted git diff --check: passed, with existing line-ending conversion warnings.
- Backend attempt: existing venv Python failed before Django started with base-interpreter Access is denied. **Six new backend tests are unexecuted.** No test database was created by this attempt.
- Browser attempt: initialization failed with kernel-assets path error, OS error 3. No desktop/mobile/print acceptance pass is claimed.

New coverage checks per-participant/edition filtering, minimal payloads, ambiguous/unassigned/invalid-colour states, no staff metadata, arrival independent of IDs, foreign arrivals excluded, expired/revoked/anonymous denial, foreign enrollment rejection and projection only for verified booking items. Frontend tests cover two-camper switching, current-snapshot fallback, house/arrival/ID separation, empty states, booking summary and existing links. Existing portal, guardian/download, recovery, feedback and welfare-disabled tests remain selected by the isolated runner.

## Exact local validation

Repository root, existing activated PowerShell:

```powershell
# Database-free preliminary projection test.
python -B backend\manage.py test dic.test_portal_dashboard.CamperProjectionTests --verbosity 2

# Complete scoped portal/ID regression suite in a unique isolated PostgreSQL DB.
# Requires existing ID QA dependencies and existing local CREATEDB capability.
python -B scripts\validate_dic_backend.py --ids-only

Set-Location .\dawana-platform
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

The existing runner checks model/migration parity and uses a newly named isolated database, retains it and refuses reuse. It never migrates/flushes development or changes role privileges. Do not substitute a production/development database for the test database or install new dependencies without approval.

Manual acceptance at 1440×900, 768×1024, 390×844 and 360×800: verify real test-channel OTP, booking summary, two-camper switching with distinct houses/arrival states, no-ID access to house/arrival, no staff details, pending assignment, existing guardian-protected ID formats, published-activities anchor, recovery link, feedback and welfare-unavailable state. Test normal scrolling/mobile navigation and long names. Synthetic data must remain in an approved isolated demonstration/test database.

## Later integration boundaries

- CP-2: cross-tab/shared-device clearing and other separately approved session improvements remain outside this change. Existing server revocation and expiry still apply.
- CP-3: a future approved individual-score projection can join the same participant+edition summary under booking authorisation. No points, ranks, tables, APIs or house-total derivation were introduced here.

Ready for local backend execution and manual acceptance, not declared fully verified. Stop for review before CP-2.
