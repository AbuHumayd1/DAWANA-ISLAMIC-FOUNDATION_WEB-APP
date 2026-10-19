# Milestone 1L architecture

## 1. Purpose and review status

Prepared on 18 October 2026 against approved checkpoint **`fb24dfa`**, `feat(dic): complete operations portal and unified Dawana themes`. Git HEAD matches that checkpoint. This is a proposal for review, not an implemented feature or authorization to release participants.

DIC 2026 runs **23 December 2026–1 January 2027**, at **Faisal Omar Memorial School**. Preserve those confirmed details. This work does not open registration, enable live payments, create accounts, or alter application code or database schema. Existing local settings, Git-status snapshots and generated acceptance artifacts are outside this report's scope.

The system verifies registration and records camp entry/exit for safeguarding and operational accountability. It is **not an activity, class, lecture, daily-session or percentage-attendance system**. There are no absence penalties or requirements to scan for activities.

Three independently usable modules:

| Module | Responsibility | Dependencies |
| --- | --- | --- |
| A — Participant portal and identification | Scoped access to existing registrations; individual digital/printable IDs | Existing registration/payment/recovery infrastructure |
| B — Verification and movement | Staff verification, arrival, temporary exit, return, final departure, safety oversight | Existing participant records; can provision its edition enrollment without requiring portal/ID issuance |
| C — Optional QR enhancement | Resolve an opaque credential into the same staff verification screen | Separately approved extension of A/B; never required by either |

QR remains absent from A/B releases. Manual participant/reference search and readable individual ID numbers must support all core operations. A digital ID is identification evidence, not payment proof, entry entitlement, guardianship proof or departure authorization.

## 2. Findings from the actual codebase

| Existing implementation | Evidence and consequence for 1L |
| --- | --- |
| Django user model | `backend/accounts/models.py`: `User(AbstractUser)`; retain these staff identities, not a second staff database. |
| Participants | `backend/dic/models.py`, `Participant`: UUID PK, name, date of birth and contact/demographic fields. No portrait, guardian relationship, collector authority or movement fields. Reuse participant UUIDs; do not assume photographs exist. |
| Multi-participant registrations | `RegistrationOrder` belongs to a `PrimaryRegistrant` and edition; `RegistrationOrderItem` links each participant/category and immutable snapshots. Uniqueness is `(order, participant)`, **not `(participant, edition)`**. A primary registrant is a payer/contact, not an established guardian or authorized collector. |
| Existing statuses | Order: submitted/confirmed/cancelled. Payment: pending/paid/failed/refunded. There is no authoritative dispute/chargeback or safeguarding-hold model. Do not invent such an existing status or infer that all disputes are captured. |
| Verified settlement | `backend/dic/payment_views.py`, `_apply_verified_transaction`: locks order then payment attempt; validates provider reference, amount, currency, transaction identity, trusted completion time and accepted price window; handles reconciliation/idempotency. Preserve this authority. |
| Eligibility precedent | `backend/dic/allocation.py`, `paid_participants`, and `operations_api.py`, `_verified_order_queryset`: confirmed order + paid flag + successful attempt for that order/edition. A manually edited paid flag is insufficient. Do not confuse a successful historical attempt with an order currently refunded/cancelled. |
| Existing order access | `backend/dic/access.py`: expiring/revocable, hashed bearer order credential checked with constant-time comparison. `security.py` currently provides 32-byte random credentials and a 30-day order expiry. These are order-access capabilities, not staff sessions or collection authority. |
| Recovery | `recovery_views.py`, `recovery.py`, recovery models: contact verification, rate limits, encrypted delivery, short-lived grants scoped to orders and one-time order restoration/credential rotation. Reuse delivery/security primitives; do not silently broaden recovery grants into safeguarding permissions. |
| Public frontend API | `dawana-platform/src/services/dicApi.js` uses order/recovery bearer headers with `credentials: 'omit'`. `DIC.jsx` holds access/recovery credentials in component state. A persistent participant portal requires an explicit new, scoped session design; it does not already exist. |
| Staff portal | `operations_api.py`: Django SessionAuthentication, CSRF login/logout, no-store responses, separate operations/finance/contact/export/audit permissions. `Operations.jsx` has protected real-data views. Extend it without replacing it. |
| Groups | `setup_dic_staff_roles.py`: Registration Staff, Finance Reviewers, Administrators; provisioning changes groups, not memberships. Administrators currently receive **all DIC permissions**, including new ones on rerun. Future safety permissions therefore require an explicitly reviewed provisioning change, not an unexamined rerun. |
| Audit | `DICAdminAuditEvent` records actor/action/target/details/time; model save/delete reject mutation of existing records. QuerySet/raw SQL can bypass model methods: this is not database-enforced tamper-proof evidence. New movement evidence needs stronger write controls. |
| Exports | `operations_exports.py` and `OperationsReportView`: python-docx, CSV formula protection, permission-scoped rows, auditing and 5,000-record bounds. Reuse these patterns with movement-specific projections and restricted sensitive fields. |
| Theme/accessibility | `public/appearance.js`, `public/theme.css`, `AppearanceControls.jsx`, `theme-polish.css`, Admin overrides: shared Light/Dark/System and reading preferences. New screens must consume these tokens/controls. |
| Migrations/tests | Latest code migration is 0013 (permissions, provider evidence fields, administrative audit model). Existing tests include operations, portal, recovery, allocation, acceptance and Admin appearance. No movement, guardian/collector authorization, participant portal session, digital-ID or QR models/routes were found. |

These findings are from repository inspection. No fresh database read or full test run was needed for this documentation-only task; prior validation reports are historical evidence, not a new 1L test result.

## 3. Domain boundaries and identity

Create one **CampEnrollment** for an existing participant in an edition. This is an edition participation record, not another participant/person record. Module B can create it transactionally on first staff verification; Module A can provision the same unique enrollment on eligible ID issuance. A shared service handles both paths.

Preserve original order items. Select and record the order/item supplying current eligible registration evidence. If several items for the same participant/edition conflict, stop automatic admission/ID activation for review rather than choose the newest or combine incompatible financial evidence. Multiple clean eligible items may be resolved explicitly to one source without duplicate stays. If separate participant UUIDs might represent one person, flag a possible duplicate for authorized human review; never automatically merge names, phone numbers or dates of birth. A later identity-resolution policy is separate from payment settlement and does not erase historical references.

Keep these independent facts visible:

1. Registration/payment eligibility, evaluated now from authoritative records.
2. Staff's recorded identity check and its evidence/method/time.
3. Collector/guardian authority and single-departure approval.
4. Current **recorded** camp-location state and unresolved discrepancies.

Neither a payment receipt, OTP, public ID nor QR can substitute for the other checks. Recorded on-premises population is not a sensor-confirmed physical census; show last reconciliation time and unresolved observations prominently.

## 4. Proposed models and migrations

Names are provisional. Use the existing `dic` app and database; all new FKs to participants, editions and historical order items use `PROTECT`. Staff references retain actor identifiers/display snapshots if an account is later disabled/deleted under approved policy. Sensitive snapshots are minimal, not wholesale copies of participant JSON.

### 4.1 Phase A data

| Model | Proposed fields and rules |
| --- | --- |
| `CampEnrollment` | UUID; participant; edition; selected source order item; random readable `public_number`; created_at; staff identity-resolution reference if applicable. Unique `(participant, edition)` and unique public number. Source item must refer to that participant/edition; category/order edition consistency checked by service plus DB constraint trigger where cross-table validation is required. Enrollment existence does not assert payment or presence. |
| `ParticipantPortalGrant` | UUID; digested opaque session handle; verified contact digest/channel; authentication time; expiry; revocation time; audience=`participant_portal`; authorization version. No staff privileges. Separate explicit scope rows link grants to allowed orders/enrollments and allowed views. |
| `ParticipantPortalScope` | Grant; order/enrollment; scope type, authorizer/provenance, valid-from/to; unique grant/scope target. Viewing a booking and accessing additional guardian-sensitive material are separate scopes. Custody/access restrictions can revoke scopes without deleting registration. |
| `DigitalIDIssue` | UUID; enrollment; issue version; non-authenticating printed ID number; issued_at/by; revoked_at/by/reason; branding/template version. Unique `(enrollment, issue_version)`; partial unique active ID per enrollment. Reissue revokes the earlier issue under lock. Runtime eligibility remains separate. |

A denied/revoked/unpaid registration may still be visible to its properly authorized booking accessor with a clear non-eligible status, but must not receive an active eligible-participant ID. No child `accounts.User` is required. Do not change existing order-token expiry or public checkout contracts to implement portal grants.

### 4.2 Phase B data

| Model | Proposed fields and rules |
| --- | --- |
| `CampMovementPolicyVersion` | Edition; immutable version; approved_by/at; configured age rule/reference date; permitted hours; departure approval requirements; expected-return rules; emergency/reopen policy; retention/access choices. Unique `(edition, version)`; published versions immutable. No permissive default for unknown minor status or unpublished policy. |
| `CampSafetyHold` | Enrollment; reason code; sensitive case reference; scope (`admission`, `departure`, `identity`, `portal`); opened_by/at; append-only disposition records. Financial discrepancies can reference evidence without falsely changing provider payment status. Explicit resolution only by the corresponding authorized reviewer. |
| `GuardianAuthority` | Enrollment; adult name/contact in restricted storage; relationship claimed; independent authority-verification method/reference; checked_by/at; valid scope/time; restriction/case reference. Record amendments/revocations as new versions/events. Merely supplying a name/contact does not establish authority. |
| `AuthorizedCollector` | Enrollment; linked verified guardian/authority; collector name, relationship and minimum identity-verification details; validity window; permitted departure kinds; approval/revocation evidence. A guardian may designate a collector only under approved policy; registrant/payer is never silently converted into one. Do not store full identity-document copies/numbers by default. |
| `DepartureAuthorization` | UUID; enrollment; departure kind; reason; collector version reference; expected_return_at for temporary leave; authorization validity; policy version; creator; approval records; revocation events. Immutable request snapshot. `DepartureApproval` stores approving staff, scope, decision and server time; unique approval role/actor slot as policy requires. Actual consumption is a separate one-to-one record tied to one effective departure, not a reusable flag. |
| `CampStay` | One-to-one enrollment; stream_version; effective_revision; materialized recorded_location; last effective event; current open leave/expected return; discrepancy flag. One stay per enrollment. A rebuildable projection, not freely editable truth. Not a new person record. |
| `CampMovementEvent` | UUID; stay/enrollment; edition; one of the four movement types; monotonic sequence; server recorded_at; responsible active staff account and identifier snapshot; verification reference; authorization/collector/policy-version reference where required; reason code; expected_return_at; prior/effective state evidence; request correlation. No update/delete by ordinary operators or Admin. |
| `CampStayRevision` and `CampStayRevisionEntry` | Append-only revision header linked to prior revision and approved correction/reopen action; entries give the complete ordered list of effective original/replacement movement event IDs. Unique `(stay, revision_number)` and `(revision, position)`/`(revision, event)`; same-stay integrity required. Old revisions remain intact. Latest committed revision is the authoritative effective history. |
| `CampExceptionalAction` | Correction or reopen request; reason/case; prior version; requested event changes; requester; independent approving staff where required; approved_at; resulting revision reference; previous final-departure event for reopen. Action type is **not** a fifth movement type. |
| `MovementCommandReceipt` | Actor/stay/operation; idempotency-key digest; normalized request fingerprint; committed event/revision reference and safe response. Unique `(actor, idempotency_key_digest)`; reusing a key with another participant/payload is rejected. Retain for an approved retry window. |
| `CampSafetyIncident` / `CampIncidentEntry` | Enrollment when known; edition; type (overdue, missing, unauthorized/unrecorded exit, disputed collector, emergency, uncertain presence, outage); opened_by/time; restricted notes and append-only observations/actions/resolution. Unknown-person observations get a case reference until matched to existing records; do not create duplicate participants to close a case. |

Cross-table equality, authorization sufficiency and movement sequencing cannot be guaranteed by Django `CheckConstraint` alone. Use explicit FK/unique/check constraints for local invariants, service validation inside row locks for policy rules, and migration-installed database triggers for evidence immutability/cross-table integrity where approved. Do not present `model.clean()` or a disabled Admin edit button as complete enforcement.

### 4.3 Constraints, indexes and migration sequence

- Store UTC aware times; display Africa/Lagos with timezone labels. `recorded_at`, approval/verification times and actor come from the server, not submitted identities or browser clocks. A reported earlier observation is stored separately with source/confidence and never overwrites server recording time. Expected-return time is staff input validated against policy, not an evidence timestamp.
- DB checks enforce valid four movement types, nonnegative stream/revision numbers, valid issue/revocation order, expected_return_at on temporary-exit requests/events, and consumed authorization uniqueness. Local FK combinations must be validated on insert and protected from later reassignment.
- Add indexes `(edition, recorded_location)`, `(edition, discrepancy_flag)`, `(stay, sequence)`, `(edition, recorded_at)`, authorization validity/status and outstanding expected returns. Enforce unique sequence per stay and partial unique active credential/ID as applicable.
- Proposed **0014**: additive A/enrollment/access/ID tables and explicit permissions; depends on actual 0013. Proposed **0015**: additive B policy/safeguarding/stay/event/revision/incident/receipt tables, constraints, indexes and reviewed DB guards. Actual migration names/numbers must be checked again at implementation time.
- No automatic paid/admitted/guardian/collector backfill. Enrollment materialization is idempotent and does not assign staff roles, mint active IDs for unpaid records or import historical movements from payment/allocation status.
- Treat published movement evidence as non-destructively reversible only through new revisions; rolling back schema after real evidence exists requires a separate retention/recovery plan, never dropping event tables casually.
- Optional C schema is a later, separately approved migration. No QR columns, scanner package or camera permissions are required by 0014/0015.

## 5. Participant portal access and digital IDs

Proposed frontend namespace: `/dic/participant`. Existing registration/recovery screens remain intact. Module A initially supplies booking-scoped read access and IDs, not public exposure of a child's location, collector identity or emergency notes.

1. Use the existing verified recovery-channel delivery/rate-limit mechanisms with an explicit portal audience and generic responses that do not reveal whether a child/booking exists. Recheck channel configuration; do not pretend a delivery provider is available.
2. Issue a new short-lived, scoped `ParticipantPortalGrant` after contact proof and approved scope resolution. Do not treat possession of an order bearer token as guardian/collection proof. A recovery-verified registrant may view the booking it already controls; added sensitive scopes need separate authority verification.
3. Use an opaque, rotated server-side grant handle bound to a Django session namespace and an HttpOnly cookie. Keep participant principal/scopes separate from Django staff authentication keys; never make a portal grant satisfy `request.user`/operations permissions. Staff-session coexistence must be tested explicitly.
4. Use Secure cookies in production, appropriate SameSite, CSRF for mutations/login/logout, session rotation, expiry/revocation checks on every request, rate limits and no-store responses. No portal bearer credential in URLs, localStorage, sessionStorage, exported files or printed IDs. Shared appearance preferences may remain in localStorage.
5. Logout revokes the grant; reauthentication can rotate it. Contact/authority changes can revoke affected scopes and sessions. A contact match must not expose unrelated orders beyond the verified existing scope and applicable access restrictions.

Issue one individual ID per eligible enrollment, even when a family paid together. Show approved official Dawana logo, participant display name, readable individual number, edition/dates and optionally permitted category/house information. Omit DOB, address, phones, guardian/collector data, finance details, recovery tokens and movement history. No photo placeholder implying verified likeness is required. Warn staff on the live verification screen that printable copies may be stale, shared or forged.

Use responsive digital display and browser print styling (individual card/print sheet). The number supports exact manual search but grants no data access without staff/portal authorization. Reprinted current versions do not duplicate participants. Replacement/revocation is audited; staff see current issue status. If payment becomes ineligible, suppress new eligible-ID downloads and show an ineligible result on live lookup; existing paper cannot be remotely erased.

The approved logo is currently referenced externally by `SiteChrome.jsx`; the prior implementation found no verified standalone local asset. Module A ID branding needs the approved original asset supplied/verified before release. Do not invent a logo or scrape/crop an unverified substitute. Missing logo is a delivery dependency, not permission to generate a fake one.

## 6. Registration eligibility and staff verification

Implement a shared read-only evaluator returning `eligible`, structured reason codes, checked_at, source order/item/attempt IDs and policy version. Reuse verified-settlement meaning across A/B rather than copying divergent queries into each view. Never call Paystack or take payment as a side effect of a lookup or movement command.

Normal initial arrival/active ID requires:

- Existing participant and matching edition/item; no unresolved duplicate/source ambiguity.
- Source order currently confirmed and paid, with a successful verified payment attempt belonging to that exact order. Verify the durable settlement evidence expected by the existing payment service; investigate legacy incomplete evidence rather than invent values or manually mark successful.
- No current cancellation/refund, relevant unresolved reconciliation/dispute/chargeback hold or identity/admission restriction. A failed or duplicate later attempt alone must not negate a valid settled order; classify evidence rather than blocking on any non-success attempt.
- Staff identity verification for admission, within approved operational dates/hours/policy. Public registration being closed is **not** a reason to reject already eligible campers arriving during camp. Allocation absence is an attention item, not automatic payment failure or fabricated house assignment.

Because there is currently no dispute ingestion, Phase B must not claim automatic detection of all provider disputes. Agree how finance records/receives a dispute and opens a safety eligibility hold. Financial reviewers resolve the financial issue through existing trusted mechanisms; gate staff cannot override a paid status or alter provider evidence.

Search by individual number, order reference or name, with category/edition and constrained supporting details to disambiguate. Contact search/details retain separate permissions. Log staff verification outcome/method without copying identity documents. Opening the record is not recording an arrival; mutations require an explicit confirmation and idempotency key.

**Safeguarding is not a debt-collection mechanism.** A new financial hold must not prevent recording a real return, emergency exit or safeguarding action. A RETURN from authorized leave records the return and raises the current eligibility/identity issue for supervisors. No one is silently changed to absent, deleted from the safety population or refused factual documentation because payment changed. An initial ineligible/unknown arrival is recorded as a restricted incident/observed presence pending supervised safe handling; any exceptional admission authority is separately approved and never changes financial eligibility.

## 7. Movement state machine

Use four event types only. Derived recorded-location states are `NOT_YET_ARRIVED`, `ON_PREMISES`, `TEMPORARILY_OFF_PREMISES`, `FINAL_DEPARTED`. Missing/overdue/uncertain are separate safety flags/cases, not invented routine movement events.

| Current state | Event | Next state | Required checks |
| --- | --- | --- | --- |
| NOT_YET_ARRIVED | INITIAL_ARRIVAL | ON_PREMISES | Current eligibility; staff identity verification; arrival policy |
| ON_PREMISES | TEMPORARY_EXIT | TEMPORARILY_OFF_PREMISES | Valid one-use authorization, required approvals/collector checks, reason and expected return |
| TEMPORARILY_OFF_PREMISES | RETURN | ON_PREMISES | Match open leave; staff identity check; record truthful return even if financial eligibility changed, with escalation |
| ON_PREMISES | FINAL_DEPARTURE | FINAL_DEPARTED | Final-release authority and collector checks where applicable; explicit closure confirmation |
| FINAL_DEPARTED | Any ordinary movement | Rejected | Separately authorized reopen procedure required |

Every unlisted transition is rejected as a routine command: repeated arrival, exit before arrival, two exits in a row, return while already inside, departure before arrival, and post-final normal reentry.

Final collection while already temporarily off-premises is **not** recorded by inventing a RETURN. Proposed exceptional off-site closure requires supervisor authorization, confirmation of participant whereabouts/collector custody and audit evidence; it appends FINAL_DEPARTURE from the off-premises state with a distinct exception reason/authority and closes the open leave. This is disabled until that policy is approved. Otherwise the case stays off-premises and open for resolution.

Each temporary exit pairs with exactly one effective return or approved exceptional off-site final closure. Expected returns derive from the currently open effective leave. At camp end, do not auto-final-depart everybody: remaining on-premises/off-premises records are unresolved operational items until staff document outcomes.

### Reopening after final departure

A supervisor submits an explicit reopen request referencing the effective final event, reason and current safety/identity assessment; a separately authorized approver grants it under approved policy. Keep FINAL_DEPARTURE in the original stream and revisions. The reopen action establishes a new stay segment whose baseline is NOT_YET_ARRIVED, with no implication that the person has physically reentered. A fresh INITIAL_ARRIVAL is required for actual reentry. It uses the same enrollment/stay aggregate, a new segment reference, and fresh eligibility checks. This is not a fifth normal movement event or an ordinary gate-staff toggle.

## 8. Transactions, idempotency and concurrent commands

One service layer owns all commands from React, Admin and optional future QR workflows. No frontend-calculated state or writable Admin status fields can bypass it.

1. Authenticate the staff session, enforce CSRF/action permission and validate bounded input. Identify enrollment/source evidence without trusting a submitted order/participant pairing. Enrollment creation races use the DB unique constraint and retry/reload.
2. In `transaction.atomic`, lock relevant source `RegistrationOrder` rows in ascending PK order, then enrollment/stay, then authorization/collector/hold rows in a documented consistent order. This is compatible with the existing payment path's order-before-attempt lock ordering. Future cancellation/refund/hold services must participate in the same protocol. Revalidate source selection and evidence **after** locking; retry if it changed. Do not hold DB locks across provider requests.
3. Check the unique command receipt: same actor/key/fingerprint returns the committed result without another event or repeated authorization consumption; key reused for a different payload conflicts. Serialize receipt insertion under the stay lock and handle unique-key races across stays with rollback/retry of the winner's stored result.
4. Require `expected_stream_version` (or equivalent If-Match); reject stale screens with 409 and current safe state. Re-read effective history/projection, current policy/identity and departure approvals. A cached eligibility badge is not sufficient.
5. Validate the transition and authorization; append the event, consume authorization uniquely, append the effective revision/entries or advance the current valid revision, update the materialized projection/version, insert receipt and administrative audit reference in the **same transaction**. For clarity, the authoritative choice is immutable revision headers/entries: ordinary movement appends a new revision containing the prior effective entries plus this event. Never mutate a published revision in place.
6. Commit before returning success. Dispatch alerts/export notifications with `transaction.on_commit` and a durable outbox when reliable delivery is required. Notification failure cannot erase a movement or authorize a release.

An exit and final departure submitted concurrently cannot both consume the ON_PREMISES state: one commits, the other conflicts. A refund racing admission is serialized against the source order; if refund commits after arrival, the stay remains recorded on-premises and becomes an attention case, never retroactively absent. Hold creation/resolution and collector revocation must lock the same stay/authorization path so stale approvals cannot be consumed.

## 9. Minor safeguarding and collection

Minor age threshold, legal/policy authority, reference date, age verification, collection evidence and approver requirements are **organizational decisions requiring approval**. Do not assume a specific legal age or determine guardianship solely from the booking. Compute age deterministically from verified DOB and the published policy reference date, record the version and fail closed on uncertain age for routine release. Do not silently switch rules on a birthday mid-stay.

Proposed workflow:

- Safeguarding staff verify guardian authority independently of payment/contact possession and record restricted evidence references. Requests/custody restrictions remain confidential; ordinary operators only see that approval is required or blocked.
- An authorized guardian/collector arrangement specifies participant, edition, collector, scope and dates. A registrant may propose a collector, but their proposal is pending until verified; an OTP proves contact control, not guardianship or the collector's physical identity.
- For each temporary/final departure, staff create an immutable departure request: participant, exact action, reason, collector version, expected return if temporary and valid window. Required staff approve it; gate staff recheck collector identity at handover and confirm the exact participant/action. Approval alone does not move the person.
- Default proposal for high-risk minor release, emergency exception, correction or reopen is two distinct authorized actors (requester/approver separation). The organization must approve staffing feasibility for 1–3 operators and a documented fallback. Do not silently reduce approval count because only one staff member is logged in. A superuser does not bypass these service-level safeguarding invariants.
- Gate confirmation consumes the authorization once and creates movement/approval evidence transactionally. Revocation, changed collector, expired authorization, new hold or changed policy invalidates use and requires review/reapproval. Do not reuse a temporary-exit approval for final departure.
- RETURN matches the active leave; verify the returning participant and close that leave. Do not demand the original collector as the only possible escort unless approved policy requires it. An escort discrepancy is documented/escalated, not a reason to leave a known return unrecorded.
- Final collection requires current authority even at official camp closure. Age/authority uncertainty triggers safe supervised handling; scanning a QR never authorizes release.

Emergency life-safety action must not be delayed while trying to complete an electronic form. Authorized safeguarding staff follow an approved offline/emergency procedure, then record factual observation, actual responsible adults, reason and incident reference promptly. Emergency documentation is not a payment override, a reusable collector approval or a way to hide a routine unauthorized release.

## 10. Corrections, incidents and discrepancies

### Corrections without destroying evidence

Do not edit/delete original movements, approval decisions, evidence times or published revisions. A correction request names the mistake and proposes a new effective ordered history using original events plus explicit replacement events. Replacement events carry server recorded_at plus any separately evidenced reported occurrence time; the original timestamps remain available.

Authorized reviewers lock the stay, validate the **entire proposed sequence** from the segment baseline, verify collector/approval consequences and append a new immutable `CampStayRevision` and its ordered entries. The correction action references omitted/superseded events and reasons; raw originals remain in the audit view. Recompute state, open leave, overdue alerts and counts from this revision in the same transaction. If later movements depend on the mistaken event, a single-event void that creates impossible history is rejected; the reviewer must submit a coherent complete correction plan. No silent cascade voiding and no fictional physical events inserted just to satisfy the reducer.

Authorization consumption is historical evidence. Correcting a mistaken departure does not silently make its approval reusable. Any replacement approval/consumption is explicitly reviewed and linked; ordinary gate staff cannot reset it. A correction records evidence interpretation, not permission to release someone now.

### Incident workflows

| Situation | Required behavior |
| --- | --- |
| Overdue expected return | Derive from an open temporary exit whose expected_return_at is past server now, using configured grace/escalation policy. Open/deduplicate an alert/case by leave; acknowledgement is not return. Keep visible until effective return/approved closure or clearly documented disposition. |
| Unauthorized/unrecorded departure | Open a restricted safety incident immediately. Retain last valid recorded state and prominently mark location uncertain; record last-seen/reported location separately. Do not fabricate a normal authorized exit or assert physical presence solely from the old state. |
| Missing participant / uncertain presence | Display discrepancy count with the recorded population; reconcile by supervised physical checks. Restrict names/details to safety roles. Case resolution documents evidence and any approved history correction. |
| Emergency lookup | Named permitted staff enter a reason; return minimum necessary emergency contacts/restriction indicators for that enrollment, with actor/time audit. No mass export, unauthenticated endpoint or unrestricted search dump. |
| Collector dispute | Block routine release and escalate through approved safeguarding contacts. Financial staff and booking token holders do not resolve authority by default. |
| Network/device outage | Use an approved secure numbered manual log, verified handover procedures and communication between gates. Do not queue offline auto-approved exits on phones. Reconcile via an authorized import/correction workflow with original paper reference and server recording time; disclose the stale dashboard. |
| Participant physically returned but electronic state is wrong | Record an incident/observation immediately and seek a validated correction or appropriate RETURN. Safety staff must see observed/uncertain presence alongside ledger state; never discard the observation because it fails the normal state machine. |

No automatic absence penalties, deletion of missing people or automatic movements triggered by time, geolocation, payment changes or alerts.

## 11. Staff permissions

Retain existing operations, finance, contact-view/export and audit permission boundaries. Add action-specific permissions, reviewed before assignment:

| Proposed permission | Allowed scope |
| --- | --- |
| `can_verify_dic_registration` | Manual identity/registration verification; no settlement changes |
| `can_record_dic_arrival_return` | Initial arrival/return via service, policy and current state |
| `can_request_dic_departure` | Create requests; cannot self-authorize restricted release |
| `can_record_dic_departure` | Confirm approved handover/consume authority; cannot create approval implicitly |
| `can_manage_dic_collectors` | Restricted guardian/collector verification and revocation |
| `can_approve_dic_departure` | Approve policy-permitted departures with actor-separation checks |
| `can_view_dic_movement` | Edition-scoped movement records and permitted population views |
| `can_view_dic_safeguarding` | Restricted cases/restrictions; not automatically all contact exports |
| `can_use_dic_emergency_lookup` | Reason-bound, audited minimum emergency details |
| `can_correct_dic_movement` / `can_approve_dic_movement_correction` | Request/approve coherent correction revisions |
| `can_reopen_dic_stay` / `can_approve_dic_stay_reopen` | Separately authorized exceptional reopening |
| `can_export_dic_movement` | Bounded movement reports, with separate existing contact-export gate |
| `can_manage_dic_digital_ids` | Issue/revoke IDs after eligibility checks; no collection authority |

Do not assign new privileges automatically to existing users/groups. Update provisioning to explicitly distinguish technical configuration from safeguarding powers, including the current Administrators all-DIC-permissions behavior. Existing accounts can combine approved roles; avoid departments or an unnecessary hierarchy. An operations permission is a prerequisite for staff portal access, but not sufficient for movement/release. Contact viewing and exporting remain separate. Hide unauthorized links **and** enforce permission/object scope on every backend endpoint.

## 12. Proposed API contracts

All routes below are proposals, not implemented endpoints. Edition/enrollment must be authorized server-side. Staff endpoints require the existing Django session, CSRF on mutations and action permissions. Participant endpoints use the separate portal principal/scopes; ID possession is never an API permission.

| Namespace and endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/v1/dic/participant/auth/challenges/` | POST | Purpose-scoped contact challenge; generic response/rate limits |
| `/participant/auth/verify/` | POST | Verify challenge, rotate/bind portal session |
| `/participant/auth/me/`, `/participant/auth/logout/` | GET / POST | Scoped principal and revocation/logout |
| `/participant/enrollments/` | GET | Only permitted booking/enrollment summaries |
| `/participant/enrollments/{id}/id/` | GET | Authorized current ID rendering/print; live eligibility check |
| `/operations/enrollments/` | GET | Search/filter/paginate; individual number, reference/name |
| `/operations/enrollments/{id}/verification/` | GET / POST | Current eligibility result / explicit staff identity-verification record |
| `/operations/enrollments/{id}/movements/` | GET / POST | History / one of four normal event types, service-enforced |
| `/operations/enrollments/{id}/departure-authorizations/` | GET / POST | Restricted list/create request |
| `/operations/departure-authorizations/{id}/approvals/` | POST | Explicit approval decision; no physical movement |
| `/operations/departure-authorizations/{id}/revocations/` | POST | Revoke unconsumed authority under lock |
| `/operations/enrollments/{id}/collectors/` | GET / POST | Restricted versioned collector administration |
| `/operations/enrollments/{id}/digital-id-issues/` | POST | Issue/revoke/reissue command with permission/audit |
| `/operations/enrollments/{id}/correction-requests/` | POST | Submit complete correction proposal |
| `/operations/correction-requests/{id}/approvals/` | POST | Validate/commit corrected revision |
| `/operations/enrollments/{id}/reopen-requests/` | POST | Separate exceptional reopening request |
| `/operations/reopen-requests/{id}/approvals/` | POST | Approved new segment, not automatic arrival |
| `/operations/safety/dashboard/` | GET | Recorded populations, overdue leaves and discrepancy counts/as-of |
| `/operations/safety/incidents/` | GET / POST | Restricted cases/observations; deduplicated alerts |
| `/operations/enrollments/{id}/emergency-lookup/` | POST | Reason-bound sensitive read, no-store and audit |
| `/operations/reports/movements/` | GET | Authorized CSV/DOCX report with validated filters and audit |

Abbreviated namespace rows inherit `/api/v1/dic`. A movement body contains event type, expected stream version, verification/authorization reference and permitted reason/expected-return input; never authoritative actor, derived state, payment status or server recorded_at. Require `Idempotency-Key` for mutations. Return safe updated state, event/revision/version and verification time. Use 409 for version/idempotency/transition conflicts, 400 for malformed input, 403 for missing permission and non-enumerating not-found responses where required. Unknown identifiers and sensitive decisions are not leaked through public search responses.

## 13. UI and operational workflows

Extend existing themed Operations routes with Verification, Camp Movements and Safety views. Keep existing registration/participant detail links; add a verification panel for each individual, not an order-level arrival button affecting all siblings.

- **Verification desk:** search manually; show clear identity, selected registration evidence, verified payment result, eligibility reasons and separate safety restrictions. Staff confirm the individual; a green payment badge alone does not confirm identity.
- **Initial arrival:** show permitted action, staff verification result and policy warnings; explicit submit records one arrival. Unallocated eligible campers are routed to existing allocation oversight without inventing houses.
- **Temporary departure:** request/approval/collector check/confirmation are distinct steps. Show expected return and consumed authority. Pending approval never changes population.
- **Return:** select the open leave, verify the individual, record return and surface any issue requiring safeguarding/finance review.
- **Final departure:** separate destructive-in-effect confirmation, current collector authority and closure warning; no bulk final-departure action for all members of an order.
- **Safety dashboard:** recorded on-premises, temporarily off-premises, not-yet-arrived and final-departed; overdue expected returns and unresolved uncertainty. Show totals as of server time/current effective revisions and filters. Authorized safety views include admitted/observed people whose payment later becomes ineligible. Never silently restrict the safety census to currently paid participants.
- **History:** chronological original evidence and current effective interpretation, correction/reopen annotations, staff/time, leave pairing and case links; restricted details omitted for ordinary viewers.
- **Emergency:** deliberate reason-bound entry point with minimum contacts and restrictions, not an unrestricted public search field.

Dashboards must declare their population denominator: enrollment counts differ from all registration items/orders. Provide an unmaterialized/ambiguous registrations queue so lazy enrollment creation cannot make eligible not-yet-arrived people disappear. Either materialize all resolved edition enrollments idempotently before gate opening or use an explicitly tested canonical registration-to-enrollment read model. Keep a separate eligible admission pipeline and inclusive safety population. Mutating filters do not create records.

Reuse normal document scrolling, accessible keyboard/touch controls, reduced-motion behavior, light/dark/system tokens and saved reading sizes. Tables use responsive horizontal wrappers, no fixed-height app shell. Print IDs need explicit readable print colours and suppression of navigation/theme controls. Status uses words/icons in addition to colour; show real zeros and honest unavailable/stale states.

## 14. Word/CSV reporting and privacy

Both the React portal and existing Django Admin must expose the same authorized filtered datasets in **DOCX and CSV**, reusing python-docx/CSV safety utilities. Proposed report types: arrival register, current recorded population, temporary exits/open leaves, returns, final departures, overdue returns and movement history; restricted incident/correction reporting requires extra safeguarding permissions.

Filters: edition, participant/category/house when appropriate, movement type, recorded-time range, current state, overdue status and authorized staff scope. Distinguish event-time reports from current-state/as-of snapshots. Include revision/as-of time so a corrected current report does not pretend to reproduce the original evidence. For historical reconstruction, select the revision known at the requested cutoff, not today's corrected revision without disclosure.

Common fields: individual reference, permitted name/category, edition, movement type, server recorded_at/timezone, permitted staff identifier, current recorded state and expected-return/overdue indicators. Exclude full DOB, health measurements, home addresses, guardian/collector document details, sensitive incident narratives and contact data unless an explicit authorized report schema requires them. Finance visibility does not imply safeguarding access; contact export still requires the separate export permission. No OTP, bearer/recovery/QR credential, raw session key, secret or provider authorization URL is exported.

Word: verified official branding, report title, edition, timestamp/timezone, filters/as-of/revision, totals, readable tables, suitable orientation/margins, repeated headings, footer and page fields; render/inspect all representative pages before acceptance. CSV: UTF-8, clear headers, stable identifiers, formula-injection protection. Use the same permission-filtered row projection for both formats, with record limits before materialization (reuse the 5,000-record guard initially). Larger exports require a separately designed bounded job, not removal of limits.

Audit each successful export with actor, format/report, edition, filters, revision/as-of and record count. Record denied/failed sensitive exports as appropriate without leaking query/contact secrets. Audit ID issuance/downloads separately; printed individual cards are not a bulk safeguarding report. Authorize before query enumeration or file creation and disable shared caching.

## 15. Audit, privacy and operational controls

- Append-only evidence plus materialized projections; database/service invariants protect mutations, and Admin evidence screens are read-only. Routine credentials must not have a supported API/ORM path to rewrite published movement evidence. Review DB triggers/roles and test QuerySet/bulk/raw-SQL mutation denial for protected evidence tables.
- Record actor, server time, action, target, request correlation, policy/verification/authorization/revision references and reason codes. Separate restricted evidence/notes from broadly visible `DICAdminAuditEvent.details`. Do not dump collector/contact/credential payloads into general logs.
- Apply least-privilege access to retrieval as well as changes; contact and safeguarding access are independent. Emergency lookup is audited and reviewable, with no silent self-granted break-glass permission. Background jobs use explicitly scoped service identities.
- Agree retention, deletion/anonymization, backup and subject-access handling before production. Do not invent a retention period or claim legal compliance. Keep movement evidence for approved accountability needs while minimizing sensitive identity-document storage; legal/organizational retention decisions remain open.
- Encrypt sensitive fields/backups using managed secrets where adopted; keep token digests, secure transport and revocation separate from appearance storage. Restrict device caches, print handling and downloaded safeguarding lists. Operational printouts have custody/secure-disposal procedures.
- Consider hash-linked ledger entries and restricted off-host backups as tamper-evidence enhancements; neither a hash chain nor model-level immutability prevents a privileged database operator from changing records. Define trusted administrative access and monitoring honestly.

## 16. Testing and acceptance strategy

No implementation tests were run for this architecture-only change. Future delivery must add tests before feature acceptance and rerun the existing backend/frontend checks.

| Area | Required cases |
| --- | --- |
| Identity/enrollment | Multi-participant order creates one ID/stay per individual; unique enrollment races; multiple source orders; same name is not automatic merge; cross-edition/order pairing rejected; no participant duplication. |
| Eligibility | Confirmed/paid/success evidence; manually edited paid flag; pending/failed/cancelled/refunded orders; reconciliation/dispute holds; duplicate-success attempt handling; missing legacy evidence; payment change while on camp; closed public registration does not block valid camp arrival. |
| Portal | Contact challenge abuse/rate limits; scope isolation across bookings/families; purpose-bound grants; replay/expiry/revocation/rotation; CSRF; HttpOnly/Secure behavior; no child account or staff privilege; shared-device logout; restricted custody/access changes. |
| IDs | Per-participant issuance; current eligibility; issue/reissue/revoke; readable number not authentication; no sensitive fields; no photographs assumed; print layout/multipage sheets; official-logo availability gate; works with no QR subsystem installed. |
| State machine | All valid transitions and all invalid pairs; many temporary exits/returns; late return; final closure; no arrival/departure from lookup alone; reopened segment needs new actual arrival; exceptional off-site closure disabled without policy. |
| Safeguarding | Registrant not assumed guardian; unauthorized/expired/revoked collector; wrong participant/action; one-use approvals; approval versus actual handover; self-approval separation; unknown age; emergency handling and policy version changes. |
| Concurrency | PostgreSQL TransactionTestCase with separate DB connections: simultaneous arrival, exit/return, exit/final, approval consumption, payment/refund/hold/collector revocation races, same/different idempotency payloads, correction versus gate command, authorization revocation versus departure; assert one coherent committed history and bounded deadlock retries. |
| Corrections | Original evidence retained; complete valid replay; invalid dependent sequence rejected; no silent approval reuse; historical as-of snapshots; reopen retains final event; projection rebuild equals stored projection. |
| Safety | Overdue boundary/timezone/grace behavior; deduplicated alerts; unknown/unrecorded departure; observations visible despite ledger conflict; admission hold does not erase safety population; outbox retries and offline reconciliation; no auto-final at camp end. |
| Permissions/privacy | Every endpoint and direct UI route; per-object scope; ordinary operator/contact/finance/safety separation; reason-bound emergency audit; cross-edition access; no sensitive data in broad audit/export/errors/cache. |
| Reports | Both formats, same rows/filters; actor/count audit; formula injection; bound enforcement; corrected/as-of interpretation; Word rendered headings/widths/wrapping/page fields; no token/collector-document leakage. |
| UI | Existing themes/reading sizes; keyboard/touch; desktop/tablet/mobile; explicit confirmations; stale-state 409 recovery; real empty states; one primary scrollbar; manual lookup fully supports every core workflow. |

Use isolated test accounts/data only. No fake registrations in the development operational dataset and no live provider payments. Browser-test when tools are available; otherwise record the limit and supply an exact manual acceptance plan. QR remains separately disabled in every A/B acceptance run.

## 17. Delivery phases and approval gates

**1L-A — Participant identity, portal and digital/printable IDs.** Approve audience/scope and logo asset; implement additive enrollment/access/ID models, secure portal session, per-individual cards and manual ID lookup. Preserve existing recovery/checkout. Acceptance: family multi-participant isolation, current eligibility, revocation, no child accounts and readable printed IDs without QR. Module B is not required to view/print an ID.

**1L-B — Verification and camp movement.** Approve safeguarding policy/authority/evidence/emergency/retention choices first. Implement transactional ledger/projections, permissions, guardian/collector and departure authority, four movement workflows, safety/overdue/discrepancy dashboard, revision corrections/reopen and DOCX/CSV reports. Acceptance includes real PostgreSQL race tests and a staffed safeguarding drill. No dependency on issuing or scanning IDs: manual existing registration lookup must work throughout.

**1L-C — Optional QR, only after separate organizational approval.** If ever approved, add a high-entropy revocable `QRIdentificationCredential` whose stored value is a digest, with issue version, enrollment binding, expiry and revocation metadata. QR encodes no sensitive participant data and no existing order/recovery/session token. Prefer an authenticated staff scanner page accepting the opaque code without putting it into analytics/referrer logs. An unavoidable scan-link token must be scrubbed from logs/referrers and exchanged safely, not exposed to third-party resources.

Resolution returns the same permission-filtered verification screen as manual lookup. A scan is read-only identification, never a movement, payment verification, approval or minor-release instruction. Staff still select/confirm every action; revocation and current eligibility checks apply online. Camera permission is requested only on explicit scanner use, with manual fallback and no mandatory third-party scanner service. The organization may permanently decline C without any loss of A/B functionality.

## 18. Open decisions requiring approval

1. Minor threshold/reference date, handling uncertain DOB/age and appropriate organizational/legal review; adult versus minor departure rules.
2. Guardian authority and custody-restriction verification, collector evidence, alternate collectors and minimum data retained. Confirm a payer/recovery-contact is not automatically authorized.
3. Required separation of request/approval/handover roles for each risk level and a feasible authorized emergency procedure for 1–3 operators; who may approve correction/reopening.
4. Temporary-leave hours, expected-return/grace/escalation windows, permitted reasons, supervisor contacts and arrangements after camp closure.
5. Policy for final closure while a camper is already off-premises, exceptional reopening, admission/payment disputes and documented safe handling of ineligible arrivals/returns.
6. Portal contact-access scope versus guardian-only information, access-restriction revocation, session duration/shared-device rules and availability of verified delivery channels.
7. Authoritative dispute/chargeback intake and reviewer workflow; no claim of automatic dispute coverage without an implemented source.
8. Duplicate registration/person reconciliation and source-item selection, plus complete not-yet-arrived population materialization before gates operate.
9. Approved official local logo asset, ID template/content, readable-number format and printed-card handling.
10. Sensitive-data retention, evidence/backup controls, permission assignments and a deliberate update to the current all-DIC-permissions administrator provisioning behavior.
11. Offline/manual gate procedure, reconciliation ownership, emergency access accountability and physical safeguarding drills.
12. Whether to approve QR at all. Absence of a decision means **C stays disabled and unimplemented**.

Review this proposal before any model migration, API implementation, new account/permission assignment or operational rollout. This task changes only this architecture document and performs no commit, push or deployment.
