# DIC Campsite Operations — Stage 2, Phase 2.1

## Audit performed before implementation

The existing React application already routes `/dic/operations/*` outside the
public SiteChrome layout. It has a staff login screen, green/cream/gold shell,
responsive sidebar, Escape-to-close mobile navigation, loading/error/empty states,
pagination and report downloads. The participant portal has separate scoped OTP
cookies. No second application, login, participant store or password reset is needed.

Existing backend OperationsBaseView uses SessionAuthentication, IsAuthenticated,
and `can_view_dic_operations`; mutations retain session CSRF enforcement. Login
uses Django authenticate/login with CSRF and rate limiting. `_user_data` already
exposes granular finance, audit, contact, report and ID capabilities. Existing
Operations access permits some explicitly authorised non-is_staff accounts; this
legacy behavior is preserved. The NEW campsite overview additionally requires
active is_staff status. No user, group, password or permission grant is modified.

Existing data sources inspected:

- CampEdition and RegistrationCategory: edition configuration and categories.
- RegistrationOrder/Item and price revisions/items: booking, participant source,
  payment state and accepted pricing evidence.
- Participant: existing participant details, never duplicated.
- House/HouseAllocation and housing policies/services: inventory and allocation.
- CampEnrollment/DigitalIDIssue and participant_services.eligibility: stable ID,
  active credential and stronger eligibility definition.
- DICAdminAuditEvent: immutable application audit history.
- PaymentAttempt, PaystackWebhookEvent, payment return grants, payment_views and
  payments.py: existing provider integration and payment evidence.

Existing APIs cover auth, registration dashboard, filters, participants,
registrations, houses, payments, enrollments, ID commands, printing, audit activity
and CSV/Word report export. The old registration overview counts successful
attempts with a broader definition than participant_services.eligibility. Its
figures are preserved on the separate registration-overview route, not relabelled
as strict campsite ID eligibility. The new campsite summary uses the latter.

## Paystack readiness findings

Source contains initialization and verification clients, HMAC webhook verification,
payload-digest replay protection, provider transaction-ID uniqueness, order/attempt
locks, reference/amount/currency/environment checks, accepted-price-window checks,
provider timestamps and explicit mismatch/reconciliation/duplicate-success states.
These mechanisms are reusable evidence sources, not a general camp accounting
ledger. Code currently explicitly accepts the TEST provider environment in trusted
settlement; live deployment readiness must be separately reviewed and approved.
No assumption is made that Paystack is complete, configured or live, that a
registration has been paid, or that an order's paid label is sufficient evidence.
No provider request was made and no secret configuration was printed or changed.

There are no existing general income/expenditure, settlement-fee/bank receipt,
approval-ledger or end-of-camp financial reporting models to reuse. Existing
payment reports are NOT complete camp financial statements. Finance is a core
dashboard module; its transaction implementation is deliberately deferred.

## Implemented foundation

- `/dic/operations` now opens a dedicated Campsite overview for active authorised
  staff, using the existing session. No ordinary public navigation item is added.
- Existing registration overview remains at `/dic/operations/registration-overview`.
- Existing Participants, Housing, ID lookup/printing, Payments, Reports and Activity
  routes remain. No housing, issuance, payment or participant mutation is added.
- New Finance, House scoring, Feedback and Comprehensive reporting plan pages
  are explicit Planned destinations, not working entry/approval/export controls.
- The new overview selects a camp edition and distinguishes registered people,
  verified ID-eligible people, pending registration/payment state, recorded house
  allocations, eligible unallocated people, active eligible QR IDs and attention.
- Attendance is explicitly Unavailable. An issued ID or house record is not check-in.
- Numbers have API definitions; absent/invalid values display Unavailable, never
  an invented zero. No edition returns no metrics, never global aggregate data.
- Scoped API response contains aggregates and edition names/IDs only, not contacts,
  portraits, QR payloads, digests, encrypted secrets or raw payment details.

New API: GET `/api/v1/dic/operations/campsite/?edition=<existing-id>`.
No write verbs. Invalid/missing requested editions fail with 400. Omitted edition
uses the existing active/latest fallback. No configured edition yields null metrics.
All aggregate queries filter that edition; distinct participants prevent duplicate
registration items increasing totals. Candidate enrollment objects are UNSAVED;
the overview never calls ensure_enrollment, issuance, payment or audit mutations.
No cache storage: existing Operations finalizer enforces no-store/Pragma no-cache.

New plan routes: `/dic/operations/finance`, `/dic/operations/scoring`,
`/dic/operations/feedback`, `/dic/operations/reporting-hub`. Finance requires the
existing finance capability in the UI; its real payment-review endpoint retains
server-side finance checks. Other plan pages contain only non-sensitive static
architecture information. They expose no new sensitive APIs. Future module data
must not rely on these frontend guards for authorization.

## Metrics and boundaries

Registered means distinct participants with an item in the edition, including
cancelled registrations. Eligible means the exact current ID eligibility service
passes: payment evidence, source review and identity restrictions included.
Awaiting payment verification includes non-cancelled people failing the existing
registration/payment state check; other evidence/source problems and cancelled
registrations appear in attention. These are distinct meanings, not revenue totals.
Recorded assignment counts existing active allocation rows for registered people,
not a fresh certification of housing policy. Unallocated counts eligible people
without an active allocation. Active IDs are eligible enrollments with unexpired,
unrevoked configured QR issues, not evidence of a physical QR scan or attendance.

The overview edition selector scopes ONLY the new summary. Existing directories
and reports keep their existing edition query parameters/defaults; some legacy ID
and audit directories are cross-edition staff tools. The UI states that navigation
does not carry the overview edition into those tools. Their contracts are not
silently changed here. Before future operational transactions, use a required
edition context through every domain and reject cross-edition related IDs.

## Existing staff permissions — unchanged

| Capability | Current enforcement / reuse |
| --- | --- |
| Campsite overview | Active authenticated is_staff + can_view_dic_operations |
| Participant/housing read | Existing can_view_dic_operations Operations endpoints; contacts separately protected |
| Housing management | Existing can_allocate_participants / can_reassign_allocations / can_release_allocations, approval and guardian permissions; existing Admin/services only |
| ID lookup | Existing can_view_dic_ids; card views additionally enforce staff |
| Issue/reissue/revoke and bulk printing | Existing active staff + can_manage_dic_ids; existing eligibility/CSRF/audit |
| Payment review | Existing can_view_dic_finance + Operations session |
| Audit activity | Existing can_view_dic_audit + Operations session |
| Operational CSV/Word exports | can_export_dic_reports plus finance/contact export permission checks |

Existing setup_dic_staff_roles groups inspected: DIC Registration Staff, DIC Finance
Reviewers, DIC Administrators. The management command was NOT run. No full Admin
grant is proposed for the initial two or three onsite staff. An administrator must
review each existing account's minimal required capabilities; non-is_staff accounts
may use legacy Operations but cannot access the new campsite data. This difference
is explicit, not a silent grant or a changed login policy.

## Future permission/approval plan — NOT installed or granted

Proposed capability names below are design identifiers only. No model Meta
permissions, migrations, groups or assignments are created in Phase 2.1.

| Domain | Proposed separated capabilities | Required boundary |
| --- | --- | --- |
| Finance | finance.view, income.record, expense.record, finance.approve, finance.reconcile, finance.export, receipt.view | Recorders cannot approve their own entries; approver/reconciler roles, amount limits and exceptions require committee approval. Existing finance-review rights do not automatically authorize writes. |
| House scores | score.enter, score.verify, score.correct, leaderboard.view, score.export | Activity/date/house/edition references validated; separate verifier; immutable corrections reference original; only verified records affect rankings. |
| Feedback | feedback.submit, feedback.review, feedback.confidential_view, feedback.export | Explicit organiser authority; participant scope if approved; ratings and questions approved first; confidential fields excluded by default. |
| Attendance | attendance.view, attendance.record, attendance.correct, attendance.export | Separate future domain; QR/ID validity alone is never presence. |
| Reporting | report.generate, report.export, report.confidential_export, report.signoff | Reports require BOTH report permission and every source domain permission; no cross-domain privilege escalation. |

Every future domain must enforce permissions server-side, explicit edition scope,
CSRF for mutations, safe errors, data minimization and immutable actor/time/action
history. Receipt access should use private storage and authorized delivery, with
limits and validation. Sensitive responses/logs and exports must exclude raw QR,
authentication and recovery credentials. Retention and access reviews are pending.

## Core future module architecture

### Finance

CampEdition is the financial boundary for every eventual entry, approval, receipt,
reconciliation and report. Registration payment evidence is imported only after
trusted provider verification; an idempotent source identity should include provider
environment/account and provider transaction ID with a database uniqueness rule.
Webhook replay or verify retry cannot create another income entry. A payment attempt,
order and accounting entry are distinct entities. Duplicate successful charges
require review, not silent omission or reuse of the order's status. Preserve gross
income, provider fees, net settlements, refunds and bank receipts as distinct facts.

Later implement cash, transfer, donations and sponsorship income; expenditure with
vendor, amount, currency, camp date, category, method, description and private
supporting receipts; approval state and immutable corrections/reversals; Paystack
fee/settlement/refund/bank reconciliation; income/expenditure/balance/category and
transaction reports; printable PDF and Excel/CSV exports. Never infer cash balance
from confirmed orders. Refund recognition and cash/bank accounting rules require
approval. No transaction models or migration designs are implemented in this phase.

### House scoring and leaderboards

Later records bind approved activity, camp-local date, edition and house to points,
entry actor, verification actor and correction history. Only verified scores count;
daily and cumulative rankings derive from the same verified data. Categories,
points, tie-breaks, score correction/appeal rules and publication rights must be
committee-approved. No hardcoded activities or point values, scoring model, ranking
calculation or official leaderboard is introduced now.

### Daily and overall feedback

Later capture authorised organiser daily ratings, observations, challenges,
corrective actions, recommendations and follow-up. Participant evaluations require
approved questions, scope and confidentiality/consent rules. Consolidation into
daily, overall and category-specific analysis must minimize PII and restrict raw
confidential responses. No questionnaire, rating scale, response model or collection
form is implemented now.

### Comprehensive reporting

Later provide daily/domain PDF, Excel/CSV and end-of-camp reports covering finance,
house scores, attendance, feedback and operational performance. Use edition/date
filters, verified-domain definitions, snapshots/version identifiers, generation
actor/time/filter history and optional sign-off. End-of-camp summaries must reconcile
to detailed supporting records. Domain/privacy permissions apply at query AND
export time. Existing CSV/Word export and audit patterns are reusable, but do not
claim current PDF/Excel camp reports exist. Printing PDF ID cards is unrelated to
financial or evaluation report readiness.

## Files changed in this phase

Created:
- backend/dic/campsite_api.py
- backend/dic/test_campsite_foundation.py
- backend/CAMPSITE_PHASE_2_1.md
- dawana-platform/src/pages/CampsiteFoundation.jsx
- dawana-platform/src/services/campsiteModules.js
- dawana-platform/src/services/campsiteFoundation.test.js

Modified:
- backend/dic/operations_api.py: additive can_access_campsite profile capability only.
- backend/dic/urls.py: additive read-only campsite route.
- dawana-platform/src/pages/Operations.jsx: foundation entry, plan routes, generic
  edition-neutral shell title, actual registration status in preserved old view.
- dawana-platform/src/services/operationsNavigation.js: future core-module navigation.
- dawana-platform/src/pages/Operations.css: responsive module cards and planned labels.

No schema, migration, group, account, record, pricing, payment, ID credential,
house assignment, participant portal or audit-history changes. Pre-existing Git
changes were preserved. No database connections, migrations or network Paystack
requests were executed for this task.

## Validation and remaining work

Frontend tests include navigation permissions, edition input safety, unavailable
metrics, actual rendered planning pages, finance denial, existing protected route
structure and responsive CSS/menu safeguards. Backend database-free tests cover
anonymous/inactive/nonstaff/missing-permission rejection before data access,
selected/missing/invalid editions, no write route, private-field exclusion, cache
headers, scoped aggregate filters, distinct people and existing eligibility reuse.

The new frontend test initially failed due to its test-harness SSR import of a
CommonJS package; it now uses the normal React Router import, and the five focused
tests pass. Final full frontend results: 69 tests passed, 0 failed; lint and
production build passed. Build warns about a >500 kB chunk; it still succeeds.
This is a performance follow-up, not an authorization bypass.

Python remains denied execution in Codex. Six database-free backend tests are
implemented but UNEXECUTED. Run from the existing activated PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
python -B backend\manage.py test dic.test_campsite_foundation.CampsiteFoundationTests --verbosity 2
```

SimpleTestCase prevents DB access and creates no test database. For frontend:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP\dawana-platform"
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

Before browser sign-off, exercise real session/CSRF and 403 behavior, no-edition and
two-edition summaries, cancelled/unpaid/reconciliation/expired/revoked cases, menu
closing/scrolling and long labels at 360/768/desktop widths. Static/SSR checks are
not a claim of browser acceptance. Eligibility reuse currently performs per-person
queries; measure response time for the intended camp size before deployment.

Database-backed tests are NOT authorized by this document. Proposed next validation
after explicit approval: extend the existing guarded isolated validation runner with
a campsite-specific test selection covering real edition exclusion and role cases,
then run it against a uniquely named local test database. Do not use a default test
database name, mutate dawana_dev, or run setup_dic_staff_roles as part of validation.

## Proposed Phase 2.2 — not started

First obtain operational rules and confirm initial accounts/edition context. Then
implement only the next agreed domain (for example, participant check-in and daily
attendance), with approved presence/correction rules, server permissions, immutable
audit and isolated validation. Finance, scores and feedback remain CORE roadmap
requirements with separately approved rules and later migrations. Phase 2.1 stops
at this foundation; none of those domain implementations is started automatically.
