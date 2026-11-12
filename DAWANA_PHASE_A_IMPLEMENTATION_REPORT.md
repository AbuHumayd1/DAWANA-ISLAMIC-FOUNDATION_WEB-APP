# DAWANA Phase A Implementation Report

Date: 12 November 2026 (Africa/Lagos).

## 1. Executive summary

Phase A implements creation-based 24-hour unpaid-order expiry with explicit operational activation, historical preview, preserved payment evidence, secure account reuse, account-credential checkout recovery, and separately authorized late-payment decisions. Participant passwords accept any nonempty value up to the existing 128-character maximum, including common, one-character and space-containing passwords. Staff password policy is unchanged.

The original production baseline remains owner-reported: successful NGN 4,000 Paystack registration/payment, Operations visibility, participant login/dashboard and document download on 12 November. No live transaction or production login was repeated here. Local HEAD remains `7a9c97845541c56820380b9756eac4c4c5eeb093` on `deployment/container-packaging`; the actual deployed revision is still unverified.

No deployment, production access, production migration, production expiry activation, real charge/refund/reinstatement, infrastructure or environment change was performed. All database writes during testing were confined to a newly initialized disposable workspace PostgreSQL cluster on loopback port 55483. No existing local database was used.

## 2. Approved policy implementation

| Policy | Implementation |
|---|---|
| 24 hours from creation | `created_at + timedelta(hours=24)`, timezone-aware; at the deadline a new payment is forbidden. Provider payment at the deadline is outside the window. |
| Historical unpaid orders included | Explicit activation applies computed deadlines to old and new orders alike. No reset of old creation timestamps and no automatic historical exemption. |
| Activation control | Migration creates schema only. No activation row is seeded. Default command is a read-only preview; `--activate --apply` is required to activate. |
| Paid/tutor protection | Paid/refunded flags and successful-payment evidence are conservatively protected from automated expiry; tutor-basis bookings are excluded. Contradictory paid evidence requires review rather than automatic closure. |
| Financial retention | Expiry is an additive archival overlay. It never deletes orders, attempts, references, webhook events, bindings or audit history; it does not relabel an uncertain charge failed. |
| Late delivery | Independently verified payment within the original window follows ordinary settlement even after the order appeared in the expired archive. |
| Genuinely late success | `reconcile` with `order_expired`; no automatic entitlement. Staff resolution is permission-protected and audited. |
| Participant passwords | Required/nonempty only, existing maximum 128; no minimum, composition, common-password, numeric-only or similarity rejection. No whitespace trimming. |
| Usernames | Stable lowercase/trim normalization, 1–40 ASCII letters/numbers with spaces, dots, hyphens and underscores; initial alphanumeric; repeated spaces and reserved names/prefixes rejected. Existing identifiers are not renamed. |
| Account reuse | Explicit Create / Existing account form; existing credentials authenticate before binding another same-contact booking. Each booking keeps independent payment state. Contact matching alone never selects or authenticates an account. |

Expiry deliberately does **not** set `RegistrationOrder.status='cancelled'`. Cancellation already has different settlement semantics. The overlay lets an on-time payment delivered late settle safely and keeps uncertain payment evidence accessible. It is shown as Expired in Operations/default archives and enforced at initialization/repricing regardless of scheduler delay.

## 3. Exact application/test files changed

Modified files (Phase A changes only; the overall working-tree diff also contains older owner work):

```text
backend/accounts/admin.py
backend/dic/models.py
backend/dic/operations_api.py
backend/dic/payment_return.py
backend/dic/payment_views.py
backend/dic/payments.py
backend/dic/portal_accounts.py
backend/dic/recovery_views.py
backend/dic/registration_accounts.py
backend/dic/serializers.py
backend/dic/test_portal_accounts.py
backend/dic/test_registration_accounts.py
backend/dic/urls.py
dawana-platform/src/components/dic/PortalAccountAccess.jsx
dawana-platform/src/components/dic/PrimaryRegistrantFields.jsx
dawana-platform/src/components/dic/TutorRegistration.jsx
dawana-platform/src/pages/DIC.jsx
dawana-platform/src/pages/Operations.jsx
dawana-platform/src/services/bookingContact.js
dawana-platform/src/services/portalAccount.test.js
```

New files:

```text
backend/accounts/participant_admin.py
backend/config/phase_a_runner.py
backend/config/settings/phase_a_test.py
backend/config/settings/phase_a_postgres.py
backend/config/settings/phase_a_tutor.py
backend/dic/management/commands/expire_dic_orders.py
backend/dic/migrations/0041_phase_a_order_lifecycle.py
backend/dic/order_lifecycle.py
backend/dic/order_lifecycle_models.py
backend/dic/payment_resolution.py
backend/dic/phase_a_api.py
backend/dic/test_phase_a.py
dawana-platform/scripts/check-phase-a-ui.cjs
dawana-platform/src/components/dic/AccountCheckoutRecovery.jsx
dawana-platform/src/components/dic/AccountCheckoutRecovery.css
dawana-platform/src/components/operations/LatePaymentResolution.jsx
dawana-platform/src/services/orderLifecycle.js
dawana-platform/src/services/participantCredentials.js
dawana-platform/src/services/phaseA.test.js
scripts/run_phase_a_tests.py
DAWANA_PHASE_A_IMPLEMENTATION_REPORT.md
```

Validation logs, synthetic screenshots/build outputs and the disposable database directory are under ignored `output/phase-a/`. Do not package that directory as application source. Temporary edit helpers there are not deployment inputs. A pre-Phase-A copy/patch of already-modified `DIC.jsx` is retained there to distinguish the owner's earlier changes.

No Git staging, commit, reset, checkout, clean or branch merge occurred. Earlier CI/bootstrap/schema-recovery/staging/configuration edits, review archives and release candidate artifacts remain present. The Phase A changes to `DIC.jsx` were layered onto its existing edits; the older server-validation notice was retained. Other previously modified application/configuration files were not repurposed as Phase A work.

## 4. Database migration

`0041_phase_a_order_lifecycle.py` follows `0040_username_credential_transition` and creates:

- `OrderExpiryPolicy`: singleton activation timestamp and responsible actor.
- `OrderExpiry`: one archival record per order, original deadline, recording timestamp and evidence classification.
- `PaymentResolution`: unique request ID, original attempt, actor, decision, reason, timestamp and optional provider refund ID; per-attempt decision uniqueness.
- `dic.manage_dic_order_lifecycle` permission. Existing operations and finance permissions are also required.

No participant/password/username/contact/binding migration is needed. The contact-channel/digest uniqueness constraint remains intact. No data backfill or activation is included in migration 0041. Real migrations ran only in disposable test databases, including the repository's PostgreSQL integrity triggers.

## 5. Management command and scheduling

`expire_dic_orders` previews overdue unpaid records without provider calls or database writes by default. It emits only order reference, numeric cursor, original deadline and evidence classification, plus batch totals. `--after-id` allows a complete paginated preview. No participant name/contact is printed.

Application mode verifies available non-successful attempts through the existing provider verification/settlement path before recording archival metadata. Network uncertainty is retained as verification-required evidence. Order-first/attempt-second locking rechecks payment state, and per-order transactions permit interruption-safe retries. Existing successfully paid orders are excluded and never archived merely because they are old.

No scheduled task, hosting worker or production setting was created. After separately approved activation, the existing operational scheduler may invoke the bounded command periodically to record archival audit entries. Deadline enforcement and default archive filtering do not depend on that scheduler running exactly at the boundary.

## 6. Historical activation procedure — prepared, NOT executed

The following PowerShell commands are instructions for a **separately approved production operation**, after release/migration review. They must not be interpreted as current execution authorization. Use the established Render management environment and approved settings; placeholders must be replaced privately, never paste credentials into chat.

```powershell
# From the backend directory in the separately approved management environment.
$phaseAPython = '.\.venv\Scripts\python.exe'

# Read-only first batch. No provider requests, expiry writes or activation.
& $phaseAPython manage.py expire_dic_orders --dry-run --limit 100

# Continue preview using next_after_id from the preceding batch.
& $phaseAPython manage.py expire_dic_orders --dry-run --limit 100 --after-id <last-cursor>

# Only after explicit operational approval, migration and reviewed staff grants:
& $phaseAPython manage.py expire_dic_orders --activate --apply `
  --actor <approved-staff-id> --database-name '<confirmed-database-name>' --limit 100

# Subsequent batches/retries: activation is not repeated and existing expiry
# records are skipped. Run from the beginning to catch interrupted work.
& $phaseAPython manage.py expire_dic_orders --apply `
  --actor <approved-staff-id> --database-name '<confirmed-database-name>' --limit 100
```

Activation commits a policy timestamp/audit event before batch processing. Therefore the creation-based deadline and archive filter become effective for **all** qualifying historical orders immediately, even while archival-record batches are still being processed. This is intentional under the approved historical policy. A provider outage must not be mistaken for no money received; inspect verification/reconciliation cases. Command interruption does not undo committed earlier records, and retry does not duplicate them.

Preview counts reflect stored evidence only, not a certification that the provider holds no successful charge. Apply performs provider verification; webhooks and customer verification remain available after expiry. Long-running batches should be sized for the existing provider timeout and platform limits. Never use the synthetic test settings for production activation.

## 7. Late-payment reconciliation workflow

Payment time, webhook-event creation time, backend `verified_at`, policy activation time and original expiry deadline remain separate. The existing signed webhook and independent verification checks for reference, amount, currency, transaction identity, environment and idempotency are preserved.

1. Timely provider success (`created_at <= paid_at < expires_at`) can confirm a previously archived submitted order, subject to existing quote validity/eligibility. Paid bookings leave the default expiry archive automatically; archival/audit history remains.
2. Success genuinely at/after the deadline enters `reconcile/order_expired`. Missing/naive, impossible pre-creation or future timestamps are held for reconciliation while expiry is active. No automatic charge retry or entitlement follows.
3. Operations registration details expose late-payment decisions only to active staff with Operations, Finance and lifecycle permission. API enforcement is independent of UI visibility. Session authentication and CSRF remain required.
4. **Reinstate** re-fetches provider transaction evidence, uses the ordinary verified-evidence checks, requires a valid paid quote and no conflicting successful charge, then confirms payment and reuses ordinary housing/fulfillment handoffs. An existing refund decision blocks reinstatement. Other evidence conflicts continue to block eligibility.
5. **Refund requested** records intent, actor/reason/time and does not call a refund-initiation endpoint or mark a refund complete. Staff arrange the actual refund separately through approved Paystack operations.
6. **Verify completed refund** fetches an existing provider refund ID. Only a matching `processed` full refund with correct transaction ID, amount, currency, environment and plausible timestamp marks the order refunded. Pending, failed, partial or mismatched refunds remain under review. Original attempt evidence is retained.
7. Retrying the same decision request is idempotent; reusing its ID with different content is refused. Decision records are append-only through the service/model paths, with separate DIC audit events. Cross-order request-ID races roll back the losing transaction.

Provider contract reviewed against [Paystack Refund API](https://paystack.com/docs/api/refund/) and [refund lifecycle documentation](https://paystack.com/docs/payments/refunds/). Provider `processed` status does not guarantee immediate bank availability; this UI records provider completion, not a promise of arrival in the customer's bank account.

## 8. Account reuse and recovery

- New form submissions explicitly choose create or existing account; older payloads retain compatible auto mode. Existing mode never creates an account after failed authentication and does not require confirmation of a newly chosen password.
- Existing same-contact account credentials can link multiple orders, including grouped children and separate registrations. New-account username collisions are directed to reuse/another username. The existing contact uniqueness constraint is retained; creating another username for the same channel/contact still fails safely.
- A different primary-contact snapshot does not silently transfer a booking or establish ownership. Such changes require existing verified/staff-assisted recovery; no general account merger was added.
- `POST participant/auth/orders/recover/` authenticates current credentials, rate-limits attempts, rechecks account/binding/contact/revocation under locks and returns only owned pending/failed submitted orders. It rotates existing order bearer access for checkout/status verification, not a dashboard/Django staff session. Tokens/passwords remain in memory and are not written to browser storage.
- Up to 100 recent unpaid owned bindings are returned. Paid bookings remain available through ordinary eligible participant scope; an added unpaid or expired order does not remove earlier paid access.
- Expired recovered orders show a concise warning and no new checkout action. Existing attempt references can still be verified. Recovering an old link does not extend the creation-based deadline.
- Existing contact-code and staff-reviewed recovery continue to work. Staff recovery still does not establish guardianship/collection authority or grant paid entitlement merely by setting credentials.

## 9. Password and username changes

Participant policy is enforced consistently through signup serializers, shared account policy, setup/reset/credential transition, tutor inputs and frontend validation. One-character/common/symbol/space-containing values are accepted; empty and >128-character values are refused. Django secure password hashing/comparison remains unchanged in runtime code.

The Django user-administration password form detects ordinary portal accounts and applies participant policy only to those accounts. Staff/superusers and unrelated Django users retain Django's validators. Participant usernames are read-only in the ordinary user-change form so a unilateral Django username edit cannot desynchronize the portal key; the established reviewed credential transition updates both together.

Simple ASCII names with single spaces are supported without introducing Unicode casefold/canonicalization migrations. Accented usernames are not added in this increment; natural full names remain separate. Login continues case-insensitive lookup and does not retroactively reject old valid usernames. Reserved organizational/admin/staff names and prefixes remain blocked for new choices.

**Security limitation:** extremely short/common passwords have a small guess space. Hashing adds cost per guess but no entropy. Rate limiting reduces online guessing but does not eliminate distributed/prolonged guessing, and stolen hashes can be attacked offline. A compromised account can expose its authorized booking information. This residual risk is accepted by the explicit owner policy; no hidden minimum, common-password ban or forced MFA was substituted. Optional longer-passphrase guidance is shown.

## 10. Operations Portal changes

Registration list filters now offer Active registrations, Expired archive and All records. Default active list/dashboard excludes computed expired unpaid orders after activation. Detail URLs remain accessible to appropriately authorized staff without an archive query parameter. Paid/status filters and original financial views remain available. Expired status is readable; provider attempts and reconciliation reasons remain preserved.

Lifecycle staff can view decision history and record reinstatement/refund intent/provider-confirmed refund from late-payment details. Permission checks require all three capabilities and active staff status; a finance role alone is insufficient. No permission was assigned to an actual user or group during development.

## 11. Executed validation

All API/provider calls in automated tests were mocked; the backend test adapter blocks external network access. PostgreSQL connections were limited to a fixed new loopback-only cluster/user. The migration graph ran unchanged before disposable reference seeds were flushed for the existing synthetic fixtures. No production configuration was imported by the test settings.

| Check | Result / evidence |
|---|---|
| Backend core + Phase A + existing username concurrency, account, registration, Paystack verification/webhook/idempotency, return, recovery, Operations and participant access suites | **227 passed**, `output/phase-a/backend-complete.log` |
| Tutor policy/integration partition | **27 passed**, `output/phase-a/backend-tutor-final.log` |
| Frontend service/render regression suite | **313 passed**, `output/phase-a/frontend-tests-final.log` |
| Frontend lint | Passed, `output/phase-a/frontend-lint-final.log` |
| Production frontend build | Passed using the approved API origin in a command-scoped variable; no environment file edited. Output `output/phase-a/frontend-dist`; existing >500 kB chunk warning remains. |
| Migration consistency | `makemigrations --check --dry-run`: no changes detected |
| Migration plan | Prepared against isolated in-memory settings; migration 0041 actually applied in disposable PostgreSQL test setup |
| Django system check | Passed |
| Targeted Phase A browser flows | Headless Chrome: both Create and Existing account registration through intercepted synthetic checkout passed; mobile 390 px pending/expired recovery, one-character password, no credential persistence, duplicate-submit disabling and payment initialization passed. Every API/external checkout request was intercepted locally. Log: `output/phase-a/browser-phase-a.log`. Synthetic screenshots inspected; recovery spacing corrected. |
| Diff whitespace | `git diff --check` passed (Git reports existing LF/CRLF conversion notices) |

The Phase A suite includes real PostgreSQL expiry-versus-settlement concurrency, original deadline boundaries, activation/dry-run/interruption/idempotency, archived detail access, short/common/space password hashing/reset/reviewed recovery, staff isolation, account reuse/contact mismatch, pending-only recovery without paid session, prior paid scope preservation, and refund intent versus verified completion. Existing username-concurrency tests also executed successfully in the guarded core partition.

An initial SQLite migration attempt failed on pre-existing PostgreSQL-specific `FUNCTION` SQL and was replaced with real disposable PostgreSQL. Initial unadapted test runs encountered existing seeded-edition collisions and guarded partition-name requirements; the dedicated test runner follows the existing CI pattern of real migrations followed by a strictly named disposable-only flush. Failures found during implementation (nullable-join locking, datetime serialization, obsolete password assertions and test fixture setup) were corrected before successful runs. Earlier failed logs remain as history rather than being presented as passes.

## 12. Validation limits

- Production deployment, live payment/refund, production migration/expiry activation and production browser verification were not run, as explicitly prohibited.
- Real iPhone Safari and a PostgreSQL version other than the available disposable PostgreSQL 18 were not tested.
- The old broad `check-registration-ui.cjs` was attempted and timed out on an animated occupation dropdown before reaching checkout; it is not counted as a pass. Targeted current Phase A browser coverage is separate; a complete cross-browser visual sweep remains a release prerequisite.
- Password reset ownership tests use the existing proof boundary with synthetic/mocked fresh proof; no actual email/SMS provider was contacted.
- No unrelated Phase B–E feature suite or document visual regression was added/run solely for this scope. Existing payment-return/download boundaries were exercised by the selected regression suites; no claim of full application or production certification is made.

## 13. Deployment prerequisites and remaining decisions

No further policy decision is required for the approved Phase A scope. Production deployment and activation still require explicit authorization.

Before release: establish actual deployed frontend/backend revisions and applied schema, review the Phase A-only diff alongside existing owner work, run approved CI, verify backups/recovery procedures, review migration 0041 and permission grants, and complete real-device Safari/browser smoke checks. Use existing Cloudflare/Render/PostgreSQL/Paystack infrastructure; no new service is needed.

Deploy compatible backend/migration before frontend, keeping expiry inactive initially. Review read-only historical preview and payment evidence, then obtain the separate operational activation authorization. Review the activation's immediate effect on all historical deadlines and staff workload. Verify staff reconciliation access without expanding financial access to ordinary users. Actual refunds remain separately authorized Paystack operations.

The narrow resolver intentionally holds ambiguous timestamps, invalid/stale quotes, partial refunds, cancelled bookings, conflicting evidence and complex multi-charge cases for existing financial review. It does not fabricate settlements, waive quote validity, automatically refund, or automatically reopen an expired unpaid order to make another charge. The contact/booking ownership safeguards remain intact.

## 14. Rollback

Before activation, return to the preceding reviewed frontend/backend artifacts if needed; keep the additive migration tables. Do not migrate backward by deleting expiry/resolution/audit records. No password hash or existing username needs conversion on rollback, but old UI/policy may again reject newly chosen short passwords during account changes—avoid rolling back just the account-policy helper while leaving the new frontend deployed.

After activation, a rollback to code without deadline enforcement would permit expired-order charges again. Prefer a forward correction or temporarily pause new registration/payment initialization through an approved operational procedure while preserving webhook verification and reconciliation. Do not delete the activation row or archival evidence to conceal the effect. Do not bulk reopen/refund/mark paid or restore an old production database over newer payments. Keep active schema and recorded decisions; reconcile affected records with audited staff actions.

An already processed real refund cannot be undone by code rollback. Reinstatement remains a paid entitlement decision and must be reconciled using the original reference. Existing verified paid registrations, participant accounts, authorized tutors and financial history must remain intact.

## 15. Delivery status

**PHASE A IMPLEMENTATION COMPLETE — AWAITING PRODUCTION DEPLOYMENT APPROVAL**

Implementation and the scoped local synthetic checks are complete, subject to the documented release prerequisites and validation limits. Production systems and existing unrelated work remain unchanged. Deployment and historical expiry activation have not been performed.

Concise diff summary: participant credential policy and explicit account reuse; additive expiry/decision schema and command; deadline-aware payment/recovery handling; Operations archive and reconciliation controls; participant-aware Django admin password handling; focused backend/frontend/browser regression coverage and isolated validation helpers. The overall `git diff --stat` includes older unrelated owner edits and should not be used as the Phase A-only release manifest. The exact file lists above identify this implementation scope.
