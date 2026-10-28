# Phase 7 — finance finalization and release preparation

**Release decision: BLOCKED.** Source preparation is not deployment approval.

## Implemented and changed files

- `dic_finance/services.py`: gross verified collections, recorded adjustments,
  net verified collections, commitments, paid expenses and budget remain distinct.
  Available operating balance is explicitly unavailable without bank/opening
  balance reconciliation. Existing net-position field remains compatible.
- `dic_finance/api.py`, `dic/templates/dic/finance_report.html`, frontend
  `pages/Finance.jsx`, `services/financePresentation.test.js`: permission-checked
  printable exports with the same filters, bounded rows and audit as CSV; clearer
  recorded-net-position wording. No approval or payment transition is weakened.
- `dic/operations_api.py`: participant/booking lists and details and housing views
  plus the registration dashboard and record exports now require explicit
  record-view permissions, not general Operations/report-export access alone.
- `setup_dic_staff_roles.py`: default preview performs no database access. Applying
  explicit additive allowlists requires `--apply-reviewed-grants`. General DIC
  Administrators receive no blanket finance/welfare/identity rights. Existing
  grants are neither silently removed nor changed; review them before release.
- `config/settings/production.py`, staging.py, `config/release_security.py`:
  strict secret/host/origin/TLS/cache validation, secure cookies/HTTPS/HSTS,
  static WhiteNoise setup, redacted request failures and shared throttle cache.
  Production keeps strong Django hashers; fast hashing exists only in validation.
- `render-migrate.sh`, `config/release_migrations.py`, management command
  `release_migrations.py`: inspection-only deployment hook, fail closed on pending
  migrations; separate exact-manifest approval for manually authorized application.
- `test_release_readiness.py`, `scripts/validate_dic_phase7_policy.py`,
  `scripts/validate_dic_phase7.ps1`: database-free release regression/graph checks
  plus frontend tests/lint/build and PASS/FAIL/NOT RUN summary.

## Paystack review and limits

Existing initialization uses server totals/revisions and an access-authorized
booking. The settlement service checks provider reference, integer amount,
NGN currency, test domain, provider transaction identity, paid time and accepted
revision. Unique transaction constraints and locks prevent duplicate credit.
Webhooks authenticate HMAC signatures, deduplicate payload hashes and independently
verify transactions before settlement; transient verification failures remain
retryable. Tutor orders cannot initiate ordinary payment. Whole-order settlement
preserves multi-child totals. Portal eligibility separately checks trusted evidence
and current source restrictions. Email ownership/password creation alone do not
grant protected access.

**Live Paystack is intentionally still unsupported/blocked** by both the client
and settlement domain checks. Never merely swap in a live key. A separately approved
change and test/live parity acceptance are required before live launch. No provider
request, refund, payment or credential change ran during this work.

Finance reconciliation records documented refund/reversal evidence; it does not
call Paystack refunds or itself invalidate portal eligibility. Eligibility follows
existing order/payment/source state. Real refund processing and evidence/state
reconciliation must be accepted before launch. Bank settlement balances and a
dedicated downloadable camper payment receipt are not established by this phase;
existing verified payment-return/booking confirmation is not a bank receipt.

## Migration approval and deployment checklist

No migrations were applied and no databases were inspected. Source graph remains
0026 → 0028 → 0029 → 0030 → deferred 0027 → 0031. Finance/Movement app migrations
remain separate dependencies on 0026. No historical migrations were modified.

The deployment hook requires explicit `DJANGO_SETTINGS_MODULE` and
`RELEASE_DATABASE_NAME`; it runs `release_migrations --database-name ...` in
inspection mode only. It refuses development/demo/system database names, verifies
configured and PostgreSQL database identity, checks history/conflicts, and prints
the entire pending ordered plan with source hashes and dependencies. Pending
migrations fail deployment rather than silently being skipped or applied.

Before any separate migration authorization:

1. Obtain a read-only plan in the explicitly approved release environment. Actual
   pending state is NOT known from this source review.
2. Review every step and dependency, especially 0027/0031. Retain the exact JSON
   manifest; changes to code, plan, settings or database require renewed approval.
3. Take a database backup; verify restore in an approved disposable environment.
   Record backup identifier, approver/time, restore procedure and rollback decision.
4. Place the manifest inside an approval JSON with keys `manifest`, `approved_by`,
   `approved_at`, `backup_reference`, `restore_procedure`, `rollback_decision`.
   Restrict filesystem access: this is an operator approval artifact, not a digital
   signature or automatic authorization issued by this application.
5. Only after explicit authorization, an operator may invoke the separate command
   with `--apply-approved-plan --approval-file ...`. No build/start hook passes
   this flag. Application also emits Django post-migration permission/content-type
   initialization; it never grants those permissions to actual staff accounts.
6. Shared cache table creation is **separately approved** and not automated here.
   Staging uses `dawana_staging_cache`; production uses `dawana_release_cache`.
7. Validate schema, cache, static manifest and health, then acceptance with traffic
   closed. On failure do not automatically reverse data migrations: restore the
   approved backup or follow reviewed forward repair. Account for all writes since
   backup before a restore. Revert application artifact only when schema compatible.

Read-only planning can query a database but must not be executed until the target
environment is approved. No release command was run here. The old health endpoint
checks connectivity (`SELECT 1`), not full schema/cache readiness; use the guarded
migration inspection plus cache/static checks before routing traffic.

## Required configuration (names only; never copy secrets into source)

- `DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
  `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` (exact HTTPS origins).
- Explicit PostgreSQL `DATABASE_URL`; TLS enforced; `DB_TEST_NAME` remains separate.
  `RELEASE_DATABASE_NAME` must match the intended release database. Staging also
  requires `STAGING_DATABASE_NAME` and retains tester allowlisting.
- `PAYSTACK_MODE=test`, test-only `PAYSTACK_SECRET_KEY`, approved HTTPS
  `PAYSTACK_CALLBACK_URL`. Live activation requires separate approval/code acceptance.
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`/`EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL`;
  use a secret store. `DIC_PORTAL_EMAIL_VERIFY_URL` points to the HTTPS
  `/dic/participant` page. `DIC_RECOVERY_ENCRYPTION_KEY`, recovery delivery flags
  and actual worker operations require separate verification. No emails sent here.
- `DIC_FEEDBACK_PRIVACY_KEY` must remain stable and private; at least 32 characters.
  `DIC_PORTAL_ACCOUNTS_ENABLED` only after approved schema and acceptance.
- Frontend uses same-origin `/api/v1` preferably; otherwise exact approved HTTPS
  `VITE_API_BASE_URL` with matching CORS/CSRF. Frontend environment values are public.

Render production start is **not finalized**: current `render-start.sh` intentionally
accepts staging settings only. Do not change settings/route live traffic as a way
around this gate. Validate trusted-proxy header handling for production before
enabling SSL redirects behind a TLS-terminating proxy. HSTS includes subdomains
and preload: confirm all affected hosts are HTTPS before launch. Static/media and
backup retention require hosting review. No production credentials were read or
assessed for compromise; no mandatory rotation is inferred. Rotate any known
exposed/reused credentials only through explicitly approved secret management.

## Manual acceptance — one controlled test-mode procedure

The latest retained Phase 3 receipt reports `stage=account_activation`, failed,
and `cleanup=rollback_verified_no_retained_rows`. Source locators still match the
email-confirm button and success text. No confirmed application defect follows
from this timeout; browser acceptance remains incomplete. No Playwright rerun.

After separately approving a disposable database, schema and synthetic fixtures:

1. Verify all three database identities; keep public traffic closed, use test
   Paystack and an explicit synthetic-email allowlist/sink. Never real campers.
2. Register one synthetic camper at `/dic/register` using explicit primary contact,
   password/confirmation. Check server price, checkout total and category.
3. Complete a Paystack test payment or approved isolated provider mock. Return via
   the existing payment-return route. Require backend-confirmed evidence; a forged
   success URL, pending/failed attempt or password alone must not unlock the portal.
4. Follow the actual verification email to `/dic/participant`; click Confirm email
   ownership once. Confirm the success state, then email/password Sign In. If it
   fails, record sanitized endpoint/status/stage rather than tokens or screenshots
   containing secrets. Do not repeatedly retry automated browser cycles.
5. Confirm only linked children appear. Repeat with a multi-child whole-order
   booking and a separately paid order. Unrelated/unpaid orders must remain denied.
6. Verify authorized issued QR ID access; no fabricated ID before issuance. Test
   unpaid, invalidated and revoked tutor scope using only approved synthetic data.
7. Logout; verify protected API denial, cross-tab clearing and expired-session
   behavior. Legacy setup/password recovery requires booking/email ownership.
8. Inspect mobile labels, focus, error states, payment return and normal scrolling.
   Check finance permissions and Phase 5/6 schema-unavailable behavior.
9. Preserve receipt/evidence; cleanup only explicitly recorded synthetic fixtures
   through an approved rollback/cleanup procedure. Never reset/delete existing DBs.

## Validation / next action

Run once locally from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_phase7.ps1
```

This is database-free: system checks, production validation contracts, payment
client/evidence/Finance, authentication, privacy, tutor, Phase 5/6, movement/housing
and migration graph/model-state checks. It does not inspect actual pending schema,
apply migrations, create databases or run database-writing acceptance. The final
summary must therefore be considered alongside the pending-schema release gate.

Executed here: 214/214 frontend tests PASS, lint PASS, production build PASS
(bundle-size advisory only), PowerShell syntax PASS. Backend tests, actual
production-settings import/deploy checks, pending-database inspection and migration
application NOT RUN. Python remains inaccessible in this environment and was not
retried. Overall validation is INCOMPLETE; no backend pass is claimed. Pure
configuration contracts are covered in the prepared suite, not a verification of
actual production secret values or hosting configuration.

BLOCKERS: local backend execution/validation; isolated migration approval and
acceptance; Phase 3 browser/manual acceptance; actual staff-grant review; production
proxy/start/cache/email/static/backup checks; separate live-Paystack approval and
receipt/refund acceptance. Public registration and production deployment remain
unauthorized. Phase 4 remains postponed. No claim of production readiness is made.
