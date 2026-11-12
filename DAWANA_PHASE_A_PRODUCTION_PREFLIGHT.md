# DAWANA Phase A Production Release Preflight

Date: 12 November 2026, Africa/Lagos. **Recommendation: NO-GO for production release or expiry activation at this time.**

This is a read-only preflight, not deployment approval. Only this document was added. Application code, tests, existing owner work, production databases, backups, settings, payments and infrastructure were not modified. No migrations, activation, charges, refunds, staff grants or production authentication were executed. Local browser investigation used the existing Vite development server and mocked APIs; it did not contact Paystack.

## 1. Verified facts and evidence boundary

| Item | Evidence and conclusion |
|---|---|
| Local source identity | Branch `deployment/container-packaging`; HEAD `7a9c97845541c56820380b9756eac4c4c5eeb093`. This is not either deployed revision. |
| Working tree | Phase A implementation remains uncommitted alongside older owner changes and untracked release/recovery artifacts. No staged/committed release artifact was established. |
| Implementation evidence | Existing logs record 227 backend core/access/payment/Operations tests passed, 27 tutor tests passed and 313 frontend tests passed. Lint/build/migration checks passed in the implementation turn. Those logs are local candidate evidence, not production or exact-release-commit CI certification. |
| Migration identity | `backend/dic/migrations/0041_phase_a_order_lifecycle.py`, SHA-256 `CAD332423AF3B3E03763A0051CB8B2491DE927077B4AD624AAB9F0943132F8E9`. |
| Protected live baseline | Owner-confirmed successful NGN 4,000 registration/payment, payment visibility, portal login/dashboard and document download on 12 November. No new live test was performed. |
| Production frontend revision | **Not verified.** No authenticated Cloudflare Pages deployment metadata/session was available through the inspected tools. Public homepage fetch was unavailable through the web tool. |
| Production backend revision | **Not verified.** No authenticated Render deployment metadata/session was available. Public health fetches were unavailable through the web tool; source health responses contain status only, not Git SHA. |
| Backup/current recovery readiness | **Not verified.** Repository runbooks describe procedures; no current provider backup record, restore-point timestamp, retention, decryptability/access evidence or actual restore-test receipt was available. |

Public fetch failures are tool-access limitations, **not evidence that production is down**. The source-defined health URLs are `/api/v1/health/web/` and `/api/v1/health/`; these exact URLs were also attempted without success. Wrong guesses such as `/healthz` do not establish application health. No secrets/environment files or participant data were retrieved.

### Exact owner actions to establish deployed identities

1. In Cloudflare Pages, inspect the deployment currently serving the custom domain: project, deployment ID, production environment, full source commit SHA, branch, build time, build command/root/output and active custom-domain association. A successful preview build is insufficient. Retain a sanitized metadata record.
2. In Render, inspect the running web service's active deploy: service/deploy ID, full source commit SHA, repository/ref, image digest if container-based, root directory, build/start commands and successful activation time. Inspect the worker's deployed revision independently if one is enabled. A latest-build SHA is insufficient unless it is the running deploy.
3. Compare these with Git repository history and the owner-confirmed working release. `RENDER_GIT_COMMIT`/`CF_PAGES_COMMIT_SHA`, if exposed by their actual build metadata, must be tied to the active deployment—not a shell on an unrelated release. Do not expose private environment dumps.
4. Provide read-only applied migration names through 0040, database PostgreSQL major and whether any Phase A activation row already exists. Do not infer applied schema from successful registration alone.

Until these are recorded, neither the correct patch base nor compatibility with the actual production schema can be certified.

## 2. Phase A versus older owner work

The exact Phase A file inventory is in `DAWANA_PHASE_A_IMPLEMENTATION_REPORT.md`, sections 3–4. Inspection confirms these groups:

- **Phase A backend:** participant-aware admin form; account policy/serializers/binding; lifecycle models/service/command; migration 0041; late-payment resolution service/API/routes; payment initialization/settlement/return summaries; recovery; Operations archive and permission visibility; focused tests and isolated test helpers.
- **Phase A frontend:** explicit create/reuse fields, password policy, pending checkout recovery and scoped CSS, deadline helper, Operations archive/resolution controls, related service/render/browser tests.
- **Older tracked work:** `.github/workflows/backend-acceptance.yml`, `RENDER_STAGING_PREPARATION.md`, native host/defaults/deployment tests, `backend/native-start.sh`, environment examples, `backend/dic/templates/admin/base_site.html`, `backend/dic/test_payment_return.py`, existing API helper/test corrections and `scripts/test_production_policies.py`. Their current diff sizes match the earlier owner baseline for inspected paths. They are not automatically authorized release dependencies.
- **Older untracked work:** bootstrap/schema-recovery workflows/helpers/tests, previous review documents, `release-validation/`, source-review archives/directories, preview/build outputs and `.vite/`. Preserve them; exclude them from a Phase A package unless individually reviewed and selected.
- **Mixed file:** `dawana-platform/src/pages/DIC.jsx` already had `paymentReturnSetupMessage` import/error-guidance changes. `output/phase-a/DIC.owner-before.jsx` and `.patch` preserve that pre-Phase-A version; the current diff retains those changes alongside Phase A. A whole-file copy would include both scopes.

Do not use `git add .`, deploy the working directory blindly, or treat `CONSOLIDATED_PRODUCTION_RELEASE.md`'s old 21-file candidate as a Phase A artifact. It predates migration 0041. Also do not remove its API helpers merely to exclude old work: current `DIC.jsx` uses an older helper export. Prepare a reviewed hunk-level patch against the **verified deployed base**, explicitly selecting any required older corrections, or adapt the Phase A patch to that base in a separately authorized implementation step. Run tests against that exact result.

No release commit, immutable backend artifact or whole-package checksum currently binds the mixed working tree to the local test results. This is a release blocker. No worktree was reset, cleaned or staged during preflight.

## 3. Migration 0041 safety assessment

### Confirmed structure

- Dependencies: `dic.0040_username_credential_transition` and the swappable authentication-user model.
- Three `CreateModel` operations only: `OrderExpiry`, singleton `OrderExpiryPolicy`, and `PaymentResolution`.
- Foreign keys point to existing registration orders, payment attempts and user records, using `PROTECT` in Django deletion semantics.
- New-table primary keys, order one-to-one index, unique request ID, `(attempt, decision)` uniqueness and singleton ID check are included.
- New lifecycle permission is created by Django post-migrate; default add/change/delete/view permissions are disabled for these models.
- No `RunPython`, seed/backfill, existing-row update/delete, password rewrite, existing-table column alteration or activation is included. Merely migrating does not expire historical records.

### Compatibility and operational risks

This is an additive migration that old runtime code should tolerate **if** the installed schema/graph matches the expected 0040 lineage. Creating foreign-key constraints still acquires database locks on referenced tables; additive does not mean lock-free. Check migration role DDL privileges, active long transactions, migration lock/statement timeouts and provider/version compatibility before execution. No runtime or schema check in this preflight establishes production table volume, locks or role grants.

The new backend does not gracefully tolerate missing lifecycle tables. `order_lifecycle.activation()` queries `OrderExpiryPolicy` directly; settlement, payment initialization/repricing and read serializers call lifecycle helpers even while policy is inactive. Therefore **schema first, then new backend traffic**, not merely “deploy backend and migrate later.” `/api/v1/health/web/` and the basic `SELECT 1` database health check will not detect missing lifecycle tables. Check exact migration application separately.

Old code with the additive tables is compatible in principle; new code without them is not. Applying 0041 to a production schema with earlier pending migrations could apply older data-changing migrations too if an unreviewed all-leaf migrate is used. Review the complete pending graph/manifest, not the filename alone. Conflicting/absent migration history is a blocker; never fake-apply or run the older schema-recovery/bootstrap workflow as a shortcut.

### Migration tooling and rollback

Existing `release_migrations` builds a manifest of pending migration source hashes, dependencies and target identity. It checks database/host/port/role/cluster identity and requires approval metadata including backup/restore/rollback evidence before apply. `backend/render-migrate.sh` is planning-only and stops on pending work; it does not apply migrations. The planner invokes `pg_control_system()`: if Render's approved inspection role cannot use it, stop and obtain an explicitly reviewed alternative identity-binding procedure. Do not bypass the guard by guessing a cluster ID or granting broad privileges.

Prefer keeping the additive tables when rolling code back. Reversing `CreateModel` operations would drop expiry/decision history and activation evidence, and is not an acceptable routine rollback once records exist. Django model immutability/PROTECT is not a substitute for database-level denial of arbitrary SQL deletion; retain least-privilege operational access and backups. An empty schema rollback, if ever necessary, needs its own reviewed plan, not this document's approval.

## 4. Release-order compatibility

| Transition | Assessment |
|---|---|
| Existing frontend + existing backend + additive schema | Intended safe compatibility stage; no expiry activation. Verify actual deployed base first. |
| Existing frontend + new backend + schema 0041, policy inactive | Intended compatible: old payload omits `mode`, default auto preserves reuse; old passwords/hashes remain usable; additional response fields are additive. Old UI may still impose its stricter minimum until refreshed. |
| New frontend + old backend | **Not compatible as a release strategy:** explicit `mode` can be rejected by the old strict serializer; new recovery/resolution endpoints and archive filter are absent. |
| New frontend + new backend + schema, policy inactive | Intended complete code release; ordinary verified settlement remains active. |
| Mixed old/new backend processes during activation | **Unsafe:** old processes do not enforce the deadline and may settle genuinely late payments normally. Wait until all web/worker replicas have the new revision and old jobs are drained. |
| Already-open old frontend tab after activation | Server blocks new initialization/repricing, but an old displayed Paystack URL can remain available. Preserve verification/recovery and communicate expiry. External checkout cannot be retroactively revoked by hiding a button. |

An activated policy is not an environment flag. It is a singleton database row; changing hosting settings cannot be assumed to disable it. Do not delete/edit that row ad hoc for rollback.

## 5. Historical expiry activation review

`expire_dic_orders --activate --apply` calls `activate()` **before** collecting/verifying its batch. Activation commits globally in its own transaction. At that instant:

- Every qualifying old unpaid order whose `created_at + 24h` has elapsed is logically expired, hidden from active registration views and blocked from new initialization/repricing—even before its `OrderExpiry` row is recorded.
- The `--limit` controls audit-record/verification processing, **not** how many historical deadlines become effective.
- The command subsequently verifies available attempts and records archival metadata per order. In-flight and uncertain attempts remain evidence, not failed/deleted charges. Timely payment can restore normal confirmed-paid workflow after independent verification; genuine late payment is held for reconciliation.
- A process interruption/provider configuration failure after activation leaves the global policy active. Retrying is idempotent for recorded orders, but does not roll back activation.

**Operational condition:** the command does not guarantee that all provider evidence is reconciled before global archival visibility changes. The implementation report correctly describes this, but release approval must explicitly acknowledge it. For the stricter requirement “reconcile historical evidence before any effective state change,” historical evidence reconciliation must be a separate approved step before activation, or an implementation correction must add that sequencing. Do not describe read-only preview as provider reconciliation. Keep expiry activation NO-GO until the owner has reviewed the complete cohort, pending/ambiguous payments, provider readiness and this immediate effect.

The apply path is **not read-only**: it invokes the existing verifier, which may settle payments and enqueue followups, then writes activation/expiry/audit rows. Do not run it during preflight, even with a small batch. Only `--dry-run`/default preview is read-only.

## 6. Complete read-only historical preview

### Available command after schema compatibility is established

Use a read-only operational session with the exact reviewed source/settings and verified database identity. Do not execute it now. The command's `expiry_record` exclusion queries the new archival table, so **0041 is required even for its dry run**. Use the existing-schema snapshot SQL below when preview is needed before schema approval; do not migrate merely to make preview available. It does not authenticate a supplied actor in preview mode, so access must be restricted by the shell/database role.

```powershell
# From backend in the approved management environment; no --apply/--activate.
& $phaseAPython manage.py expire_dic_orders --dry-run --limit 1000
& $phaseAPython manage.py expire_dic_orders --dry-run --limit 1000 --after-id <next_after_id>
```

Continue until `next_after_id` is null/no rows remain. Preserve every JSON batch securely, count unique order IDs and retain start/end times, exact source revision and target identity. Outputs contain cursor/order UUID/deadline/evidence state, not contact/name. They may still be sensitive operational data. No provider network requests are made.

**Limit:** each command uses a fresh `timezone.now()` and current evidence; separate pages are not a consistent snapshot. Orders can age across the boundary or settle while paging. The command also excludes existing archival records. Thus “remaining=0” alone does not certify a complete fixed-time historical population or all exceptions. Use the snapshot procedure below for the approval baseline, and refresh a delta just before activation.

### Fixed-time snapshot, including before migration 0041

An authorized owner/DBA can use a transaction explicitly set `REPEATABLE READ, READ ONLY` against the existing schema; no Phase A schema write is required. Example query, to be reviewed against the actual verified schema and executed only by the approved read-only operator:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH overdue AS (
  SELECT o.id, o.public_id, o.status, o.payment_status, o.created_at,
         o.created_at + interval '24 hours' AS expires_at
  FROM dic_registrationorder o
  WHERE o.registration_basis = 'paid'
    AND o.payment_status IN ('pending', 'failed')
    AND o.created_at <= transaction_timestamp() - interval '24 hours'
    AND NOT EXISTS (
      SELECT 1 FROM dic_paymentattempt p
      WHERE p.order_id = o.id AND p.status = 'successful'
    )
)
SELECT transaction_timestamp() AS snapshot_at,
       o.id AS cursor, o.public_id AS order_reference,
       o.status, o.payment_status, o.created_at, o.expires_at,
       count(p.id) AS attempt_count,
       coalesce(bool_or(p.status IN
         ('initializing','pending','init_unknown','verify_pending')), false)
         AS verification_required,
       coalesce(bool_or(p.status IN
         ('reconcile','amount_mismatch','duplicate_success')), false)
         AS reconciliation_required,
       coalesce(bool_or(p.provider_status = 'success'), false)
         AS recorded_provider_success
FROM overdue o LEFT JOIN dic_paymentattempt p ON p.order_id = o.id
GROUP BY o.id, o.public_id, o.status, o.payment_status, o.created_at, o.expires_at
ORDER BY o.id;
COMMIT;
```

Stream the complete result to approved private evidence storage; if size requires pagination, keep one read-only snapshot/server cursor rather than restart its clock per page. Record row count/checksum and summarize by evidence/status. Cap query duration to avoid a long snapshot affecting production cleanup; plan with the DBA. Do not copy contacts, portraits, bearer tokens or provider authorization URLs.

Review separately overdue paid-flag-without-success, successful-attempt-but-unconfirmed, refunded, cancelled, tutor and pre-existing archival cohorts. They are not silently eligible for bulk expiration. The query intentionally does not exclude `status='cancelled'`, matching the candidate command's broad pending/failed selection; show these separately rather than call them actionable active registrations. Existing paid/tutor counts are protection controls, not a reason to edit those records.

Provider verification of pending/unknown/failed/superseded attempts is a separate operation. Existing application verification APIs can **write** settlement state even when their provider request is GET. For a strictly read-only evidence review, the owner may inspect Paystack dashboard/approved provider fetches without invoking application settlement, using only references for the reviewed cohort. Any application reconciliation must await separate operational approval. No provider evidence was fetched here.

## 7. Staff permission requirements

`order_lifecycle.require_manager` requires all of:

- Authenticated, active Django user with `is_staff=True`.
- `dic.can_view_dic_operations`.
- `dic.can_view_dic_finance`.
- **New:** `dic.manage_dic_order_lifecycle`.

The resolver uses the existing Operations session/CSRF boundary. UI visibility is not authorization. Staff also need the existing registration detail/view permissions to reach the relevant order and finance information. Contact export, superuser, account editing and unrelated financial powers are not required merely for this workflow.

| Existing role | Proposed explicit grants |
|---|---|
| DIC Finance Reviewers | Only designated senior reconciliation reviewers should receive the new lifecycle permission. Existing operations/finance/record-view grants are present in the role source. Do not grant it to the whole group automatically without owner selection. |
| DIC Administrators | The source group name does not imply financial authority; its default grants are edition/category/operations views. Add finance, relevant record views and lifecycle permission only for designated resolvers. |
| DIC Registration Staff | May view permitted active/archive registrations; should not receive finance/lifecycle action permission by default. |
| Active staff superuser | Django's `has_perm` normally satisfies all checks, but use an accountable ordinary scoped staff identity where feasible. Do not create/convert a superuser for this feature. |
| Participant/media/other staff | No lifecycle grant. |

`setup_dic_staff_roles.py` does not assign the new lifecycle permission. Applying migration creates the permission, not membership. Owner must name resolvers, review direct/inherited grants and record approval. No production user/group state was inspected or changed. Same lifecycle permission currently covers activation, reinstatement and refund decisions; if separation of these duties is required, that needs an explicit code/permission change before activation.

## 8. Payment and participant continuity

Source inspection supports intended continuity, with the schema/revision prerequisites above:

- Existing signed `payments/paystack/webhook/` route remains; signature validation and independent Paystack verification remain the source of payment truth. Initialization/callbacks alone do not mark paid.
- Settlement still locks order before attempt and verifies reference/amount/currency/provider mode/transaction identity and duplicate identity. Successful/duplicate-success replays remain idempotent.
- Inactive expiry retains normal existing settlement rules. Active expiry uses provider `paid_at`, not webhook arrival time; missing/ambiguous timestamps hold entitlement rather than inventing a payment time.
- Expiry does not cancel an order or revoke its evidence access. Verification remains available; paid/tutor protected records are not auto-expired. Late genuinely successful payments enter reconciliation.
- Reinstatement re-verifies provider evidence and quote validity, records actor/reason/time, and uses normal fulfillment/housing handoffs. Refund-requested is intent only; confirmation requires matching provider `processed` full-refund evidence. Partial/ambiguous/complex cases remain held.
- Participant session/booking eligibility continues per linked order; a new unpaid/expired order does not remove earlier paid access. Staff/superuser accounts are not silently participant accounts. Existing hashes and usernames are not rewritten.

These are source/local-test conclusions, not current-production certification. Keep existing Django secret, recovery encryption key, cookie settings, cache/rate-limit storage and Paystack live credentials/mode stable across releases; replacing them can invalidate sessions or reconciliation assumptions. Do not replay real successful webhooks, call verification on live references, or log into a production participant account during this read-only preflight: those actions may write audits/sessions/verification state. Authorized post-deployment smoke tests are a later phase.

## 9. Occupation-dropdown timeout investigation

The earlier log identifies `getByRole('option', {name:'None (Not applicable)', exact:true})` resolving **`occupation-option-4`** and then timing out as invisible. The test's loop subsequently operates on marital status, but both lists contain the same option label. The locator is page-wide and does not bind the option to the combobox that was just opened.

Relevant source: `RegistrationField.jsx` renders each list permanently, hides closed lists with visibility/opacity/transform and `inert`, and handles outside pointer/focus events. `RegistrationControls.css` has a 140 ms open/close transition. The broad script also tests old draft-persistence expectations; the current registration contract intentionally removes sensitive draft data on reload, so a later full-script failure cannot be interpreted solely as dropdown failure.

Read-only local experiments used an **in-memory** copy of the existing script; no source/test file was edited:

1. Normal pointer selection with additional geometry observations successfully chose None for both occupation and marital status; execution later failed at a separate registration-summary expectation. This disproves a deterministic inability to select None.
2. Reduced-motion variation selected occupation, then the broad global option locator again resolved the now-hidden `occupation-option-4` while moving to the next field and timed out. Animation alone is not the root cause.
3. The scoped-locator experiment targeted `#<field>-options` rather than the global identical label, with normal pointer clicks and no forced click. It passed and printed `SCOPED_POINTER_SELECTED occupation None`, `SCOPED_POINTER_SELECTED maritalStatus None`, and `SCOPED_POINTER_SEQUENCE_PASSED`. The native select values were asserted/read in the experiment. Only the test was changed in memory; application/test files were preserved.

**Classification:** confirmed test-harness locator ambiguity/timing problem; no deterministic application selection defect was established. Do not “fix” the production combobox by force-clicking hidden elements or disabling accessibility. Correct the test to scope by each controlled list, assert `aria-expanded`/visible list, wait for a stable open state, then assert the native backing select's value. Keep a real pointer/touch and keyboard check because an intermittent UI focus issue cannot be excluded by these experiments alone. The old broad script is not a green release check and needs maintenance/revalidation against the current privacy contract before being relied on.

## 10. Smallest real-device/browser smoke checklist

Before approval, use the built candidate locally with synthetic/mocked APIs on a real iPhone Safari and one desktop Chrome/Edge browser; do not create staging/demo hosting. If production must be used, obtain explicit smoke-test authorization first because login/session/recovery/verification can write records.

1. At 320–430 px portrait width, open direct `/dic/register`, recovery, participant and Operations routes; rotate once. No clipped actions, unexpected horizontal scroll or keyboard-covered submit. Test Safari back/forward and refresh.
2. Select occupation and marital-status None by touch, then another value; tap outside, reopen and select again. Check academic/category/date controls; no hidden option selection, lost focus or stuck overlay. Desktop: Tab, Arrow keys, Enter and Escape.
3. Create-mode and Existing-mode forms show correct password-manager hints. Test a one-character/common/space-containing synthetic password, empty rejection, readable validation and one submission on a rapid double-tap. Do not disclose real passwords.
4. Recover owned pending and expired orders. Pending resumes the same order/attempt; expired does not offer a new charge; original payment status/reference remains verifiable. Passwords/tokens never appear in URLs/storage.
5. With synthetic auth responses, check paid participant access, another unpaid booking, tutor exemption, expired session, logout, slow/offline/retry, and secure same-site cookie/CSRF behaviour. Protected data must not flash before authentication.
6. Separately authorized post-release identity: existing paid participant login/dashboard/document download; ordinary staff archive access; unauthorized lifecycle action denial; designated staff decision history. Do not submit reinstatement/refund just to test a button on real records.
7. Payment smoke: complete callback/webhook/idempotency/late-timing tests using mocked provider fixtures or approved test credentials before release. Production read-only observation can inspect existing provider/webhook logs and status; no new live charge is required by default. An owner-authorized live test must specify identity, amount and reconciliation handling separately.

The prior mobile evidence was headless Chromium, not Safari or physical-device touch. Treat the checklist as a release prerequisite rather than claim that screenshots certify it.

## 11. Production backup/recovery prerequisite

Repository instructions are not a current backup. `.github/PRODUCTION_SCHEMA_RECOVERY.md` is preparation-only, includes procedures that create backups/restore disposable copies, and deliberately refuses live payment mode. It cannot be reused as an already-verified live recovery receipt. Do not dispatch it, create a backup or weaken its guards during this task.

Owner/DBA must provide read-only evidence before any schema change:

- Exact production database/service identity and PostgreSQL major; latest completed backup/snapshot or PITR restore-point timestamp and status, retention window and whether coverage includes schema plus all registration/payment/audit tables.
- Backup reference/checksum where applicable, approved secure storage, access/decryption-key custody and evidence that operators can access it. Do not attach backup contents or keys here.
- Documented restore target/procedure, responsible operator, expected recovery time/data-loss window, latest authorized restore-test result and date/version. Existing untested recovery scripts are insufficient.
- Treatment of writes after the backup: payment/webhook reconciliation plan, DNS/application cutover plan if restore is ever needed, and protection for participant media/recovery secrets stored outside PostgreSQL. A DB restore cannot undo a real Paystack charge/refund.

No current backup or workable recovery procedure was independently verified. This alone keeps schema migration NO-GO. If current evidence is missing, request separate authorization to create/validate it; do not infer that Render has an adequate backup merely because it hosts PostgreSQL.

## 12. Exact candidate artifacts and required settings

### Artifacts

- Backend: immutable reviewed release commit/archive (or image digest if that is the actual verified deployment method), containing the Phase A runtime files, migration 0041, existing complete application/migration lineage, declared `backend/requirements.txt` and established start/build configuration. Native deployment vs container deployment must come from Render metadata, not branch name. No backend release digest is established yet.
- Frontend: build the same approved candidate with `npm ci` then `npm run build`, root `dawana-platform`, output `dist` unless the verified Pages project says otherwise. Retain `_redirects`, official assets/fonts and all generated chunks. The existing local proof build is `output/phase-a/frontend-dist`: main `assets/index-C-9srb5S.js`, CSS `assets/index-CPNJ9pkZ.css`, QR fallback `assets/qrFallback-C2MM5Umq.js`. It is a validation artifact from a mixed uncommitted tree, **not** an approved production artifact. Rebuild/hash from the isolated release commit.
- Manifest: exact candidate SHA, file/asset hashes, migration hash, dependency/build environment, backend deploy/image identity, Pages deployment identity and previous rollback artifacts. Keep test adapters, disposable DB, screenshots, preview archives and owner recovery artifacts out of deployed packages.

### Configuration to verify; no changes authorized here

| Setting/contract | Required evidence |
|---|---|
| Frontend API | `VITE_API_BASE_URL=https://api.dawanaislamicfoundation.org/api/v1` at build time; changing a Pages variable does not rewrite an existing bundle/open tab. |
| Backend runtime | Actual Render runtime/root/build/start command, `DJANGO_SETTINGS_MODULE=config.settings.render` where established. Do not use staging-only `render-build.sh`/`render-start.sh` blindly; those explicitly require staging settings. Native scripts in this repo are `native-install.sh`, `native-build.sh`, `native-start.sh web`. Verify actual metadata before selecting them. |
| Hosts/origins | Existing exact backend `PUBLIC_HOST`, approved aliases if the older alias correction is selected, and exact HTTPS `FRONTEND_ORIGIN`. No wildcards, CORS regex expansion or cookie-domain broadening. Preserve the currently working domain choice. |
| Payments | Preserve existing approved live `PAYSTACK_MODE`, live-enabled gate, matching key/webhook verification secret and HTTPS callback `/dic/register/payment-return`. Source defaults are test/disabled; never replace live production values with defaults during release. No new Phase A key or refund-initiation setting is needed. |
| Authentication | Existing strong Django secret, secure HTTP-only/Lax cookies, exact CSRF/CORS origins, participant accounts enabled, shared DB cache/rate-limit table and recovery encryption/channel settings. Do not rotate secrets or enable delivery merely for this release. |
| PostgreSQL | Existing verified DB identity, role, TLS `verify-full`/CA, timeout and migration DDL authority. Test-only settings/MD5 hasher/loopback trust cluster must never be deployed as production settings. |
| Workers | Actual existing worker revision, approved actor/grants, queue/readiness and scheduler topology. Do not create another worker/service or enable an expiry schedule during code deployment. |
| Expiry | No new environment flag; inactive until explicitly approved database activation. Confirm no existing activation row before release. |

There is no evidence that a new production environment-variable change is required solely for Phase A. Verify and preserve working values; select older pending hostname/origin fixes only through their own reviewed scope.

## 13. Conditional release sequence — NOT execution authorization

1. Clear all blockers below: active deployment SHAs, exact candidate base/diff/manifest, schema history, current backup/recovery, CI and browser evidence. Record separate approvals for deployment/migration and later activation. Preserve prior artifacts and auto-deploy controls before publishing a candidate; do not let a validation branch push trigger production.
2. Prepare the isolated candidate and manifest, reconciling older owner changes deliberately. Run CI on that exact commit, including PostgreSQL concurrency/tutor partitions, frontend tests/lint/build and migration graph. Retain logs/checksums. No automatic deployment after a green build.
3. Under separately approved read-only production access, bind actual DB identity, inspect complete pending migration manifest, obtain fixed-time historical preview and confirm current backup/recovery evidence. Do not invoke any apply path yet. If only 0041 is expected, any additional pending step is a stop condition.
4. Build/retain the backend artifact without routing traffic. Under explicit migration approval, apply the **exact approved** graph using the established guarded migration command/manifest while the old application remains serving. If the platform cannot separate migration from traffic activation, stop and design an approved compatible release hook; do not launch new backend traffic without schema.
5. Verify 0041 and post-migrate permission creation, no policy activation, database health and no unexpected data changes. Failed schema step: leave old runtime serving; investigate rather than force/fake.
6. Deploy the new backend web/worker artifacts; verify all replicas' active SHA and drain old processes. Keep expiry inactive. Check web health and DB health, exact schema, API payload compatibility, stable secret/session configuration, authorized logs and no webhook 5xx regression. Coordinate workers so followup jobs retain compatible code.
7. Deploy frontend from the same approved commit, correct build-time API origin and all assets; verify direct nested-route fallback, cached/fresh tabs, callback/recovery links and asset availability. Never overwrite backend DNS or custom-domain settings.
8. Execute only separately approved smoke tests. Existing paid access/download, old/new payload compatibility, CSRF/cookies, staff denial and provider webhook observations must pass. No new real charge/refund by default. If the frontend fails, roll frontend back while keeping compatible new backend/schema.
9. Keep deployment and activation as separate gates. Owner reviews the complete historical snapshot/delta, provider exceptions and immediate activation behaviour; approve staff grants and handling capacity. Reconcile historical payment evidence under its own authorization before activating if required by the approved safety condition.
10. Only after explicit activation authorization and all web/workers are upgraded, run bounded activation/apply with the verified actor/database name, then idempotent retries from the beginning. Monitor archive counts, original refs, timely delayed success, queue health and reconciliation backlog. Do not use `--after-id` to skip interrupted apply work accidentally.

Health checks: `GET /api/v1/health/web/` checks web process only; `GET /api/v1/health/` checks DB `SELECT 1` and configured readiness. Neither certifies migration 0041, webhook signatures, provider connectivity, paid eligibility or backup readiness. Check those independently. API registration-options GET can verify JSON/CORS without submitting an order; do not use report/portal endpoints that write audit/session state as “read-only” smoke checks in this preflight.

## 14. Rollback strategy

**Before activation:** retain schema 0041, return frontend to its previous approved Pages artifact if needed, and backend to its previous verified artifact only after confirming old-code/new-schema compatibility. Preserve secrets/cookies/keys and recorded data. New short passwords still authenticate in old Django login, but old signup/reset UI can reject them; coordinate rollback of policy and frontend rather than mix contracts. Keep webhook processing available; do not revoke participant access to undo a UI regression.

**After activation:** an old backend ignores the expiry policy, so a blind code rollback can accept genuinely late payments and permit new charges. Prefer a forward correction/compatible hotfix. If collection must pause, use an already reviewed separately authorized operational control that preserves webhook verification/status recovery; this preflight does not establish or approve a new switch. Keep active schema, audit and resolution records. Do not delete the singleton, truncate archives, reverse migration 0041 or bulk reopen orders. A separately reviewed deactivation/control implementation is needed if an emergency reversible activation switch is desired.

**Database recovery:** use only the verified approved recovery procedure under explicit incident authorization. Do not restore an old database merely to undo additive schema/UI changes; it could erase newer payments. Reconcile post-backup provider transactions and staff decisions. Refunds/reinstatements are financial actions, not undone by deploying old code.

## 15. Blockers and final recommendation

| Blocker | Required owner/operator action |
|---|---|
| Active frontend/backend/worker identities unknown | Supply sanitized active deployment metadata with full SHAs and current topology. |
| Mixed, uncommitted candidate and no immutable artifact manifest | Authorize isolated release preparation against verified base; select older dependencies deliberately and bind artifacts/CI to the resulting commit. |
| Production schema/role/lock/identity unverified | Approved read-only schema/manifest/target inspection; verify migration role and plan. Resolve any managed-provider planner permission limitation explicitly. |
| Current backup and recovery not verified | Supply current backup/PITR and restore-procedure/test/access evidence; authorize any missing backup validation separately. |
| Schema-before-runtime cutover not confirmed in actual Render configuration | Verify the current release controls support migration before new traffic, with old runtime compatibility and worker coordination. |
| Complete historical cohort/provider readiness not reviewed | Obtain fixed-time read-only preview plus delta; review in-flight/ambiguous transactions and the activation-before-batch-verification effect. |
| Staff resolver grants unknown | Name designated active staff and review exact grants; no automatic group-wide financial expansion. |
| Browser release evidence incomplete | Maintain the ambiguous old harness and run the minimal real Safari/pointer smoke checklist; do not rely on headless mobile screenshots alone. |

**NO-GO.** Local tests support the implementation, but do not establish production revision/schema compatibility, backup readiness, an isolated releasable artifact or safe activation readiness. Code deployment and expiry activation are separate decisions; neither is authorized by this document. No production operation was performed. Stop here and await explicit deployment approval after the recorded blockers are resolved.
