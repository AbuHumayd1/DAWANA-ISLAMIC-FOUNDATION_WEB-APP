# Phase 5 — feedback, final evaluation and confidential complaints

This supersedes the online-welfare postponement for the authenticated endpoints
only. Source implementation is prepared; schema and isolated acceptance are
deployment gates. Phase 4 remains postponed. Public registration and deployment
must remain disabled. Phase 3 browser acceptance is still incomplete.

## Implemented

- Daily responses: same camp date only, Africa/Lagos, no edits, HMAC duplicate
  receipts. Final evaluation: final camp date onward, canonical final-day answer,
  one final receipt per camper/edition, including corrected camp end dates and
  historical date-based receipts. Neither workflow sends email.
- Five-point questionnaires, tutor accommodation exclusion, explicit accommodation
  not-applicable option for other campers. Existing staff/verified lecturer flows
  retain their separate identities and permissions.
- Questionnaire version 1 retains the historical three-point questions and labels;
  new submissions use version 2. Reports separate versions and suppress anonymous
  groups below five, including individual question distributions with fewer than
  five applicable answers. CSV/print remain aggregate-only and audited.
- `/dic/feedback?channel=daily|final|welfare|history` reuses the existing page.
  Complaint creation and history both resolve `item_id` through current eligible
  booking scope. Affected participant and identified registrant are persisted;
  no complaint ID, supplied participant identity or booking reference authorizes
  access. Guardian selection is explicit. Complaints can be submitted during camp.
- Complaint urgency and contact preference are recorded (no new delivery system).
  Authorized submitters see their selected camper's complaints/current statuses,
  never officer notes, assignments or private audit events. Legacy cases without
  an affected participant are not guessed or exposed through the camper history.
- Operations welfare review: edition/status/category/urgency filters, case reads
  audited, separate view/manage permissions, assignment, version checks, idempotent
  updates and confidential internal notes. Welfare data never enters feedback
  analytics or exports.
- General staff-group provisioning no longer grants welfare permissions to DIC
  Administrators automatically. **Existing grants are preserved** and must be
  reviewed before activation; no real users were changed by this work.

## Files

Backend: feedback_schema.py, feedback_models.py, feedback_services.py,
feedback_api.py, templates/dic/feedback_summary.html,
management/commands/setup_dic_staff_roles.py, test_feedback.py,
test_welfare_postponement.py, test_phase5_policy.py,
migrations/0031_phase5_feedback_welfare.py. Existing feedback_admin.py, routes,
authentication and settlement services are reused without replacement.

Frontend: pages/CamperFeedback.jsx, pages/Feedback.jsx, pages/Feedback.css,
pages/Operations.jsx, components/operations/FeedbackForms.jsx,
components/dic/PortalPhase3.jsx, services/portalPhase3.js,
services/operationsNavigation.js; feedback.test.js, portalPhase3.test.js,
operationsRefinement.test.js.

Validation: scripts/validate_dic_phase5_policy.py,
scripts/validate_dic_phase5.ps1, scripts/validate_dic_phase5_demo.py.

## Database-free validation (from repository root, PowerShell)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_phase5.ps1
```

This runs only SimpleTestCase suites without Django database setup/teardown,
blocks database connections/external network, checks the runtime migration graph
and Phase 5 model state, then runs frontend tests, lint and build. It stops at the
first failed stage. The synthetic database name is never connected to or created.

In the implementation environment Python could not start because access to its
base Python 3.13 executable was denied. Backend execution/parity is therefore
unverified; run this command locally before approving the schema gate.

Frontend validation completed: all 207 tests passed. After the final form-ref
cleanup, the 28 focused feedback/portal/Operations tests passed again; lint and
production build passed. The build retains its bundle-size advisory. No browser
or database-writing acceptance was run.

## Schema gate — prepare only; separate approval before migration

Historical migration files are unchanged. Source dependency ordering is:

`0026 -> 0028 -> 0029 -> 0030 -> 0027 -> 0031`

0031 depends directly on 0027. It adds questionnaire versions (existing rows get
1; new rows default to 2), nullable affected participant for legacy compatibility,
urgency/contact preference and their check constraints. It does not guess legacy
child identities, seed content, settle payments or grant permissions to users.

Read-only preflight:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_demo.py preflight --database dic_2026_demo
```

**Only after explicit approval to apply the reviewed Phase 5 schema:**

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_demo.py migrate --database dic_2026_demo --confirm-demo-writes --approve-phase5-schema
.\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_demo.py integration --database dic_2026_demo --confirm-demo-writes
```

The helper establishes the demo target before settings load; verifies requested,
configured and PostgreSQL database identity; requires existing 0030; permits only
0027/0031 as pending targets; and refuses backward plans. Migrations target dic
0031 explicitly. It never creates/drops/flushes/resets databases. Integration uses
the real feedback services in rollback transactions, never DiscoverRunner, with
provider/network isolation and an outcome/cleanup receipt. No browser acceptance
or database-writing command was executed during implementation.

Do not use the old unrestricted test runner to validate this demo procedure.
Do not rotate DIC_FEEDBACK_PRIVACY_KEY without reviewing duplicate-receipt
continuity. It must be privately configured with at least 32 characters; there is
no fallback to Django's secret or participant identifiers.

## Remaining acceptance / release gates

- Run database-free backend checks and resolve any meaningful failure.
- Approve/apply isolated schema using the guarded procedure, then integration.
- Review existing welfare grants and designate actual authorized reviewers using
  existing permissions, without blanket committee access.
- Verify mobile forms, guardian child isolation, tutor applicability, duplicate
  responses, changed payment eligibility, complaint status/private-note separation,
  and five-point/legacy CSV and print output in isolated manual acceptance.
- No Phase 3 browser rerun is required for implementation; its acceptance remains
  outstanding. No Phase 5 browser acceptance is claimed.
- `backend/render-migrate.sh` still runs unrestricted migrate. This is an unchanged
  Phase 7 release blocker; no deployment is authorized.
