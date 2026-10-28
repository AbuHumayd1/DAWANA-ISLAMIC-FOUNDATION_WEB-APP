# DIC 2026 launch-readiness and feature-gap audit

Audit date: 25 October 2026. Project: Dawana Islamic Foundation, existing Dawana platform. Scope: repository inspection, read-only local PostgreSQL inspection and existing non-mutating frontend checks. This is an audit, not implementation approval.

## A. Executive summary

**Not ready for unrestricted public registration or a claim of complete camp operations.** Registration, payment verification, booking-scoped email OTP, Digital IDs, house allocation, check-in and official scoring have substantial implementations. Their existence is distinguishable from an end-to-end, production-verified service. Current local data cannot demonstrate a paid camper journey.

The highest-priority findings are:

1. Public registration is intentionally closed: the active 2026 edition is draft, registration dates are unset and there are no active participant categories. The “Stay informed”, unknown deadline and unknown fees are consistent with those conditions. Do not open registration or invent fees during testing.
2. Real payments are blocked by implementation, not merely an environment flag. `dic/payments.py::paystack_secret_key()` requires test mode and an `sk_test_` key; `dic/payment_views.py::_apply_verified_transaction()` requires configured test mode and provider domain `test`. A reviewed live-payment implementation and isolated validation are needed before accepting real payments.
3. Finance and Comprehensive reporting are explicitly planned UI modules. Existing Payments and Reports are useful but are not camp accounts or a comprehensive reporting system.
4. Feedback has forms, permissions, services and exports, but its schema is absent. Its storage guard requires all six feedback/welfare tables from the deliberately unapplied `dic.0027_feedback_welfare`. Feedback cannot presently be enabled independently by configuration.
5. Certificates, DIC Quest and Family Challenge have no functional implementation found in the inspected application models, routes or services.
6. Backend execution remains blocked in this execution environment. The existing virtual environment reports access denied to its configured base Python. Database-backed and full-browser acceptance remain unverified.
7. Reporting has confirmed semantic inconsistencies: its definition of “verified paid” is weaker than Digital ID/participant eligibility, and a payment-attempt row can be labelled verified because a different attempt paid its order. These are not safe foundations for financial totals.

No application code, settings, permissions, records, migrations or registration availability were changed. No email or payment workflow was invoked. Only this report was added.

### Evidence and verification boundary

- Frontend: `dawana-platform/src/App.jsx`, `pages/DIC.jsx`, `pages/ParticipantPortal.jsx`, `pages/Operations.jsx`, `components/dic/CamperExperience.jsx`, API services and navigation definitions.
- Backend: `backend/config/settings/base.py`, `backend/dic/urls.py`, models, registration/payment/participant/identity/allocation/check-in/scoring/feedback services and Operations APIs; supporting `backend/dic_scoring` app.
- Checks executed now: `npm.cmd test` — **137 passed, 0 failed, 0 skipped**; `npm.cmd run lint` — **exit 0**. PowerShell blocks `npm.ps1`; `npm.cmd` works without changing execution policy.
- Attempted database-free backend classes: `dic.test_activity_scoring.ActivityPolicyTests`, `dic.test_feedback.FeedbackPrivacyTests`, `dic.test_welfare_postponement.WelfarePostponementTests`. **Not executed:** `.venv/Scripts/python.exe` cannot access its configured Python 3.13.7 base executable. A direct base-path invocation was also unavailable. No Python installation, environment or ACL was changed.
- Frontend tests are Node tests, including source assertions, server rendering and mocked transport. They do not prove a browser login, Gmail delivery, database concurrency or responsive rendering.
- No new browser session was established for this audit. Prior browser-access limitations remain unresolved; no visual or authenticated browser pass is claimed. No build was run during this audit; earlier build results are historical evidence only.
- Production deployment, production schema, provider credentials, mailbox delivery, TLS/proxy behaviour and actual staff grants were not inspected or exercised. Local database facts below do not establish production state.

### Read-only local database evidence

PostgreSQL queries used a read-only transaction default and a statement timeout. Only schema, migration state, edition configuration and aggregate counts were inspected; no personal emails or names were selected.

| Fact | `dawana_dev` | `test_dic_portal_2026_local` |
|---|---|---|
| DIC schema | Through `dic.0026_house_score_transaction` | Through `dic.0026_house_score_transaction` |
| `dic_scoring.0001_activity_award` | Applied; award table exists | Unapplied; award table absent |
| `dic.0027_feedback_welfare` | Unapplied | Unapplied |
| Feedback/welfare tables checked | Absent | Absent |
| 2026 edition | Active, draft; registration dates unset | Active, draft; registration dates unset |
| Configured camp end | 1 January 2027 | 1 January 2027 |
| Active registration categories | 0 | 0 |
| Bookings / campers | 0 / 0 | 1 / 1 |
| Booking payment state | No bookings | One submitted, pending-payment booking |
| Allocations / check-ins / house ledger entries | 0 / 0 / 0 | 0 / 0 / 0 |

The isolated unpaid booking supports OTP testing only. It does not establish paid eligibility, Digital ID issuance or scoring readiness. Its missing scoring table must not be mistaken for a zero personal score.

### Architecture and migration boundaries

The frontend is a React/Vite SPA. Public pages use the public layout; `/dic/participant/*` suppresses public chrome and uses the camper shell; `/dic/operations/*` uses the existing Operations shell. Django uses DRF and PostgreSQL, with `accounts.User` extending `AbstractUser`, the main `dic` domain app and the small `dic_scoring` supporting app. No separate camper account application exists.

Principal records are `CampEdition`, `RegistrationCategory`, `PrimaryRegistrant`, `Participant`, `RegistrationOrder`, registration items and price revisions; `PaymentAttempt`/webhook events; recovery and portal challenges/grants/scopes; `CampEnrollment`, `DigitalIDIssue`, `GuardianRelationship`, `House`, `HouseAllocation`, housing jobs, `CampCheckIn`, `HouseScoreTransaction` and `ActivityAward`. Feedback/welfare models exist in source but are not backed by the inspected databases.

`backend/dic_scoring/migrations/0001_activity_award.py` explicitly depends on **`('dic', '0026_house_score_transaction')`**, not 0027. Its dependency chain can support scoring without feedback/welfare. `backend/dic/migrations/0027_feedback_welfare.py` depends on 0026 and the swappable user model and creates four feedback-related models plus `WelfareReport` and `WelfareEvent`.

An unrestricted `migrate`, or an ordinary Django test runner that migrates all installed apps to their latest heads, can include 0027. Selecting a test label or checking a targeted dependency graph does not constrain the test runner's migration behaviour. In particular, do not assume `scripts/validate_dic_backend.py` is safe for this constraint solely because its selected test suite or preliminary graph check targets 0026. Any future test execution needs a reviewed, disposable-database migration configuration. No migration command is authorised by this report.

## B. Feature inventory

Priority: P0 = prerequisite to the affected public launch; P1 = required camp-operation capability or correctness work; P2 = enhancement that may be deferred with an explicit scope decision. Status is conservative: implemented business workflows remain untested until integrated acceptance is available.

| Module | Feature | Status | Evidence | Missing work | Priority |
|---|---|---|---|---|---|
| Public site | Homepage, DIC entry and programme information | Implemented but untested | `src/App.jsx`, public layout, `pages/DIC.jsx` | Browser links/content/accessibility acceptance | P1 |
| Registration | Edition/opening/pricing gates | Complete and verified | `dic/views.py::_registration_is_open`, `CampEdition.pricing_configuration_errors`; read-only draft state | Authorised real dates/categories/prices before public opening | P0 |
| Registration | Multiple participants, booking and price snapshot/revisions | Implemented but untested | `dic/models.py`, `dic/views.py`, `pages/DIC.jsx`; `dic/tests.py` | Isolated backend tests and multi-camper journey | P0 |
| Registration | Recovery and pricing-change acceptance | Implemented but untested | `dic/recovery.py`, `recovery_views.py`, recovery routes, pricing accept route | Delivery, expiry, repricing and replay acceptance | P0 |
| Payments | Test-mode initialize/return/webhook/server verification | Implemented but untested | `payments.py`, `payment_views.py`, `payment_return.py`; payment hardening/return tests | Backend and isolated test-provider acceptance | P0 |
| Payments | Real Paystack payment support | Blocked by dependency | Test-only configuration and provider-domain checks | Reviewed live-mode support, approved credentials/configuration and controlled verification | P0 |
| Portal auth | Booking reference, email OTP and booking scope | Implemented but untested | `participant_api.py`, `participant_services.py`; portal/remediation tests | Gmail round trip and negative scope tests | P0 |
| Portal auth | Duplicate request prevention and 429 UI | Complete and verified | `services/participantApi.js`, `participantSession.js`, `participantThrottle.test.js`; current test suite passes | Real-browser check remains separate | P1 |
| Portal auth | Transactional email deployment | Blocked by dependency | `dic/recovery.py`, email/worker flags in settings; delivery management commands | Prove API/worker settings parity, SMTP success and operational monitoring | P0 |
| Portal auth | Remembered device / Google Sign-In | Missing | No remembered-device model, Google auth route or identity link found | Optional scoped identity design and explicit product approval | P2 |
| Portal | Five-view shell, camper selection, branding | Implemented but untested | `CamperExperience.jsx`, `CamperBrand.jsx`, `ParticipantPortal.jsx`; rendering/source tests | Widths 320/375/390/430 and desktop, keyboard/menu/scroll acceptance | P1 |
| Portal | Personal total/history, own-house ranking, house standings | Implemented but untested | `portal_dashboard.py`, `activity_scoring_api.py`, `CamperScores.jsx` | Paid/checked-in seeded test cases in a disposable DB; reverse/transfer tests | P0 |
| Housing | Allocation, reassignment, release and guardians/queue | Implemented but untested | `allocation.py`, `housing_service.py`, `housing_policy.py`, admin console | Realistic eligibility, capacity, concurrent allocation and guardian tests | P0 |
| Attendance | Physical camp arrival/check-in | Implemented but untested | `checkin_api.py`, `checkin_services.py`, `CampCheckIn.jsx`, `test_checkin.py` | Permission, duplicate and concurrent arrival acceptance | P0 |
| Attendance | Daily/session attendance and checkout | Missing | Existing record is camp check-in; no general attendance system found | Only implement if separately required; do not infer attendance from IDs | P2 |
| Digital ID | Staff issue/reissue/revoke and camper card access | Implemented but untested | `identity_cards.py`, `identity_views.py`, `participant_services.py`, `StaffParticipantIDs.jsx` | Full eligibility/guardian/revocation/expired-card tests and PDF rendering | P0 |
| Digital ID | QR verification and print batches | Implemented but untested | `identity_tokens.py`, `printing_api.py`, `portrait_pdf.py`; identity/printing tests | Anonymous/staff response separation, scanned QR, batch print acceptance | P0 |
| Official scoring | Fixed 38 individual/17 collective catalogue | Implemented but untested | `scoring_catalogue.py`, `activity_scoring.py`, `dic_scoring/models.py` | Backend policy/integration/concurrency tests | P0 |
| Official scoring | Existing ledger, direct awards, supervised reversal | Implemented but untested | `scoring_services.py`, `scoring_api.py`, `HouseScoring.jsx` | Exactly-once and original-house reversal acceptance | P0 |
| Finance | Payment attempts and reconciliation warnings | Partially implemented | `operations_api.py::OperationsPaymentsView`, Payments page | Reliable transaction-grain financial definitions and reconciliation workflow | P0 |
| Finance | Income, budgets, expenses, receipts, balances | UI only | `campsiteModules.js::finance` explicitly planned; no dedicated finance API/models found | Minimal approved accounts design, roles and audit trail | P1 |
| Finance | Refunds and adjustments | Missing | Status fields exist; no complete provider refund/accounting workflow found | Authorised approval, reconciliation and append-only adjustment workflow | P1 |
| Reports | Six CSV/Word operational reports | Partially implemented | `operations_api.py::OperationsReportView`, `_report_rows` | Correct verified-paid semantics, filter scope, report-grain tests | P0 |
| Reports | Comprehensive PDF/Excel and cross-domain summaries | UI only | `campsiteModules.js::reporting-hub` | Permission-aware, accurate combined reporting | P1 |
| Feedback | Camper, staff and lecturer submissions/review/export | Blocked by dependency | `feedback_models.py`, `feedback_services.py`, `feedback_api.py`, feedback pages; 0027 absent | Approved feedback-only schema route and privacy/permission tests | P1 |
| Welfare | Restricted welfare operations | Blocked by dependency | Retired 503 APIs, postponed UI, unapplied 0027 | Remain postponed; not a camper-portal launch prerequisite | P2 |
| Certificates | Eligibility, issuance, release, PDF, verification | Missing | No certificate models/APIs/templates/routes/generator found | Implement approved participation-certificate requirements | P1 |
| Games | DIC Quest | Missing | No operational game model, host API or session/results implementation found | Separate individual game module, if included in launch scope | P1 |
| Games | Family Challenge | Missing | No house-game host/session/results implementation found | Separate game scores; explicit approved award bridge only | P1 |
| Operations | Staff shell, grouped navigation and permissions | Implemented but untested | `Operations.jsx`, `operationsNavigation.js`, `operations_api.py` | Role matrix, direct-route denial and mobile acceptance | P0 |
| Operations | Overview attendance accuracy | Partially implemented | `campsite_api.py` returns `attendance=None` and obsolete not-implemented text | Reconcile overview with existing check-in service | P1 |
| Audit | Operations event history and export audits | Implemented but untested | `DICAdminAuditEvent`, Operations Activity view, report audit writes | Review details visibility/retention and negative permission tests | P1 |

### Finance and reporting findings

**Existing:** the Payments screen exposes payment attempts, provider references/status, expected/provider amounts and discrepancy information to finance-authorised users. Report exports include registrations, participants, payments, categories, houses and attention items; CSV and DOCX formats, a 5,000-row ceiling, export audits and separate contact-export permissions are present. CSV spreadsheet injection protection is implemented. House ledger, check-in and feedback have their own print/export surfaces; these are separate from the comprehensive-reporting placeholder.

**Missing:** an income ledger for other authorised income, budgets, expense categories and evidence, budget-versus-actual, bank settlements/provider fees, net balances, cash reconciliation, complete refunds and financial adjustments. A successful payment attempt is not proof of bank settlement. Quoted order totals are not income, and a list of attempts is not a balance sheet.

**Confirmed correctness concerns in `operations_api.py`:**

- `_verified_order_queryset()` and `_verified_payment()` check confirmed + paid + any successful attempt. Participant eligibility additionally checks trusted source relationships, accepted price revision, verification metadata, provider identifiers/amount/currency, payment timing and reconciliation conditions. A single label must not imply these different guarantees.
- The payment export's “Verified paid” value is order-level. A failed attempt on an order paid by another attempt can receive “Yes”. Summing attempts or filtering this column can overstate receipts. Financial reporting needs an explicit grain and provider-transaction uniqueness.
- Participant export source selection uses an edition item rather than the full reviewed source-resolution guarantees used for IDs; multiple-booking ambiguity needs regression coverage.
- Order serialization collects allocated house records without constraining that display list to the order's edition. Cross-edition allocations can make a house label misleading.
- Category and house aggregate branches do not apply the same date/order filters as transaction reports, despite shared filter controls. Payment dates refer to attempt creation. The UI needs explicit filter semantics and unsupported filters should not imply they affected results.

The read-only database has no paid records against which to quantify these risks. They are source-confirmed semantic inconsistencies, not evidence that money has already been lost or duplicated.

Coverage gaps include age/gender demographic summaries, historical attendance, individual/collective scoring breakdowns, game results, full finance and operational performance. Existing participant lists/demographic filters do not constitute a comprehensive demographic report. Scoring printouts do not constitute a consolidated end-of-camp report.

### Feedback dependency, privacy and welfare separation

`feedback_models.py` defines anonymous camper responses, HMAC duplicate receipts, identified staff/lecturer responses and edition-specific lecturer access, plus two welfare models. `require_feedback_storage()` currently requires **all six tables**. Consequently, installing only four tables without corresponding service/model-state work would not make feedback available.

Implemented feedback features include daily/final camper forms through the booking grant; staff submissions under existing permissions; lecturer submissions by mapped existing staff accounts; channel/day summaries; restricted detail access; aggregate CSV/print exports. Final feedback opens at the configured end date. Anonymous analytics omit participant identity and suppress small groups below five responses. HMAC duplicate receipts have no response foreign key; stable `DIC_FEEDBACK_PRIVACY_KEY` configuration is needed. Free-text privacy still requires review, retention rules and staff guidance. Camper feedback access is booking-scoped; it is not automatically the same paid-eligibility gate as Digital ID issuance.

Welfare endpoints deliberately return 503 through their retirement mixin; the direct welfare screen states postponement and is absent from navigation. General feedback must not become a path to welfare data. Existing role setup also needs review: broadly granting every `dic` permission can unintentionally include future welfare permissions after schema installation.

**Recommended future schema route, subject to approval and a migration-state review:** keep historical 0027 unchanged and unapplied; introduce only the necessary feedback schema in a separate supporting app with a dependency on dic 0026, and deliberately update model ownership/storage checks and permission wiring. Do not duplicate ownership of the same tables, fake migration history, rewrite an applied migration or add a dic 0028 that depends on 0027. A separate app is a recommendation to evaluate, not a ready-to-run migration plan. Confirm migration state in every target before preparing it. Maintain welfare 503 boundaries and explicit denial tests. No feedback/welfare schema was created in this audit.

## C. Confirmed blockers versus enhancements

### Before accepting real public paid registration

- Authorised edition/category/pricing/opening configuration is absent locally, intentionally. Preserve draft while testing.
- Paystack live support is not currently supported by the inspected code.
- Backend execution and database-backed security/payment/scoring tests are not validated here.
- Gmail delivery and authenticated multi-camper portal acceptance are not proven by an idle worker or channel availability response.
- Production deployment configuration, shared throttling/cache behaviour, trusted proxy handling, secure cookies/CSRF and API/worker parity need environment-specific verification.
- Correct financial/report labels before presenting them as verified income or balances.

### Before advertising the complete requested camp feature set

- Feedback storage/privacy/role work; keep 0027 and welfare postponed.
- Certificates and authorised release workflow before their promised final-day availability.
- Finance and comprehensive reporting to the agreed operational scope.
- Both games if they are part of the announced programme's digital offering.
- Browser, mobile, staff-role, payment-gate, booking-isolation and ID acceptance.

### Enhancements, not prerequisites to existing OTP access

Google Sign-In, opt-in remembered devices, broader automation and daily/session attendance can follow. Welfare remains a separate postponed capability. Game sophistication can be deferred; presenting missing games as available cannot. A certificate system need not block initial registration if its later release is explicitly scheduled and delivered before the promised date.

## D. Actual registration-to-portal journey

All API paths below are relative to `/api/v1/dic/`. A route's existence is not proof of a passing integrated journey.

| Step | Frontend route/component | Backend path/service | Access, implementation and missing proof |
|---|---|---|---|
| 1. Homepage | `/`, public layout/SiteChrome | Public site content | Public entry exists; browser link checks pending |
| 2. DIC page | `/dic`, `DIC.jsx`, landing components | `registration-options/`, public editorial/showcase APIs | Correctly displays closed/draft state; no public opening authorised |
| 3. Categories | `/dic/register`, registration form | `registration-options/` | Requires open edition and priced active categories; currently none |
| 4. One/multiple campers | `/dic/register`, DIC form and summary | Registration serializers and existing models | Validates participant/category input; isolated multi-participant acceptance pending |
| 5. Booking | `/dic/register/summary`, `DIC.jsx` | `POST orders/` | Existing UUID booking-reference mechanism and price snapshot; does not prove payment |
| 6. Paystack start | `/dic/register/checkout` | `POST orders/<uuid>/payments/initialize/` | Booking bearer, valid current pricing; test mode only |
| 7. Provider return | `/dic/register/payment-return`, confirmation routes, `PaymentReturn` | Payment-return grant and `POST payments/return/` | Scoped cookie/grant + CSRF; browser query cannot itself mark paid |
| 8. Independent verification | Return polling/confirmation | Payment verify route, `payments/paystack/webhook/`, `payment_views.py` | Server verifies provider reference/amount/currency/domain and handles dedupe; no live-mode acceptance |
| 9. Confirmation | `/dic/register/confirmation` and `/:orderId` | Return summary / authorised order retrieval | Pending, failure and verified success remain distinct; browser acceptance pending |
| 10. Portal handoff | Link to `/dic/participant` | No automatic authentication | Router state can prefill booking reference; it must still require OTP |
| 11. OTP login | `/dic/participant`, `ParticipantPortal.jsx` | `participant/auth/csrf/`, `options/`, `challenges/`, `verify/`, `me/` | Contact/reference verification, encrypted queued email, browser-bound challenge, scoped grant; actual Gmail delivery unproven |
| 12. Information/house | Camper Home/Profile and selection | `participant/enrollments/`, participant services | Explicitly scoped bookings/items; pending payment visible but paid-only actions denied |
| 13. Scores/standings | Points/Houses, `CamperScores.jsx` | `participant/scoring/?item=<uuid>&page=...` | Own history, own current-house individual ranking and aggregate house standings; no arbitrary private booking lookup |
| 14. Digital ID | Profile → Open my Digital ID, `ParticipantIDCard` | `participant/enrollments/<uuid>/id/` and `/card/` | Requires eligible current issued ID; card checks dependent/guardian rules; physical print HTML or portrait PDF routes exist |
| 15. Activities | Camp view; separate `/dic/feedback` | Participant feedback endpoints; staff scoring endpoints | Camp information and feedback code exist; no camper game/host system; feedback schema blocked |
| 16. Certificate | No implemented route/action | No certificate API | Missing; must follow approved registration-only eligibility and authorised final-day release |

Registration reopening also requires complete positive pricing: regular fees for active categories, valid registration dates and consistent early-bird fees/cutoff where applicable. `setup_dic_2026` deliberately creates a draft skeleton; it is not a public-launch configuration command.

## E. Operations navigation and usability

Source of truth: `services/operationsNavigation.js`, `pages/Operations.jsx` and `backend/dic/urls.py`. There are **16 navigation entries in five groups**. Paths below are relative to `/dic/operations`; APIs are relative to `/api/v1/dic/`.

Permissions shorthand: Ops = existing `can_view_dic_operations`; campsite = active staff + Ops; finance = `can_view_dic_finance`; export = `can_export_dic_reports`; IDs = `can_view_dic_ids`; manage IDs = `can_manage_dic_ids`. Existing action-specific permissions still apply. These labels do not grant access.

| Group / section and path | Purpose and actual functionality | Permission and API | Missing action / acceptance tests |
|---|---|---|---|
| Camp Overview / Overview `/` | Current edition and operational counts | Root renders campsite foundation; `operations/campsite/`; campsite access | Attendance is hardcoded unavailable with obsolete “not implemented” explanation. Check counts, edition switch, denied role, mobile cards |
| Camp Overview / Registration overview `/registration-overview` | Registration trends, distributions and attention | Ops API `operations/dashboard/`; campsite navigation visibility | Not finance/attendance. Check date windows, empty data and chart labels |
| Participants & Registration / Camp Check-in `/check-in` | Eligible arrival lookup, one physical camp check-in, print list | Campsite; POST also `can_check_in_dic_participants`; `operations/check-in/` | No daily/session attendance. Test unpaid denial, duplicate/concurrent check-in, export permission and mobile lookup |
| Participants & Registration / Registrations `/registrations` | Filtered orders and details | Ops; `operations/registrations/`, `/<uuid>/`; separate contact visibility | No general manual create-booking workflow here. Test filters, private contact denial, cross-edition house labels, mobile detail |
| Participants & Registration / Participants `/participants` | Participant directory, demographics/status/house filters and detail | Ops; `operations/participants/`, `/<uuid>/` | Test source ambiguity, pagination, masked contacts and narrow tables |
| Participants & Registration / Participant IDs `/participant-ids` | Enrollment directory, prepare/issue/reissue/revoke controls | IDs to view, manage IDs to mutate; `operations/enrollments/`, `/<uuid>/id/` | Directory spans editions; ensure clear labels. Test eligibility, source review, mutation denial and mobile actions |
| Participants & Registration / ID Card Printing `/id-printing` | Eligible card directory, PDF batches, tracked print confirmation | Manage IDs; `operations/id-printing/`, `/export/`, `/<batch>/printed/` | Export must not itself mark printed. Test batch isolation, eligibility changes, PDF and mobile selection |
| Participants & Registration / House allocation `/houses` | Allocation directory/history and unallocated review | Ops; `operations/houses/`; Django Admin performs changes under allocation/reassignment/release permissions | Existing admin handoff, not an in-SPA full allocator. Test links, capacity/guardian constraints, history and table overflow |
| Camp Activities / House scoring `/scoring` | Ledger/direct awards and individual/collective fixed-activity forms | Campsite + view scores; record/correct permissions; `operations/scoring/`, `/activities/`, `/<entry>/reverse/` | Backend tests outstanding. Test caps, eligibility, duplicate tasks, exclusions, tied winners, exactly-once and reversal; mobile forms |
| Camp Activities / Feedback `/feedback` | Summary/detail/export | Campsite + feedback view; detail/export permissions separately; `operations/feedback/` | 503 until storage dependency resolved. Test small-group suppression, roles, CSV/print and mobile filters |
| Camp Activities / Submit feedback `/feedback-submit` | Staff/lecturer forms | Campsite + relevant staff/lecturer entry permission; `operations/feedback/options/`, `/submit/` | Storage blocked; lecturer must have edition mapping. Test duplicate/day/channel and mapping rejection |
| Finance & Reports / Payments `/payments` | Read-only attempts and reconciliation flags | Finance; `operations/payments/` | No finance ledger or settlement/refund workflow. Test amount/status semantics, finance denial and narrow-table handling |
| Finance & Reports / Finance `/finance` | Planned camp accounts explanation, link to Payments | Campsite + finance; no dedicated finance API | Placeholder explicitly labelled planned. No save/approve/expense actions. Test link permissions and no implied balance |
| Finance & Reports / Reports `/reports` | Six CSV/Word exports | Export; finance additionally for payments; `operations/reports/`, filters API | Correct report grain/filters; test 5,000-row limit, CSV injection, contact permissions, audited exports and mobile controls |
| Finance & Reports / Comprehensive reporting `/reporting-hub` | Planned integrated reporting, permitted Reports link | Campsite; no integrated report API | No PDF/Excel/cross-domain generator. Test link visibility and honest planned state |
| Administration / Activity Log `/activity` | Paginated actor/action/target/details/time history | Audit permission; `operations/activity/` | Not a reconciliation system. API returns event details to audit-authorised users: review privacy/retention; test denial and mobile readability |

**Other destinations:** `/welfare` is a direct postponed notice, not a menu item. Django Admin remains the existing mutation/configuration surface for house setup/allocation and source review. There is no House Leader Dashboard. Unknown Operations paths fall back to the dashboard; this can conceal a mistyped link rather than present a useful not-found state. No exhaustive browser dead-link check was possible.

**Mobile status applies to every row:** shared responsive shell, collapsible navigation, Escape handling and link-close behaviour exist in source, but no viewport is visually verified in this audit. At 320, 375, 390 and 430 pixels and desktop, acceptance must cover scrolling, menu open/close/back/refresh, focus and keyboard controls, action buttons, long booking references, table overflow and permission-hidden links. API denial must hold independently of hidden navigation.

### Roles and access observations

`setup_dic_staff_roles` defines Registration Staff, Finance Reviewers and DIC Administrators using existing permissions. Contact view/export, ID management, scoring correction and feedback detail access are separate capabilities. General Operations session access and stricter active-staff campsite access differ; this needs an explicit role acceptance matrix rather than an assumption that all permitted Operations users have identical powers. Existing permissions are not edition-specific officer assignments. Actual production users/group memberships were not inspected.

The Activity API exposes `event.details` under audit permission. Application-level immutable audit model behaviour is useful but is not proof of database-level append-only enforcement against privileged SQL. Do not claim either an observed data leak or tamper-proof storage without further tests.

## F. Recommended independently testable phases

### Phase 1 — Establish trustworthy validation and truthful existing screens

Dependency: a runnable backend and an explicitly disposable PostgreSQL database with a reviewed migration plan excluding 0027. Preserve the current development database and unpaid OTP fixture. Do not use a preview launcher that disables real Gmail delivery for an SMTP test.

Work after approval: resolve interpreter execution with the least disruptive method; run database-free policy tests; use a constrained isolated test setup for registration/payment/auth/housing/check-in/ID/scoring integration and concurrency tests. Verify API and delivery worker use the same database, settings module, Gmail credentials and recovery Fernet key. Restart both after environment changes. Prove Gmail delivery, OTP failure/expiry/retry/cooldown, multi-camper selection, unrelated-booking denial, logout and pending-payment gates. Correct overview attendance explanation and report semantics before trusting totals.

Acceptance: backend tests actually execute with recorded counts, no skipped required concurrency case; migration plan demonstrably excludes 0027; no development/production writes; one verified OTP browser journey; protected paid-only features remain denied for the unpaid booking; mobile widths pass. No new feature architecture is needed to start this phase.

### Phase 2 — Real registration/payment release readiness

Dependency: Phase 1 and separately approved live-payment capability/configuration. Maintain server-side provider verification, HMAC webhook validation, provider-transaction uniqueness, amount/currency checks, price-revision acceptance and cancellation/reconciliation handling. Never accept the browser redirect as payment proof.

Acceptance: test/sandbox evidence for duplicate initialize, delayed return, forged/duplicate webhook, timeout, repricing and amount/domain mismatch; reviewed live-mode boundaries; approved edition dates/categories/fees configured only at an explicit opening checkpoint. Verify deployment HTTPS, allowed origins/hosts, CSRF, shared rate-limit/cache topology and worker supervision. Real-money validation requires separate authorisation.

### Phase 3 — Minimal finance and reliable reporting

Agree accounting scope before schema work: registration receipts uniquely tied to verified provider transactions; separately identified other income and expenses with private evidence; authorised reversals/refunds/adjustments; approval/reconciliation responsibilities. Preserve the payment source records; do not create a second source that double-counts each payment attempt as income. Store money in exact currency units, with explicit gross/fee/net/settled concepts.

Start comprehensive reporting from corrected existing sources and common report definitions. Enforce each included domain's permissions, contact/feedback confidentiality and filter semantics. Include check-in counts, ledger-derived house standings, individual/collective breakdowns, approved finance data and feedback only when its dependency is resolved. PDF/Excel should be outputs of reliable queries, not a new dashboard.

Acceptance: independent totals reconcile with known fixtures; failed/retried attempts never add receipts; every filter has tested semantics; exports cannot disclose unauthorised domains; adjustments retain history. Approve and inspect any new migration separately; no dependence on postponed 0027.

### Phase 4 — Feedback without welfare activation

Dependency: approved model-ownership/migration proposal and privacy/retention/role review described above. Keep welfare APIs unavailable. Minimise the schema to feedback needs; keep lecturer access explicit and the HMAC privacy key stable.

Acceptance: storage guard depends only on approved feedback tables; daily/final/staff/lecturer channels submit correctly; duplicate prevention and small-group suppression work; comments/details/exports have negative permission tests; no identity-to-anonymous-response join or welfare API becomes available. Migration plan and effective permissions reviewed before application.

### Phase 5 — Participation certificates

No certificate implementation was found. Reuse existing participant/enrollment identifiers and private PDF/branding infrastructure where suitable, but create a separate certificate lifecycle. Do not reuse expiring Digital ID eligibility or QR credentials as certificate entitlement.

Recommended minimal design: one issuance per camper/edition with unique public verification identifier, approved participant-name snapshot, template/signature version, issue/revoke/reissue audit and PDF generation; explicit edition release configuration; existing staff permission pattern and booking-scoped participant endpoint. Define “valid, completed registration” with approved registration/payment states, not attendance, check-in, score, exams or games. Release only when the confirmed edition's final day has arrived **and** authorised release is enabled. The configured local end date is 1 January 2027; it is not itself release approval.

Certificates must remain accessible after camp and after Digital IDs expire, through renewed secure portal authentication. A guardian's booking access alone is not universal proof of legal guardianship; use an appropriate approved relationship. Support staff preview/prepare/issue/revoke, private print-ready PDF download and minimal public verification by identifier/QR. Avoid disclosing contact/payment information or exposing an enumerable participant directory. Private signatures/assets need controlled access.

Acceptance: valid completed registrations qualify regardless of attendance/points/exams/games; pending/cancelled/incomplete states follow the approved definition; release cannot occur early; final-day and post-camp downloads work; unrelated bookings and unlinked children are denied; identifiers are unique; revocation/reissue and PDF branding/signatures are verified. No unnecessary portal or dashboard is required.

### Phase 6 — Separate host-operated games

DIC Quest needs individual game sessions, approved content/questions, host controls, answers/internal game scores and results. Family Challenge needs house entries, host-managed sessions/results and internal game scores. No operational implementation was found; generic activity descriptions and official competition award codes are not a game engine.

Use the existing Operations shell and staff authentication for hosts if these games are approved for implementation. Keep internal scores in game-owned records; never sum them into camper points or `HouseScoreTransaction`. Any official house bonus requires explicit approved criteria and the existing authorised ledger-award path with stable occurrence uniqueness. Existing knowledge-competition codes do not automatically authorise a Family Challenge bonus.

Acceptance: unauthorised hosts cannot mutate a game; results cannot silently change official standings; repeated explicit award requests cannot duplicate ledger credit; tied outcomes follow the approved game rules. No House Leader Dashboard.

### Optional later authentication improvements

Current portal authentication is booking/contact based, not a camper password account. Grants are approximately 30-minute fixed sessions, persisted through an HttpOnly cookie and revoked server-side on logout; there is no remembered-device implementation or sliding refresh. Challenges are browser-bound, short-lived, attempt-limited and encrypted for queued delivery. Protected endpoints manually enforce booking grants even where a DRF view has no standard session authentication. Existing CSRF checks and scope enforcement must remain.

Recent frontend work coalesces in-flight options/session requests, briefly caches non-sensitive channel availability, guards duplicate submits and tracks retry cooldowns with a single banner. Backend limits remain intact, including portal and durable contact/IP limits. A successful availability response proves configuration shape, not SMTP delivery or worker health. Verify a shared cache and proxy/IP behaviour for multi-process production rather than assuming process-local throttles are globally consistent.

Google Sign-In can be added as a verified identity linked to an already authorised booking scope. Validate signature, issuer, audience and expiry, use stable `sub`, enforce CSRF/nonce/state as appropriate and do not auto-attach all bookings merely because an email matches. Google notes that third-party email addresses may not remain authoritative even when `email_verified` is true; initial booking ownership still needs the existing secure linking procedure. See [Google ID-token verification guidance](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token) and [Google OpenID Connect documentation](https://developers.google.com/identity/openid-connect/openid-connect).

For optional persistent sessions, prefer a separately revocable, rotating, hashed remembered-device token in a Secure/HttpOnly/SameSite cookie, explicit opt-in and bounded lifetime. Do not store OTPs or reusable auth tokens in localStorage, use device fingerprints as authentication, extend all sessions indefinitely or create staff accounts for campers. Preserve email OTP fallback and booking/guardian boundaries. No authentication settings were changed.

### Digital ID findings and remaining acceptance

`participant_services` requires trusted registration-item relationships and confirmed, paid, correctly verified payment data/current accepted pricing. Check-in and scoring are not prerequisites to Digital ID eligibility. Enrollment preparation is not issuance: staff explicitly issue/reissue/revoke credentials. QR credentials are random, stored hashed plus encrypted; encryption derives from Django `SECRET_KEY`, so key-management/rotation planning matters independently of the recovery Fernet key.

The camper Profile exposes Open my Digital ID only for an eligible current issue. Card endpoints enforce booking scope and dependent/guardian restrictions; an under-five dependent needs the appropriate approved relationship/eligible guardian. Staff have view/manage permissions, printing batches and separately tracked print confirmation. HTML physical-card layouts and portrait PDF generation exist. Anonymous QR verification is minimal; authorised staff get additional identity detail. Old/revoked/expired/ineligible credentials must fail, and issuance expires around camp end. This expiry must not be inherited by certificates.

Acceptance still needed: eligible paid issuance, unpaid/cancelled/incomplete denial, dependent denial, cross-booking denial, same-booking multiple campers, revoke/reissue, actual QR scan, printed PDF/logo/layout, batch state and post-expiry denial. No missing public issue button should be added: camper self-issuance is intentionally not supported.

## G. Product decisions that code cannot answer

1. Which missing capabilities are promised at initial public registration launch versus required by camp opening/final day: full Finance, comprehensive reports and both digital games? Certificates are already approved and need a delivery deadline before release.
2. What exact registration/payment states constitute a “valid, completed registration” for certificates, including complimentary places, cancellations and refunds? The approved exclusions of attendance/points/exams/games remain fixed.
3. Who authorises certificate release/signatures, and what correction/reissue policy and minimal public verification detail are approved?
4. Which staff roles may record, approve and reconcile finance transactions; what approval thresholds, expense evidence/retention rules, income categories and settlement definitions are required?
5. What are the approved game rules, content owners, host assignments and any explicit official-ledger bonus for Family Challenge? Internal game scores remain separate regardless.
6. What approved guardian evidence covers older children and certificate access? The existing under-five housing/ID relationship is not necessarily the complete policy.
7. If persistent login/Google is desired, what opt-in lifetime and device-revocation expectations are approved? This does not block current OTP validation.

No further scoring catalogue, invented fees/dates or architecture restart is needed to answer the audit.

## Conclusion and approval boundary

1. **Already working in verified checks:** the frontend suite passes all 137 tests and lint; request-throttle regression coverage passes. Registration gates correctly reflect local draft configuration. Substantial backend/portal, ID, allocation, check-in and ledger/scoring implementations exist, but integrated execution is not yet proven here.
2. **Genuinely missing:** complete Finance, comprehensive cross-domain reports, certificates, DIC Quest, Family Challenge, remembered-device/Google authentication and general daily/session attendance. Feedback is implemented in code but blocked by schema, rather than absent.
3. **Must complete before the affected launch:** backend/integration/browser validation, real-email proof, production security/configuration checks, live-payment support and authorised registration configuration before taking real payments; reporting correctness before trusting totals; feedback/certificates/games/Finance according to their promised release milestones.
4. **Can wait:** optional Google/remembered devices, broader attendance automation, additional reporting convenience and game sophistication if not advertised. Welfare stays postponed. Certificates can follow initial registration only if delivered before the authorised final-day release.
5. **Recommended first implementation phase:** Phase 1 — restore safe backend execution, establish constrained isolated validation, prove the existing Gmail OTP-to-portal journey, and correct confirmed misleading status/report semantics. Preserve the existing scoring ledger and every database/migration restriction.

Audit complete. Await implementation approval; no application changes or database operations are proposed for automatic execution.
