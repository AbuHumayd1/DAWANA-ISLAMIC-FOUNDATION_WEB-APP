# Phase 2.4B — Online welfare postponed

Online welfare HTTP functionality is disabled for every user, including superusers. Existing in-person camp procedures remain the route for concerns and urgent assistance. General daily/final camper, identified staff/lecturer feedback, analytics and aggregate exports remain active in code.

## Changes

- `backend/dic/feedback_api.py`: unconditional dispatch mixin returns a consistent private/no-store HTTP 503 on participant/welfare/, operations/welfare/ and operations/welfare/<uuid>/ for every method. It returns before DRF authentication, parsing, handler selection, transaction decorators, storage inspection or confidential queries. Existing handlers and their authentication/permission rules are retained underneath; reactivation requires a separate reviewed change. This deliberately serves an unavailable response rather than a CSRF/authentication challenge on retired routes; active feedback authentication/CSRF protections are unchanged.
- `backend/dic/operations_api.py`: feedback-entry capability is derived only from staff/lecturer feedback permissions, excluding welfare-only permissions. Welfare permissions themselves are not removed or weakened.
- `dawana-platform/src/pages/CamperFeedback.jsx`: daily/final channels remain; welfare option/form removed; in-person assistance notice added.
- `dawana-platform/src/pages/ParticipantPortal.jsx`: link renamed **Give Camp Feedback**.
- `dawana-platform/src/pages/Feedback.jsx`: staff/lecturer entry retained; welfare channel and case-management UI removed. Direct welfare component is static and has no hooks, API calls or forms.
- `dawana-platform/src/pages/Operations.jsx`: direct welfare route displays the static notice within the existing authenticated shell.
- `dawana-platform/src/services/operationsNavigation.js`: welfare item removed; submission label simplified.
- `backend/dic/test_welfare_postponement.py`: database-free route/method/user matrix and welfare-only capability regression.
- `backend/dic/test_feedback.py`: HTTP assertions now expect unconditional 503, no confidential content and no read-audit writes, even for authorised viewers. Existing direct-service permission/lifecycle tests remain to protect dormant safeguards; active feedback/privacy/export tests remain.
- `scripts/validate_dic_backend.py`: existing isolated --operations-feedback option includes the new postponement module.
- `dawana-platform/src/services/feedback.test.js`: static notice/no-form/no-welfare-navigation regression. Existing feedback form/analytics/export checks remain.
- `dawana-platform/src/services/operationsRefinement.test.js`: expected route navigation count is now 16; permission/grouping matrix remains.
- `backend/dic/WELFARE_POSTPONEMENT_PHASE2_4B.md`: this handover supersedes active-online-welfare instructions in the original Phase 2.4 handover.

No welfare model, record, migration, secret or staff permission grant was deleted/changed. Migration 0027 is unchanged; no 0028 was created. Existing pending model/migration work elsewhere in the workspace was preserved. Since there are no model-state changes, this correction introduces no new migration parity change; fresh runtime parity still requires the isolated runner.

## Verification

- Frontend tests: **97 passed, zero failed**.
- Lint: passed without warnings.
- Production build: passed; existing >500 kB warning remains, about 544 kB.
- Targeted git diff --check: passed; existing line-ending conversion warnings.
- Backend attempt: existing venv Python fails before Django starts with base-interpreter **Access is denied**. No backend tests or migration parity checks executed here. No database created or modified.

Local activated PowerShell, repository root:

```powershell
# Database-free preliminary checks; no test database.
python -B backend\manage.py test dic.test_feedback.FeedbackPrivacyTests dic.test_welfare_postponement.WelfarePostponementTests --verbosity 2

# Complete suite and migration parity using the runner's fresh isolated PostgreSQL DB.
python -B scripts\validate_dic_backend.py --operations-feedback
```

The isolated runner never migrates/flushes development, refuses database reuse and retains its unique test database. No migration application command is needed for this disablement.

Manual acceptance: confirm daily/final selection, staff/lecturer entry, summaries and CSV/print still work; welfare is absent from navigation/forms; direct welfare URL gives only the in-person notice; direct GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS/TRACE requests to each welfare API return 503 without confidential content. HEAD bodies may be stripped by the HTTP server, as expected. Check desktop/mobile normal scrolling. Browser verification has not been claimed as executed in this task.
