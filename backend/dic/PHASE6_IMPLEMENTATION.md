# Phase 6 reporting handover

## Implemented source

Operations `/dic/operations/reporting-hub` uses
`GET /api/v1/dic/operations/reporting/`. It requires active Operations staff and
the existing `can_export_dic_reports` permission. Explicit edition selection is
mandatory. Domain authorization runs before report queries; unavailable schemas
produce Not Yet Configured, never invented zero totals.

- Registration: distinct participants/bookings, category/gender/collected-age
  bands, trends, pending/confirmed/cancelled, recorded payment states, trusted
  payment conversion, tutor separation, explicit account/housing-guardian links.
  Booking contact records are not presented as unique guardians. Confirmation is
  not a claim of payment or complete portal eligibility.
- Finance: existing `payment_reason` and `registration_rows` evidence and
  deduplication logic; gross, documented adjustments, net, expected booking value,
  attempt states/exceptions, trends, accepted-price-line category gross. No bank
  settlement claims and no arbitrary allocation of refunds to siblings. Existing
  Finance detail/export permissions are additionally required for those actions.
- Housing: actual houses/capacity/current occupancy, allocation-window/category
  counts, queue exceptions and tutor exclusion exceptions. No room inventory is
  invented. Payment-evidenced unassigned campers are explicitly distinguished
  from fully housing-cleared campers, for whom no persisted certificate exists.
- Attendance: recorded arrival/departure/return trends, evidence-based presence,
  unknown versus absence, open departures and invalid transitions. Arrival is not
  daily attendance. Movement/check-in permissions required; event UUID details
  additionally require participant view. No QR tokens or release evidence exposed.
- Academic: Not Yet Configured; no teaching-class models or timetables created.
- Feedback: reuse Phase 5 summaries and privacy threshold, separate questionnaire
  versions, distributions/averages, recommendation and trends. Registered-cohort
  participation rates are explicitly labeled; historical eligible-population
  rates remain unavailable. Comments remain in existing audited review, not exports.
- Welfare: explicit welfare-view permission even for statistics; status/category/
  urgency, outstanding/assigned workload counts and resolution-event trends. No
  descriptions, identities, officer notes or confidential histories are projected.

Filters, bounded CSV/print, sortable tables, SQL pagination for registration and
movement details, accessible charts and mobile layouts are included. Other domain
results are aggregate/bounded existing Finance projections. Date boundaries use
Africa/Lagos. Read/export audit events are the only endpoint writes; no business
command, settlement, allocation or movement mutation runs from reports.

General summary permissions do not grant Finance, welfare, housing or movement
access. No new permissions are automatically granted. Existing staff permissions
are global across editions: explicit edition scoping is enforced, but no invented
staff-to-edition assignment model is introduced.

## Files changed

Backend: reporting_services.py, reporting_api.py, test_reporting.py,
templates/dic/reporting.html, urls.py; dic_finance/services.py adds optional report
timezone/order scope while preserving existing caller behavior; feedback_services.py
adds optional date filtering to existing summary queries.

Frontend: pages/Reporting.jsx, Reporting.css, Operations.jsx, CampsiteFoundation.jsx;
services/reporting.js, reporting.test.js, operationsApi.js, operationsNavigation.js,
campsiteModules.js, campsiteFoundation.test.js, operationsRefinement.test.js.

Validation: scripts/validate_dic_phase6_policy.py, validate_dic_phase6.ps1;
validate_dic_phase5_policy.py accepts additional database-free suites/graph checks.

## Validation and migration safety

214/214 frontend tests PASS; lint PASS; production build PASS (bundle-size advisory).
PowerShell parser check PASS. Backend policy, ORM, migration-state checks and
integration acceptance NOT RUN: the environment cannot start the configured Python
interpreter (access denied). No repeated Python attempts were made for Phase 6.
No databases, migrations, browser acceptance, payments or delivery providers were
accessed during implementation. Backend query execution therefore remains unverified.

No Phase 6 migration is needed. Existing Finance/Movement app schemas are required
for their respective reports. Phase 5 0027 and 0031 remain deferred; code checks
their tables/columns before feedback/welfare access. Historical migrations were
not changed. Reviewed source order remains 0026 → 0028 → 0029 → 0030 → 0027 → 0031.

From the repository root, run the full database-free validation locally:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_phase6.ps1
```

It runs reporting, Finance reconciliation, movement/check-in, housing policy,
feedback/privacy and authentication policy tests under network/database guards
and a fast process-scoped test hasher, then frontend tests/lint/build. It validates
source migration graphs/model parity without applying migrations. Stops on failure
and reports PASS/FAIL/NOT RUN. `-FrontendOnly` is an explicit partial run and
intentionally returns overall INCOMPLETE when backend checks are skipped.

## Release gates

- Run full local database-free validation; resolve any backend/query failures.
- Separately approve deferred schema and database-writing acceptance before use.
- Phase 3 browser end-to-end acceptance remains outstanding; none was rerun.
- Review sensitive actual staff grants before exposing confidential reports.
- `backend/render-migrate.sh` still performs unrestricted migrate: unchanged Phase 7
  release blocker. No deployment or public-registration enablement was performed.
- Phase 4 timetable work remains postponed. Phase 7 was not implemented.
