# DAWANA controlled production release candidate

Status: prepared and locally validated; **not approved for production**.
GitHub Actions/PostgreSQL validation remains blocked, not passed.

## Scope and source identity

This consolidates PRODUCTION_HOSTNAME_REVIEW.md, OPERATIONS_AUTH_REVIEW.md and
DIC_PAYMENT_FAILURE_REVIEW.md. Their earlier test counts and pending checks are
historical; the results here supersede those counts. Existing unrelated work is
retained in the working tree and excluded from the candidate patch.

Patch base: `7a9c97845541c56820380b9756eac4c4c5eeb093`, current local branch
`deployment/container-packaging`. This is not a claim that the base is the deployed
production revision. Confirm the production revision before preparing a release
branch; do not force-apply against a different base or use `git add .`.

`release-validation/production-release.patch` contains only the 21 paths below.
`release-validation/release-manifest.json` records the base and SHA-256 of each
file. Both are local review artifacts, not deployed artifacts or CI evidence.

### Exact included files

Runtime source (5):

1. `backend/config/native_defaults.py`
2. `backend/dic/templates/admin/base_site.html`
3. `dawana-platform/src/pages/DIC.jsx`
4. `dawana-platform/src/services/dicApi.js`
5. `dawana-platform/src/services/paymentReturnApi.js`

Backend regressions (6):

6. `backend/config/test_native_deployment.py`
7. `backend/config/test_render_deployment.py`
8. `backend/config/test_operations_security.py`
9. `backend/config/test_public_hosts.py`
10. `backend/dic/test_checkout_validation.py`
11. `backend/dic/test_payment_return.py`

Frontend regressions (3):

12. `dawana-platform/src/services/dicApi.test.js`
13. `dawana-platform/src/services/operationsApi.test.js`
14. `dawana-platform/src/services/paymentReturnApi.test.js`

CI/configuration documentation (3):

15. `.github/workflows/backend-acceptance.yml`
16. `scripts/test_production_policies.py`
17. `backend/render.env.example`

Review/release documentation (4):

18. `PRODUCTION_HOSTNAME_REVIEW.md`
19. `OPERATIONS_AUTH_REVIEW.md`
20. `DIC_PAYMENT_FAILURE_REVIEW.md`
21. `CONSOLIDATED_PRODUCTION_RELEASE.md`

Excluded: existing staging preparation/environment edits, native-start.sh edits,
bootstrap/schema-recovery code and workflows, prior source-review archives,
preview/build directories, caches and local validation adapters/logs. None were
removed or reverted. No migrations, dependency versions/lockfiles, credentials,
payment variables, database contents, payment records or DNS are changed.

## Compatibility and security review

- PUBLIC_HOST remains one strictly validated exact hostname. Optional
  PUBLIC_HOST_ALIASES adds only explicit exact hosts, deduplicates them and
  rejects malformed entries, wildcard/leading-dot patterns, ports, paths and
  whitespace. With the alias unset, behavior remains single-host. Production
  validation still rejects permissive hosts. Managed ingress still checks Host
  before routing and rejects spoofed forwarded hosts.
- Admin Operations navigation uses the already validated FRONTEND_ORIGIN
  through public_site_url, preserving its Operations permission condition.
- Frontend Operations login already includes cookies and a fresh CSRF header;
  its post-login CSRF refresh is preserved. No CSRF exemption or authentication
  permission change is introduced. The custom sibling API makes browser requests
  same-site while remaining cross-origin, compatible with Secure host-only Lax
  cookies and exact credentialed CORS. Browser acceptance still needs validation.
- Order creation remains bearer-only, with its existing UUIDv4 idempotency key.
  Nested DRF errors now surface bounded, labelled validation messages, supporting
  both list and sparse participant-index maps. Unknown fields/non-JSON retain a
  generic fallback; no request payloads, credentials or raw error objects are
  logged or persisted. Existing stronger Django password validation is retained.
- Secure-return setup now reports fixed guidance without discarding the failure
  category. Its origin guard, CSRF and database session/grant binding remain in
  force. Grant-only retries do not initialize payment. No initialization, pricing,
  callback, webhook, settlement or entitlement implementation was modified.
- Approved 2026 prices, price snapshots and completion-time rules are untouched.
  Paystack live-mode/key matching, HTTPS/provider validation, signature checks,
  independent verification, unique transaction identities, reconciliation rules
  and the complimentary tutor authorization boundary remain unchanged.
- Consolidation fixed one test-fixture defect: the Render startup test now uses
  the supplied PUBLIC_HOST rather than a hardcoded fixture hostname. The workflow
  now runs the entire frontend suite/lint/build, and the default database-free
  policy suite includes all eight Render startup tests.

The exact production CSRF rejection and second checkout's HTTP 400 validation
field are still unconfirmed. The source proves the hosting incompatibility and
hidden nested-error mechanism, not the participants' exact inputs. A health 200
alone cannot establish cookie persistence or payment correctness.

## Validation results

| Check | Actual result |
| --- | --- |
| Complete frontend `npm test` | 308 passed, 0 failed/skipped |
| Complete frontend `npm run lint` | Passed |
| Production build with the exact custom API URL | Passed; compiled entry contains the custom API URL and not the old Render hostname |
| Complete configured backend policy suite | 265 passed, 0 failures/errors/skips; includes all 8 real Render settings/WSGI startup tests |
| Both exact hostname health routes and foreign-host rejection | Passed, including real startup settings and mocked database health probes |
| Backend/CI Python syntax | 335 files parsed without execution/bytecode |
| Whitespace check | `git diff --check` passed |
| GitHub Actions | Not started: shell HTTPS to GitHub fails; GitHub integration is not connected |
| PostgreSQL 14/18 integration matrix | Not run; a release gate, not a waiver |
| Production browser/payment acceptance | Not run; requires approved rollout |

Logs are retained under release-validation: frontend-tests.log,
frontend-lint.log, frontend-build.log and backend-policy-consolidated.log.
The build used a separate local frontend-production-dist directory, preserving
existing dist/preview artifacts. Vite emitted the existing large-chunk warning
and an informational notice that the external output directory would not be
emptied. Neither was a build failure.

The first full local backend attempt failed from unavailable local dependencies:
the workspace virtualenv targets inaccessible Python 3.13, the available bundled
Python is 3.12, and subprocesses initially could not find django-environ/libpq.
The final run used release-validation/run_local_policy.py, a local-only adapter
that appends workspace pure-Python dependencies, loads the existing libpq DLL
through psycopg's pure-Python implementation, and supplies the same paths to
isolated startup subprocesses. Database and network guards remain active. No
packages, interpreter, virtualenv files, production settings or CI guards were
modified. The final combined run passed all 265 tests. This local adapter is
excluded from the release and does not substitute for clean Linux CI.

### GitHub Actions gate

The prepared backend-acceptance.yml runs full frontend tests/lint/build, the full
database-free policy suite, and eight disposable PostgreSQL jobs: versions 14
and 18 across core/tutor/movement/assistance. The existing guarded runner checks
migration graph/model drift, migrates and verifies a uniquely named temporary
CI database, and runs all backend app test partitions. It uses no production
credentials or services. Do not spoof its GitHub/connection guards to run it
against a local or production database.

To proceed, establish the GitHub connection/HTTPS access, publish only the scoped
candidate on a validation ref without merging or deploying, then run
backend-acceptance.yml against that exact candidate commit (manual dispatch or
PR checks). Review repository/provider branch automation before publishing the
ref so validation does not trigger an unapproved deployment. Record its commit
SHA, run URL, frontend/policy job results and all eight PostgreSQL job reports.
Do not use a green run for the old remote commit as evidence for this uncommitted
candidate. Existing native-packaging checks should also pass on the candidate PR.

No remote branch/PR/commit, workflow run or GitHub validation result was created
in this session. The GitHub integration was found but is not connected; a
connection was offered. PostgreSQL acceptance cannot be reported green yet.

## Required environment changes

### Render: after approval, with the alias-support source revision

```dotenv
PUBLIC_HOST=dawana-islamic-foundation-web-app-1.onrender.com
PUBLIC_HOST_ALIASES=api.dawanaislamicfoundation.org
FRONTEND_ORIGIN=https://dawanaislamicfoundation.org
```

Keep the existing PUBLIC_HOST. Add PUBLIC_HOST_ALIASES. Keep FRONTEND_ORIGIN if it
already has the value above; change it only if it is currently wrong, after
owner approval. It must identify the canonical frontend, not the API hostname.
The source derives these settings; do not attempt to override them separately:

```text
ALLOWED_HOSTS = [existing Render hostname, api.dawanaislamicfoundation.org]
CSRF_TRUSTED_ORIGINS = [https://dawanaislamicfoundation.org]
CORS_ALLOWED_ORIGINS = [https://dawanaislamicfoundation.org]
```

No other Render variable is required for this patch. Keep the current settings
module, keys, live payment mode/approval, callback, webhook signing setup, database,
feature flags, HTTPS redirects, HttpOnly/Secure host-only Lax cookies and proxy
trust configuration. The alias variable requires this source deployment once;
the old code ignores it and cannot accept both hostnames through environment
configuration alone. Process reload is needed for settings changes.

### Cloudflare Pages: Production build environment

Set this exact public build variable (no trailing slash):

```dotenv
VITE_API_BASE_URL=https://api.dawanaislamicfoundation.org/api/v1
```

Set it for the Production environment of the existing Pages frontend project.
This is a public URL, not a secret. Vite embeds it at build time: changing the
environment alone does not update the deployed JavaScript. The source default
is /api/v1, and .env.production.example is documentation, not an automatically
loaded .env file. The ordinary production npm run build validates the value in
vite.config.js. Use the existing frontend project/root and output dist; do not
use the Netlify-specific build:staging command. No Pages variable or deployment
was changed here. Preview environments must retain their own approved policy.

## Safe rollout order: owner approval required

1. Confirm deployed revision/baseline and the 21-file diff. Obtain green clean CI,
   including every PostgreSQL matrix job, for the exact candidate commit. Resolve
   any failure before requesting production deployment approval.
2. Record the existing Render/Pages revisions and nonsecret environment values
   for rollback. Confirm the already verified custom domain/certificate; do not
   modify DNS or credentials. Check for in-progress checkouts before the host
   switch, and plan existing-registration recovery instead of new registration.
3. After explicit approval, release the backend patch with the exact alias and
   canonical frontend origin. Retain the original Render hostname. This patch
   adds no migrations; do not run unrelated schema recovery/bootstrap, migrations,
   feature activation or payment-mode changes as part of this release.
4. Check HTTPS health on both backend hostnames. Verify the custom host accepts
   only the configured frontend CORS origin and issues/sends CSRF cookies. Check
   Admin's Operations link and an authorized Operations login/me/logout with CSRF
   rotation. Verify missing cookies/tokens and foreign origins remain rejected.
5. After backend acceptance, set the Pages Production API variable, build the
   same approved source and approve the frontend deployment. Verify direct SPA
   Operations/callback routes and actual API requests use the custom hostname.
   The old hostname remains valid for existing API consumers during transition.
6. Validate return-session persistence across callback tabs and safe validation
   errors, then perform only the explicitly approved single controlled payment
   continuation described below. Pause on any unknown/reconciliation outcome.
7. Rollback, if required, is a separately approved revision/environment action,
   with no database rollback or payment-record edits. Preserve the alias while
   any frontend still targets the custom API; removing it first breaks clients.
   Reverting Pages to direct Render hosting reintroduces the known Lax-cookie/
   return-origin incompatibility and is not a payment-functionality recovery.

## Recover the existing ₦4,000 attempt without another initialization

1. An authorized owner checks the existing order and its original Paystack
   reference, provider_mode, amount, status and accepted pricing window. Do not
   register again, change historical mode/price, initialize a replacement, accept
   repricing, or open a second authorization to bypass this failure. If charged,
   successful, unknown, test-mode or reconciliation-required, stop for authorized
   verification/reconciliation before offering payment.
2. If the original tab still has valid order authority **and already uses the
   correct API host**, use Retry secure return setup. It calls fresh /csrf/ plus
   the existing order's payment-return-grant endpoint only; it never calls order
   creation or payment initialization. Confirm the reference/attempt count is
   unchanged and the CSRF/session cookies are accepted and replayed.
3. A frontend deployment does not rewrite an already open tab's API constant.
   If that tab still runs the old Render-targeting bundle, its retry will retain
   the old hosting failure. After the approved frontend switch, use the existing
   verified registration-recovery flow to restore **the same order** in the new
   bundle/host. Refresh loses the in-memory bearer; cookies and grants issued on
   the Render hostname do not transfer to the custom hostname. Do not copy bearer
   values into URLs/storage or create another order. If verified recovery is not
   available, pause for authorized support rather than enabling unrelated delivery
   features or registering again.
4. Once authority and the new host's grant are established, verify the original
   reference before any new payment. Successful settlement requires independent
   live Paystack evidence and application verification, not a redirect or debit
   message. If still pending/unpaid and its ₦4,000 quote is valid, continue only
   the original authorization once, after explicit controlled-payment approval.
   Expected amount is 400,000 kobo, NGN, with matching reference/live mode and
   qualifying provider-confirmed paid_at. If the price window expired, pause;
   do not force the old fee or initialize a new quote in this recovery procedure.
5. Verify one successful attempt/confirmed order and idempotent callback/webhook
   processing. Pending/unknown results require further verification, never another
   charge. An old Paystack authorization can remain externally payable after
   repricing; that is why this procedure does not reprice or open multiple links.

This document authorizes no production operation. All rollout and recovery
actions above remain pending approval; no production data or payment was touched.
