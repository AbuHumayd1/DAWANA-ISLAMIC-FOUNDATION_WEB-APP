# Milestone 1L-A acceptance audit

19 October 2026. Source baseline: current working tree at HEAD `074c49b`, including the existing uncommitted/untracked 1L-A implementation. This is an audit, not implementation approval.

**Decision: substantial implementation exists, but production acceptance is withheld.** Existing tests cover important security boundaries; delivery configuration, identified defects and browser/print acceptance remain outstanding. No new features or fixes were implemented.

## Scope and evidence

Read `MILESTONE_1L_ARCHITECTURE.md`, `MILESTONE_1L_A_IMPLEMENTATION.md`, participant models/services/API, migration 0014, delivery/cleanup commands, recovery/security primitives, Operations permissions/routes, React participant/staff screens, API adapters, print CSS and relevant tests. Checked the development database read-only. Test fixtures run only in the separate PostgreSQL test database, not the application database.

The earlier implementation report is historical evidence. Its Light/Dark/System, reading-size and 15-test frontend descriptions are now stale following separately approved appearance changes. They are not missing 1L-A features. This audit does not change those approved appearance/navigation/homepage changes.

## Completed implementation

| Area | Implemented behavior and limits |
| --- | --- |
| Booking lookup/access | Full booking UUID plus registered primary email/phone; generic challenge responses; one booking per grant even when another booking shares a contact. Orders and individual participants are retrieved without creating IDs on GET. Participant contacts are not treated as primary booking owners. |
| OTP generation/security | Cryptographically random six-digit code, keyed digest, encrypted queued delivery payload, ten-minute expiry, browser binding, five committed verification attempts and one-time consumption. Separate challenge/grant tables prevent recovery/portal cross-authentication. |
| OTP request limits | Shared database-backed recovery contact/IP buckets: 60-second cooldown, five requests/contact/hour and 30/IP/hour, supplemented by DRF endpoint throttles. Portal and recovery deliberately share those buckets; operational impact must be understood. |
| Delivery | Existing email/SMS/WhatsApp adapters reused through a separate bounded portal worker; unknown/cancelled/revoked/contact-changed bookings are suppressed. No code returned to clients. Payload scrubbing and bounded expired-access cleanup exist. Live delivery is not accepted. |
| Participant session | Digest-only 32-byte random handle; 30-minute server-side expiry/revocation; dedicated HttpOnly, SameSite=Lax cookie under `/api/v1/dic/participant/`; Secure follows production session-cookie settings. CSRF on mutations and no-store responses. Does not log in or overwrite Django staff sessions. |
| Scope/authorization | Rechecks booking scope revocation, cancellation, order-access revocation and primary contact digest. A grant may remain authenticated with zero authorized bookings after scope/contact changes; it receives no booking contents. |
| Identity | Existing Participant UUIDs reused. One CampEnrollment per participant/edition, database-unique readable `DIC-{year}-{random}` number, bounded collision retry and participant-row locking. No duplicate person model or child account system. |
| Eligibility | Read-only checks for current confirmed/paid status, accepted current price revision, successful exact-order settlement evidence, amount/currency/provider identity/time and price-window validity. Legacy evidence and unresolved reconciliation/source ambiguity fail closed. |
| Digital ID lifecycle | Explicit initial POST, idempotent current-card reuse, versioned staff replacement, revocation, expiry and runtime eligibility checks. Number stays stable. No QR, photograph or camp-movement claim. |
| Staff lookup | Session-authenticated Operations endpoints plus explicit view/manage/source-review permissions. Search by number/name/reference, enrollment pagination, bounded candidates, prepare/issue/reissue/revoke/review flows. Default role setup excludes automatic new ID permission assignment. |
| Card data/print | Minimal allowlisted name/number/category/edition/dates/venue/house/version/branding data; omits DOB, contact, health, guardians and credentials. Responsive and A4 print CSS exists, with branding-pending notice. Rendered/physical output is unverified. |
| Integration | Public `/dic/participant` and protected `/dic/operations/participant-ids` routes point at the implemented APIs. Cookie/CSRF participant client is separate from existing checkout/recovery bearer access. Staff mutations reuse the Operations client. Existing registration/payment services were retained. |
| Audit | Request/rejection, authentication/logout, enrollment and ID lifecycle/source-review/card-access events exist. Audit is application-controlled, not database-tamper-proof. Search/list access has gaps described below. |

Module B movement, arrival/departure, guardian/collector authorization and optional Module C QR remain outside 1L-A. Their absence is not a reason to rebuild A. Booking access or an ID does not establish guardianship or permission to enter/leave camp.

## Outstanding findings and production priorities

### P1 ? Enrollment category integrity is incompletely guarded

Evidence: `backend/dic/migrations/0014_participant_portal_and_ids.py:108` onwards checks category edition only when an enrollment is inserted/updated. It protects source-item reassignment and order-edition reassignment, but installs no guard for changing `RegistrationCategory.edition`. Category Admin still permits editing edition, and category `clean()` does not prohibit reassignment of referenced categories. `participant_services.eligibility` checks the participant and order edition, but does not recheck the category edition.

An isolated PostgreSQL test-database probe confirmed this: moving a referenced category via `full_clean()` and `save()` succeeded; the category/enrollment editions differed afterward and `eligibility()` still returned true. Probe fixtures were rolled back. This is an integrity gap under a privileged write path, not a demonstrated public-user privilege escalation. Resolve before production; add database and service regression coverage. Do not edit an already-applied migration casually: determine an additive corrective migration after approval.

### P1 ? Worker lease handling can duplicate or invalidate OTP delivery

Evidence: `backend/dic/management/commands/send_dic_portal_messages.py:47` resets processing leases after 180 seconds. A batch of up to 100 records is marked processing at one time and then delivered sequentially. With the default limit of 50 and provider calls approaching the configured eight-second timeout, still-live queued work can exceed that lease. A second worker can reclaim it while the first is still working. `process_portal_challenge` sends outside the final row lock and has no ownership/fencing check before sending or completing.

This is a source-confirmed concurrency hazard, not an observed live-provider incident. Duplicate sends or an older worker overwriting delivery status can prevent verification. Agree safe claiming/lease ownership and failure recovery before scheduling multiple workers. Add slow-provider, overlapping-worker, crash/reclaim, consumption/resend-during-send and final-status tests. No production provider was called during this audit.

### P2 ? Staff lookup can become stuck loading

Evidence: `dawana-platform/src/pages/StaffParticipantIDs.jsx:32` clears `data` on every submit, but requests are driven only by changes to `active` and `page`. Search the current term again on page 1 (including submitting the initial empty query): dependencies do not change, no request runs, and `data` remains null. The UI stays at its loading message. Failed initial/page requests also leave null data and the loading label without an explicit retry action. Successful later searches do not consistently clear previous errors.

This is confirmed from the state/effect flow, not browser reproduction. Fix request triggering and loading/error/retry handling; add component interaction tests.

### P2 ? Non-JSON upstream failures lose useful error handling

Evidence: `dawana-platform/src/services/participantApi.js:15` parses every non-204 response as JSON before checking status. An isolated fetch-mock probe with a 502 HTML gateway response produced a `SyntaxError`, with no preserved HTTP status, rather than a recoverable portal error. Staff API behavior should be checked under the same deployment failures.

Handle malformed/empty/non-JSON responses and failed CSRF initialization predictably; add status/error tests. No application endpoint or live data was modified by this probe.

### P2 ? In-flight responses need expiry/logout race coverage

Evidence: ParticipantPortal's expiry handler clears profile/orders/card, but `load`, verify and `openID` continuations have no request-generation/abort guard. A previously authorized request can finish after local expiry/logout and refill cleared state, including a card. This does not make the server accept an expired grant, but creates a shared-device display/privacy risk. Initial-load requests alone have an unmount guard.

Reproduce with delayed responses and resolve before production. Test expiry/logout/navigation against in-flight enrollment/card/verification responses. Present coverage does not establish race safety.

### P2 ? Access auditing and deployment limits need acceptance decisions

Staff search/list returns identity summaries and candidates without an explicit search/view audit event; participant booking lists also lack a read event. Individual card views and changes are audited. Confirm the required read-audit policy and close the relevant gaps before live identity use.

DRF throttles currently use the default process-local cache; the stronger database request buckets and locked five-attempt counter do exist. Test proxy client-IP handling and multi-process limits in the actual deployment rather than treating local DRF throttles as a global limit. Contact changes revoke access dynamically, but no first-class contact/authority-change revocation administration UI was added. Agree the authorized operational procedure; do not add guardian/safeguarding features implicitly.

## Operational release prerequisites

Read-only local findings:

- PostgreSQL; 0014 applied; migration history consistent, no model drift. Three expected triggers present.
- All three delivery channels unavailable; worker disabled; encryption key not configured; official ID logo URL not configured.
- DIC 2026 remains draft/closed. Paystack mode remains test.
- Application counts: one existing user; zero participants, orders, payment attempts, enrollments, challenges, grants and ID issues. No real account or registration was created by the audit.

Before production, configure an approved delivery channel and encryption/key handling, arrange safe worker/cleanup scheduling and monitor failures without exposing codes or contacts. The adapters exist, but mocked tests do not establish real delivery, spam-folder behavior, retries, provider template approval or availability.

Supply/verify the original official logo and accept the digital/printed ID. Merely configuring `DIC_OFFICIAL_LOGO_URL` makes `branding_verified` true in code; it is not technical evidence that the logo has been approved. Obtain human branding approval.

Review actual role assignments, HTTPS/cookie/CSRF/origin/proxy behavior, deployment cache and retention/backup procedures in an isolated staging environment. Current migration checks establish the local PostgreSQL state, not a clean production restore/migration rehearsal or SQLite compatibility. 0014 contains PostgreSQL-specific trigger SQL and must not be casually reversed after evidence exists.

## Tests and validation from this audit

- Complete Django suite: **173 tests passed in 213.632 seconds**, using the existing separate PostgreSQL test database (`--keepdb --noinput`). The expected delivery-failure warning was emitted by a failure-path test, not a suite failure.
- Additional isolated PostgreSQL integrity probe: **1 diagnostic test passed in 5.700 seconds**, reproducing the category-reassignment defect; it was not added as a permanent test file.
- Frontend: **18 tests passed**, including four existing participant API/navigation/print-contract checks; frontend lint and production build passed.
- Django system checks: zero issues.
- Migration drift: no changes detected; applied-history consistency check passed; 0014 applied.
- Additional non-JSON 502 probe: reproduced the error-handling defect above.
- `git diff --check`: passed, with an existing LF/CRLF advisory.
- `.vscode/settings.json` remains unchanged (SHA-256 `77E594534D02F33D324DBF54097A13EE3F5E3028E6410B3FB119347C2B714E12`).

Existing participant backend tests cover known/unknown booking responses, browser binding, expiry/reuse/attempt lockout, cooldown, channel unavailability, same-contact other-booking isolation, cookie/CSRF/session rotation and staff coexistence, card allowlists, paid/manual-paid/legacy/refund/cancelled cases, ambiguity/source guards, collision retry, issue singleton concurrency, permissions and cleanup. They do not fully cover each missing case listed below.

Missing or incomplete acceptance coverage:

1. Real delivery, failed delivery, full worker-command batching, lease reclaim and concurrency; resend invalidation across timing races; exact contact/IP hourly boundary and multi-worker throttle behavior.
2. Category reassignment after enrollment, production migration rehearsal, source review concurrent with issuance/refund, all three staff permissions independently including direct UI routes, and lookup pagination/search/error/retry cases.
3. Rendered component tests for repeat search, OTP resend/expiry/recovery states, delayed response races and printing after expiry/revocation. Current frontend tests are service/static contract tests, not rendered UI tests.
4. Screen-reader announcements and focus after form transitions/errors/card opening, keyboard-only workflow, mobile touch/overflow, slow-network loading and long-name card printing in both themes/grayscale.
5. Access audit completeness and retention/cleanup behavior under larger queues.

## Browser and manual acceptance

Managed browser inventory is empty (`apps=[]`, `browsers=[]`). No browser, screenshot, screen-reader or physical print acceptance was performed. Responsive CSS, labels, busy/alert/status elements, resend timer and print suppression were inspected in source only. Initial loading/error states are partly implemented; the staff loading defect remains.

After fixes/configuration approval, use an isolated test environment with existing authorized test contacts and fixtures. Test `/dic/participant` and `/dic/operations/participant-ids` at desktop/tablet/mobile, keyboard-only and both themes. Exercise unavailable channel, unknown booking, wrong/expired/reused code, resend, logout/expiry, staff-session coexistence, same-contact separate bookings, unpaid/refunded/cancelled/ambiguous sources, family individual numbers, issue/reprint/revoke/reissue and source restriction review. Inspect A4/grayscale print preview with long names and absent branding; verify no contact/credential/QR appears. Confirm existing DIC checkout/recovery and Operations permissions remain intact. Do not insert synthetic operational registrations.

## Changes made by this task

Only this audit report was added. No feature, bug fix, migration, configuration, theme, navigation or homepage implementation was changed. No database reset, development-data mutation, real message, account provisioning, commit, push or deployment was performed. Existing uncommitted 1L-A work is preserved. Await approval before implementing the findings.
