# Dawana and DIC 2026 functional acceptance assessment

Assessment date: 28 October 2026, Africa/Lagos. Verdict: **NOT YET VERIFIED** for end-to-end launch acceptance. Existing frontend checks pass; they do not establish successful registration, payment settlement, portal access or camp operations against a database.

## Evidence and execution boundaries

Evidence hierarchy: real executed end-to-end journeys, executed integration tests, executed unit/component tests, then static inspection. Findings below explicitly distinguish these levels.

Executed this assessment: `scripts/validate_dic_phase4.ps1 -FrontendOnly`. Results: **217 tests, 217 passed, 0 failed, 0 skipped; lint PASS; production build PASS**. Evidence: `output/acceptance/functional-frontend-validation.log`. These tests include mocked API/service tests, React server-rendered component assertions and a QR fallback integration test. They are not browser journeys or database-backed integration tests. Vite reports a non-fatal bundle-size warning.

Attempted backend policy command: `backend/.venv/Scripts/python.exe -B scripts/validate_dic_phase4_policy.py`. Python could not start because access to its configured Python 3.13 interpreter was denied. Backend tests/checks are **NOT RUN**, rather than test failures; no individual backend assertion executed. No alternate interpreter retry or installation was attempted.

Browser discovery was attempted through the computer-use tool. It returned no browsers/apps and reported that the native pipe was unavailable. Browser navigation, interaction, screenshots, mobile viewport checks and visual accessibility checks are **NOT RUN**. No preview server or API mock harness was started after discovering that blocker.

Prior operator-confirmed baseline is preserved, not asserted as freshly executed: 231 database-free backend tests, 217 frontend tests, lint/build, and 19 Step B tests/offline preflight passed. The recorded demo state is 44 applied/11 pending migrations; production state remains UNVERIFIED. Backup/restore investigation remains paused.

## Feature acceptance matrix

PARTIAL means selected unit/component behavior was executed, while integrated functionality remains unverified. NOT IMPLEMENTED is a source-confirmed missing capability, not an invented runtime failure.

| Area | Status | Executed evidence and remaining limits |
|---|---|---|
| Public navigation/Home/About/Programs/Events/DIC | PARTIAL | Public navigation tests pass, including active DIC versus portal paths. About navigation is the homepage `/#who-we-are` section, not a dedicated About route. Actual browser routing, mobile menu, hash scrolling, scroll reset, accessibility and loading/error presentation NOT RUN. |
| Donations | PARTIAL; payment NOT IMPLEMENTED | Source renders an informative donation page with official details pending. No donation checkout or supported charge action exists. Do not confuse DIC registration Paystack with donations. |
| Contact | PARTIAL; delivery/channels NOT IMPLEMENTED | Source has required form controls and a truthful unsent notice. Email/telephone/address/WhatsApp remain placeholders; submit sends/stores nothing. Browser submission NOT RUN. |
| Registration | PARTIAL | Category, price, control, privacy, contact and API tests pass with synthetic/mocked data. Single/multiple registration persistence, current configured categories/prices, minor guardian enforcement on actual requests, recovery delivery and confirmation NOT RUN. |
| On-site assistance | PARTIAL; scope discrepancy needs review | Tests verify public/recovery handoff; Operations' old assisted route redirects to registration listing. A separate feature-flagged staff creation service still exists, default disabled; actual flag/authorization not inspected. See AC-05. |
| Paystack | PARTIAL | Payment-return/API frontend tests pass. Source checks amount/currency/reference/test domain, verified settlement and webhook signature. Initialization, callbacks, duplicate callbacks, abandonment, mismatches, grouped settlement and webhook idempotency against persisted state NOT RUN. No real provider requests. |
| Participant/guardian accounts and portals | PARTIAL | Account/session/API, expiry, selected-camper and portal component tests pass using mocks. Activation delivery, login/logout sessions, multi-child access and unrelated/unpaid child rejection against real requests/storage NOT RUN. |
| Academic class assignment | NOT IMPLEMENTED | Backend capability explicitly unavailable; class projection says pending setup. Tutor non-applicability is intentional. Houses/categories must not be represented as classes. |
| Houses/profile | PARTIAL | House configuration and camper projection tests pass; actual allocations/profile edits/view permissions NOT RUN. |
| Portal announcements | NOT IMPLEMENTED | No participant announcement model/API/rendering workflow found in scoped application sources. Public lecturer announcements are separate editorial content. |
| QR/check-in/movement | PARTIAL | QR decode/fallback integration, check-in and movement client tests pass. Source checks edition-bound nonexpired/nonrevoked ID and officer permissions. Issuance, actual scanning, arrival/departure, duplicate scans, movement persistence and audit/report consistency NOT RUN. |
| Timetables | PARTIAL; operational data unavailable by baseline | Tests verify exactly activities/food, ten dates, year-crossing navigation, no invented food times and Day 6 amendments. Backend source has explicit edit/publication rights, published-only edition scope and Lagos selection. Mobile/print/current activity UI and backend authorization NOT RUN. The 188 prepared entries remain unimported/unpublished; schedule availability is not accepted. |
| Feedback/welfare | PARTIAL | Frontend request/validation/presentation tests pass. Source separates staff permissions and confidential projections, validates camp dates and fails closed for missing schema. Submission, duplicate handling, authorized triage/status/audit and sensitive-data isolation against storage NOT RUN. |
| Administration/reporting | PARTIAL | Operations navigation/filters/report parameter tests and server-rendered controls pass. Authentication, actual memberships, exported content, contact restrictions, attendance totals and confidentiality NOT RUN. Class reporting cannot supply absent academic assignments. |
| Finance | PARTIAL | Finance path/input/presentation tests pass. Source distinguishes verified income, expenses/commitments and documented refund/reversal reconciliation, with bounded cumulative adjustments. Actual reconciliation, duplicate handling, actor separation, CSV totals and audit persistence NOT RUN. This does not assert provider refund execution exists. |
| Millionaire/Family Feud host games | NOT IMPLEMENTED | No game routes, engines, question/round/host/projector controllers or game-specific tests found. Timetable activity names and house scoring do not implement games. |

## Journey assessment

No complete journey below was executed in a browser or against a database. Each has selected frontend component/service coverage only.

| Journey | Assessment and missing evidence |
|---|---|
| Visitor → registration → test payment → confirmation | PARTIAL components; NOT RUN end-to-end. Needs approved isolated synthetic registration storage and an in-process/mock payment adapter, not real Paystack. |
| Guardian → multiple campers → payment → portal | PARTIAL selections/payloads; NOT RUN end-to-end. Must verify one grouped order, exact authoritative totals, eligible child scope and unrelated/unpaid-order denials. |
| Camper → portal → timetable/class | PARTIAL interface; NOT RUN authenticated journey. Timetables are not populated/published; academic allocation absent. |
| Officer → QR arrival → movement → departure | PARTIAL client/QR helpers; NOT RUN operations journey. Needs synthetic issued IDs, officer roles, duplicate/expired scans, presence and audit reconciliation. |
| Administrator → management → reports | PARTIAL controls; NOT RUN authenticated management/export journey. Test explicit per-domain access and actual exported contents. |
| Finance officer → reconciliation → report | PARTIAL client/policy inspection; NOT RUN accounting journey. Verify verified-versus-pending, duplicate success, original charge/refund evidence, role separation, totals and immutable audit. |
| Camper → feedback/welfare → authorized handling | PARTIAL input/request tests; NOT RUN confidential journey. Verify unrelated guardian/child denial, no internal-note leakage, duplicate submissions and officer-only handling. |

## Confirmed gaps and discrepancies

These are source-confirmed acceptance gaps. No executed workflow failure or confirmed P0 vulnerability was found. Severity reflects impact if the missing capability is required for launch; intentional placeholders must not be presented as functioning services.

| ID / severity | Feature; expected behavior | Actual behavior / evidence | Reproduction or verification procedure | Minimum recommendation |
|---|---|---|---|---|
| AC-01 / P2 | Reach the Foundation and submit an enquiry | Contact details are placeholders; `Contact.jsx` explicitly prevents sending and reports unsent. Static evidence, not executed browser submission. | In an isolated browser, open `/contact`, inspect channels, enter synthetic required fields and submit; verify truthful unsent state. | Obtain approved contact channels; decide whether public launch excludes form delivery. If delivery is required, separately scope implementation and acceptance. |
| AC-02 / P2 | Make a donation through a supported method | `Donate.jsx` says official donation details coming soon; no donation checkout. | Open `/donate` in an isolated browser and inspect available actions. | Publish only Foundation-approved instructions or explicitly accept an informational-only donation page. Do not enable live payments during testing. |
| AC-03 / P2, camp-readiness dependency | Camper sees assigned academic class | `portal_phase3.py` advertises classes unavailable; class projection is pending setup. | Inspect capabilities/class projection; later use a synthetic camper portal session. Do not substitute a house/category. | Agree whether academic allocation is launch-required. If required, it needs separately authorized implementation; not a validation-only change. |
| AC-04 / P2 | Camper receives official portal announcements | No participant announcement workflow found. | Inspect participant routes/models and portal rendering; later confirm with a synthetic session. | Explicitly defer or separately scope an approved announcement capability. |
| AC-05 / P2, latent scope discrepancy | Assisted on-site users follow the same public registration process | Public handoff exists and Operations route is retired, but `dic.assisted_registration` and `dic_assistance.services.create_assistance` retain a distinct staff creation path. `DIC_ASSISTED_BOOKING_ENABLED` defaults false; service delegates `_create_order`, so shared creation logic exists but the workflow differs. Runtime activation is NOT VERIFIED. | Inspect `backend/config/settings/base.py`, assisted input/view code, assistance service and passing `assistedRegistration.test.js`. Do not activate it or call its create endpoint. | Review the retained capability against the current same-public-process requirement; keep disabled. Any retirement/restriction change requires a focused review, not a broad refactor or speculative security claim. |

Both planned games are also absent. They are not blockers for the platform's basic registration/authentication services unless the camp explicitly requires digital game delivery at launch. They are a separate camp-programme readiness decision, not part of accepting the seven completed phases. No game implementation or testing was performed.

Timetable content and pending migrations are operational dependencies, not evidence of a code defect. No P1 core failure is asserted without executing a core workflow. No P3 visual defect is asserted without a browser/visual review. The build-size warning is a performance-review item, not proof of a functional failure.

## Launch blockers and next stage

Confirmed capability decisions: academic allocation, announcements, contact delivery/channels, donation support and optional game delivery. Resolve AC-05's retained alternate assistance path by scope review. Do not rebuild features during this assessment.

Unverified dependencies: real browser/mobile/accessibility journeys; backend execution in this agent environment; schema availability after the separate controlled migration gates; actual role grants; verification/recovery email behavior; payment callback/webhook and persisted idempotency; confidential data isolation; QR presence/audits; finance/report accuracy. No live public paid-launch readiness is asserted while payment mode remains deliberately test-only.

Next stage proposal — **requires separate approval before provisioning or connection**:

1. Designate a new disposable PostgreSQL database such as `test_dic_functional_acceptance_<run-id>` and a restricted test role on an explicitly approved server. Never reuse `dawana_dev`, `dic_2026_demo` or production. Approve the exact name, role, migration/test-database creation operations and fixture ownership first.
2. Approve applying the reviewed schema only to that disposable target, with synthetic adults, minors, guardians, multi-child/unpaid/unrelated orders, tutors, houses, QR issues and least-privilege officers. All database writes remain confined there.
3. Use intercepted local email and mocked Paystack initialization/verification/webhooks, with all external sends/provider calls blocked. Do not issue real charges or borrow production credentials.
4. Approve synthetic draft/published timetable fixtures **only in the disposable target**, independent of the 188 unimported real-edition source entries. Include ten dates, Day 6 amendments, Lagos midnight and empty/unpublished/foreign-edition cases. No demo import/publication is implied.
5. Run all seven journeys with a browser harness, direct forbidden-request checks and synthetic welfare/finance exports. Verify mobile menu, focus/labels, viewport overflow, errors, print and scrolling. Retain sanitized per-scenario receipts and classify actual defects.
6. Preserve evidence and synthetic IDs. Database cleanup/drop or deletion is separately approved, not automatic. Backup/restore work stays paused; this proposal does not approve it or bypass release gates.

For immediate safe local source/unit validation, use the existing consolidated command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_phase4.ps1
```

This command uses the database-free backend policy guards and frontend tests/lint/build. It does not provision a database or run end-to-end acceptance. Local Python must be usable. Do not replace it with an unrestricted Django test/migrate command against an existing PostgreSQL server.

## Safety statement

No Django server, database connection, database creation/reset, migration, backup, restore, timetable import/publication, real payment, external delivery, environment credential edit, production configuration change or deployment occurred. Application code was not changed. The original migration receipt and existing data/evidence were not overwritten. New artifacts are this report and the frontend validation log. The requested database-backed acceptance stage remains pending explicit authorization.
