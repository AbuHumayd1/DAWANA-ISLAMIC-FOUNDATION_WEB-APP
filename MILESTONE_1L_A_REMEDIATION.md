# Milestone 1L-A defect remediation

19 October 2026. Remediation of `MILESTONE_1L_A_ACCEPTANCE_AUDIT.md`; existing unfinished 1L-A work retained. No new participant identity system, camp movement features, delivery configuration or operational accounts were introduced.

## Remediations

| Defect / root cause | Implemented correction | Focused regression evidence |
| --- | --- | --- |
| Category edition could change after enrollment; original source trigger ran only when enrollment/source records changed. Runtime eligibility trusted the category relationship. | Category model validation rejects moving a category referenced by registrations. New additive migration **0015_guard_registered_category_edition** installs the corresponding PostgreSQL trigger, including protection against save/QuerySet/raw SQL bypass. The enrollment source trigger takes a shared category-row lock. Enrollment domain validation includes category edition; preparation and fresh-source eligibility checks fail closed on mismatches. | Original category move reproduced in a test and now rejected by `full_clean`, direct save and QuerySet update; existing number/issue remain unchanged. Category name correction still works. A simulated legacy inconsistent source is rejected by the evaluator and enrollment validation. |
| Age-based batch leases expired while messages were still awaiting/performing network delivery, allowing duplicate claims and stale status overwrites. | Replace batch leasing with a locked **per-message queued -> processing claim committed before sending**. Claimants use skip-locked row locking and only queued records may send. No automatic reclaim of processing messages, regardless of age. Replays skip the send/status write. Completion changes only its still-processing record and suppresses consumed/expired requests. Cleanup closes expired/consumed claims and scrubs payloads. | Concurrent PostgreSQL test holds the first worker in a simulated slow provider call, ages its claim past the old lease, then runs another worker and command. Exactly one adapter call, one sent result, no overwritten status. Also covers failed-send replay, abandoned old claim, cleanup and consumption during send. |
| Repeated staff searches did not change effect dependencies and cleared results forever; errors had no explicit retry/cancel state. | Add explicit search revision, cancellable latest-request resource and separate loading/error/cancelled states. Repeat query submits trigger a new request. New searches, page changes and unmount abort/invalidate older reads. Retry and Cancel actions added. Sensitive-change operations temporarily disable search/page changes so their refresh cannot restore an old query. | Controller tests repeat identical/empty searches, error then retry, empty results, latest-query-wins, cancel and unmount suppression. Existing service/permission tests continue to run. |
| Clients parsed JSON before safely handling HTML, empty or malformed responses; CSRF initialization trusted any token field. | Shared response/CSRF reader used by participant and Operations clients. Preserve HTTP status, provide a clear retry message, never render HTML gateway bodies, reject unreadable/unexpected success payloads and empty CSRF tokens. Keep binary exports on their existing blob path. Pass AbortSignal through staff reads and participant CSRF/API requests; cancelled CSRF initialization cannot launch a later stale mutation. | Both clients tested against 502 HTML, 503 empty, malformed 200 and null 200; bad/missing CSRF handling, status preservation, cancellation during CSRF and existing authentication/export paths covered by the suites. |
| Late participant enrollment/card/verification continuations could restore data after logout, expiry or navigation. | Request generation plus AbortController guards applied at response and state-commit boundaries. Invalidate on expiry/logout/unmount; clear sensitive UI immediately on logout/expiry. Check the server deadline before committing even if the timer has not fired. Ignore aborted old-session responses, including expiry events. Logout remains available while a participant read is pending. | Delayed generation/commit tests for enrollment/card/verification flows, invalidation/next-session isolation, elapsed deadline before timer and stale expiry-event suppression. |
| Identity list/search reads were not audited. | Add participant booking-list audit with grant reference and returned counts; staff ID-search audit with actor, page, counts and searched flag. Do not record search text, contact information, OTPs or credentials. Existing per-card and mutation auditing retained. | Authorized booking/staff reads emit expected records; denied staff request emits no successful-search event; audit details exclude the submitted search string and contact. |

### Delivery semantics and recovery

This implements **at most one application provider attempt per challenge**, not a promise of exactly-once delivery by an external provider. The existing adapters have no common provider-idempotency contract. Automatically retrying a claimed send after a crash could duplicate a message the provider already accepted.

A claimed message with an uncertain outcome is therefore never automatically requeued. It expires and cleanup suppresses/scrubs it; the visitor requests a fresh code through the existing rate-limited resend flow. A failed or uncertain send does not authenticate anyone. No raw code or destination is printed in worker output. Stop/drain old lease-based workers before starting this version; do not manually reset claimed rows to queued. Provider-level idempotency/reconciliation would require a separately reviewed adapter contract.

### Migration and data safety

- **0014 is unchanged.** 0015 depends on it and adds guards; it does not replace IDs, change registrations/payments, backfill data or delete records.
- Preflight rejects an existing enrollment/category mismatch with an explicit review error rather than silently rewriting history. Any existing mismatch needs an authorized data-resolution plan before rollout.
- Once referenced by registrations, a category stays in its original edition; an unreferenced category remains movable and ordinary name/fee edits remain possible under existing rules.
- 0015 was exercised in the isolated test database. It was **not applied to the application database**, in keeping with the instruction not to modify live application data. It is the sole pending migration there and must be reviewed/applied before relying on its persistence protection.
- Read-only application counts remain one existing user and zero participants, orders, enrollments and ID issues. No real staff account or message was created. No database reset or history rewrite occurred.

## Validation

- Focused Django remediation suite: **7 passed in 60.966 seconds**.
- Complete Django suite: **180 passed in 340.421 seconds**, using the separate PostgreSQL test database with `--keepdb --noinput`. The expected recovery delivery-failure warning came from the existing failure-path test; there were no test failures.
- Frontend complete suite: **26 passed**, including eight new remediation tests with additional input variants.
- Frontend lint: passed without warnings.
- Frontend production build: passed.
- Django system checks: zero issues.
- Migration drift: no changes detected. Applied history consistent; application database has 0014 applied and only 0015 pending. Migration plan checked without applying it.
- `git diff --check`: passed, existing LF/CRLF advisory only.
- `.vscode/settings.json` unchanged: SHA-256 `77E594534D02F33D324DBF54097A13EE3F5E3028E6410B3FB119347C2B714E12`.

Frontend regression tests exercise the actual API helpers and shared request lifecycle controllers; they are not browser/component-rendering acceptance. No new dependencies or test framework were installed. Browser and physical-print verification remain pending.

An intermediate full-suite startup caught a syntax error introduced while reformatting the new migration SQL for readability. It was corrected before the final run; no earlier migration or application database was changed.

## Files changed in this remediation

Backend:

- `backend/dic/models.py`
- `backend/dic/participant_services.py`
- `backend/dic/participant_api.py`
- `backend/dic/migrations/0015_guard_registered_category_edition.py` (new)
- `backend/dic/management/commands/send_dic_portal_messages.py`
- `backend/dic/management/commands/cleanup_dic_participant_access.py`
- `backend/dic/test_participant_remediation.py` (new)

Frontend:

- `dawana-platform/src/pages/StaffParticipantIDs.jsx`
- `dawana-platform/src/pages/ParticipantPortal.jsx`
- `dawana-platform/src/services/operationsApi.js` (required shared dependency)
- `dawana-platform/src/services/participantApi.js`
- `dawana-platform/src/services/apiResponse.js` (new)
- `dawana-platform/src/services/requestScope.js` (new)
- `dawana-platform/src/services/participantRemediation.test.js` (new)

Documentation: this report. Existing audit/architecture/implementation reports retained as historical records.

## Remaining deployment blockers

1. Review/apply migration 0015 with the normal backup/staging migration procedure; resolve any preflight mismatch explicitly. No automatic application-database migration was performed.
2. Configure approved delivery provider, encryption/key management and worker/cleanup scheduling. All channels/worker/encryption were unavailable at audit time and were not enabled by remediation. Accept the fail-closed fresh-code recovery procedure and perform authorized end-to-end provider testing.
3. Supply/verify official logo and accept ID content/branding, long-name A4/grayscale output and physical print behavior.
4. Complete real browser acceptance on participant and staff ID routes: repeat/empty searches, cancel/retry/rapid pagination, delayed responses, session expiry/logout during reads, keyboard/focus, mobile layout, both themes and shared staff/participant sessions. No connected browser surface was available during the audit; automated service/controller tests do not prove rendered usability.
5. Validate staging HTTPS, cookie/CSRF/origin/proxy setup, shared deployment throttling/cache, explicit role assignments, audit retention and operational monitoring. Database request buckets and per-challenge attempt locks remain intact; no live-security configuration was changed.

Homepage, theme and navigation styling were not modified. Registration remains closed and live payments remain disabled; existing registration/payment logic was not changed. No commit, push or deployment was performed. Await approval before rollout or live-data changes.
