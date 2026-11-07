# Current production initialization contract ? implementation preparation

This section supersedes the historical reference below. Nothing here provisions
or deploys a service. See PRODUCTION_REMEDIATION.md for R01?R18, policy approvals,
security contracts, scheduling, migration identity and remaining acceptance gates.

The preferred topology is one public HTTPS browser origin with /api/v1 routed
to Django. It remains conditional on owner-approved provider/gateway feasibility.
Do not deploy separate frontend/API origins or remove the payment-return guard.
Use VITE_API_BASE_URL=/api/v1; production builds reject other values. Reserve
/api, /admin, /static, /media and /health before SPA fallback; never serve private
media directly or cache API/admin responses. Deep-link fallback applies only to
frontend routes. Paystack callback is /dic/register/payment-return; webhook is
/api/v1/dic/payments/paystack/webhook/.

| Component | Provider-neutral configuration requiring runtime acceptance |
| --- | --- |
| Backend package root | Repository root, not backend |
| Build | bash backend/production-build.sh |
| Start | bash backend/production-start.sh |
| Settings | config.settings.production |
| WSGI | config.wsgi:application |
| Health | /api/v1/health/ |
| Frontend package root | dawana-platform |
| Frontend build | npm ci && npm run build |
| Output | dist, served through the approved same-origin gateway |

Builds require Python 3.13, declared Python dependencies, approved Liberation
fonts and working ffprobe. They never migrate, create cache tables or initialize
data. Production source supports self-managed, render and explicit managed
modes. The managed mode requires an approved bind address and validated port;
self-managed remains loopback-only. Neither provider is provisioned or selected
by these source changes. Existing Render compatibility is retained, not a launch
approval. Naijacloud capabilities remain subject to evidence and acceptance.

Keep PostgreSQL verify-full, exact HTTPS origins/hosts, secure cookies, trusted
immediate-gateway IP handling and durable shared throttles. Never enable trust
for arbitrary forwarded headers. See ops/production/gateway.nginx.conf.example
for a direct-edge template; it is not a managed-ingress configuration.

Production starts empty. No local/demo records, databases or portraits are
transferred; do not run historical portrait-cutover helpers. Configure distinct
production R2 editorial/private credentials and verify private storage separately.

Migration planning itself needs target-access approval. The release_migrations
command now requires --database-name, --hostname, --port, --role and --cluster-id.
It binds server-reported PostgreSQL identity into the exact hashed approval
manifest. Provider inspection privileges, backup and independent restore evidence
must be available first. All migration/application/cache/admin operations remain
separate approvals, outside build/start. No persistent database was accessed here.

Registration remains closed pending acceptance and owner approval. Owner supplies
registration dates/Early Bird cutoff. Preserve approved fees and tutor exemption.
Refund/access and global-versus-edition staff authority policies remain pending.
Email/password only; donations, Google sign-in and deferred games remain disabled.
Paystack live merchant/official settlement approval and activation are separate.

# Historical reference ? superseded deployment proposals and audit evidence

Everything below is retained for traceability, including contradictory older
Render/separate-origin proposals and old acceptance results. It is NOT the current
deployment contract or evidence that this new patch passed CI. Do not execute
historical commands without reconciling them with the current contract above.

# Direct production release: source preparation, not launch authorization

No provider, domain, database or service is provisioned by this plan. No preview
or staging deployment is required. Do not execute database commands until the
owner approves the precise production identity and migration manifest.

## Authoritative first-production configuration — correction pass 4

This is proposed configuration only. No Render service, database, domain, bucket,
credential or deployment is established or verified by this document. Production
starts with a new, empty database. No local/demo database, participant records or
portraits are backed up, restored, copied or transferred into production. Do not
run portrait cutover helpers during initial setup. Verify the production target's
own empty participant/portrait inventory before separately approving its storage
readiness flag. No demo or staging environment is part of this release.

| Component | Proposed Render configuration |
| --- | --- |
| Backend root directory | Repository root (leave Render Root Directory blank), not `backend` |
| Backend build | `bash backend/production-build.sh` |
| Backend start | `bash backend/production-start.sh` |
| Django settings | `config.settings.production` |
| WSGI application | `config.wsgi:application` |
| Backend health endpoint | `/api/v1/health/` |
| Frontend root directory | `dawana-platform` |
| Frontend build | `npm ci && npm run build` |
| Frontend publish directory | `dist` |
| Render SPA rewrite | Source `/*`, destination `/index.html`, action Rewrite |

The backend needs repository-root access because STATICFILES_DIRS includes the
sibling `dawana-platform/public` directory. Build/start scripts change into
`backend` themselves. Configure the SPA rewrite in Render; a `_redirects` file
alone does not configure Render routing. No Nginx service is required by this
Render proposal. The retained same-host example is historical/alternative only.

Use separate HTTPS frontend and API origins under the same registrable site.
Set VITE_API_BASE_URL to the approved API origin followed by `/api/v1` before
building; keep exact credentialed CORS/CSRF origins and SameSite=Lax. Provider
secrets belong only in backend secret configuration. Owner-approved registration
dates and Early Bird cutoff remain unset until supplied; registration stays
closed until production acceptance and explicit owner approval. Email/password
is the approved participant sign-in. Google credentials remain unset. Foundation
donations, Millionaire and Family Feud remain disabled/deferred.

## Clean target and secrets

Provision a new, independently named PostgreSQL database with a separate migration
owner and restricted application login (no CREATEDB, CREATEROLE or superuser).
Verify host, port, cluster identity, database name, OID and ownership before writes.
Do not restore any development dump or connect to dawana_dev, dic_2026_demo,
protected OID 25041, or a historical test/preview database. OIDs are cluster-local:
check cluster identity as well as OID; names alone do not prove isolation.
Restrict database networking to the backend and operator path. Configure backups,
retention, encryption and an approved restore procedure before public traffic.
Provisioning, hosting, email, object storage, backups and payment-provider actions
can incur costs and require separate approval.

Use deployment secrets, not copied local .env files. Select
DJANGO_SETTINGS_MODULE=config.settings.production explicitly. Configure an
independent strong DJANGO_SECRET_KEY, exact allowed hosts, and HTTPS origins.
Use PostgreSQL DB_SSLMODE=verify-full with the correct hostname and CA trust
(DB_SSLROOTCERT where required). Production does not silently downgrade TLS.
Configure database identity/credentials securely; never paste them into reports.

## Migration review and clean initialization (future approved actions only)

1. Review the release's full migration graph and source hashes against the empty
   target; use the existing release_migrations manifest/approval mechanism.
   Plan inspection itself connects to its named database: do not run it before
   target approval. Never place migrations in build/start hooks.
2. Review dic.0014 and dic.0015 PostgreSQL functions/triggers; SQLite is not a valid
   integration-test substitute. Review ordering, including 0030's run_before edge.
   Historical backfills 0010/0012/0022 operate on existing rows and should have no
   development records on the empty target. Do not edit historical migrations.
3. dic.0034 seeds the five fees and an inactive draft edition. It intentionally
   preserves non-null administrator prices. No Early Bird deadline is invented.
4. New dic.0035 adds provider_mode to payment attempts and donations. Existing rows
   are classified test because the prior implementation was test-only; any target
   with live history requires investigation before applying this assumption.
   It corrects only known obsolete/blank venue and name values, and fills a missing
   theme. Custom venue/name/theme values remain for explicit review. Fees, payment
   amounts, snapshots and registration windows are untouched. It does not open
   registration. Official details are Darul Islam Camp, The Outliers,
   23 December 2026–1 January 2027, Fazil Umar Secondary School, Lagos.
5. Apply only the approved forward manifest. Separately approve creation of
   dawana_release_cache with Django's cache-table command; it is not a migration.
6. Allow only Django technical content types/permissions, the official edition,
   and five approved fee categories initially. Do not load fixtures, acceptance
   records, synthetic donations, demo accounts or registration data. Inspect
   effective prices: Early Bird/Regular NGN 4000/5000, 10000/12000, 12000/15000,
   15000/17000, 18000/18500. Review legacy venue fields/directions before publication.
7. Create named production administrators securely; do not seed a password or test
   admin. Preview and explicitly approve operational role grants. Finance, welfare,
   participant contact access and exports require separate least-privilege review.
8. Verify participant accounts, bookings, campers, attempts, donations and recovery
   sessions are empty. Only authorized administrators and approved reference data
   should exist. Record sanitized counts and migration hashes as release evidence.

Do not reverse migrations as a payment rollback. 0034/0035 data corrections have
no-op reversals; reversing schema loses mode metadata. Once live transactions
exist, use a reviewed forward fix and reconcile against provider evidence. A
database restore can lose subsequent legitimate payments; stop traffic and agree
the reconciliation/restore procedure first. Never test restore over this database.

## Authentication and legacy dependencies

Enable DIC_PORTAL_ACCOUNTS_ENABLED only with the approved schema. Configure
DIC_PORTAL_EMAIL_VERIFY_URL=https://APPROVED_HOST/dic/participant (no query/fragment).
Use TLS SMTP with a verified sender; configure email/contact-code recovery and its
encryption key/worker separately. Confirm real delivery without logging links,
passwords, OTPs or personal data. The new account is inactive until email proof;
verified ordinary payment or explicit tutor entitlement separately gates access.

Legacy booking OTP, account activation and username login remain because older
bookings, password recovery, booking linkage and tutor access depend on them.
Do not remove endpoints until usage is reviewed, recovery has a tested replacement
and existing account migration is approved. Google is not part of new registration;
leave Google credentials unset. Existing optional backend code is not newly enabled.

## Routing, transport and operations

Use the separate same-site HTTPS Render origins specified above, with an absolute
VITE_API_BASE_URL. The retained Nginx example describes a historical alternative;
do not install it for this release. The frontend SPA rewrite belongs only on the
static site; API/admin/static backend requests go to the Django service.
Existing render-* scripts are historical staging tools; production-build.sh and
production-start.sh require explicit production settings and never migrate/seed.
The existing dependency constraint filename is historical, not a staging deployment.

Trust forwarded HTTPS headers only when the proxy strips client-supplied headers,
and prevent direct public access to Gunicorn. Set DJANGO_TRUST_PROXY_HTTPS only after
that review. HSTS starts at one hour without subdomain/preload claims; approve full
hostname coverage before increasing it. Django deploy-check warnings must be
reviewed even when the build has no errors. Terminate TLS with valid certificates.

Private media stays disabled until private object storage is configured; local
media storage is rejected in production. Review bucket IAM, encryption, lifecycle,
egress/cost, ffprobe availability and authenticated media delivery. Existing photo
validation and MP4 validation remain in force. Match proxy upload/body limits and
timeouts to approved limits. Do not expose the filesystem media root publicly.

Monitor /api/v1/health/ privately for database readiness; it performs SELECT 1.
It does not prove email, cache, media or Paystack readiness. Monitor those separately
with privacy-reviewed logs/alerts; do not log query strings, OTPs, bearer credentials,
webhook signatures or payment payloads. Validate backup restoration off-target.

## Payments: prepared capability, disabled live activation

PAYSTACK_MODE defaults to test and PAYSTACK_LIVE_ENABLED defaults false. Test keys
are rejected in live mode and live keys in test mode. Live requires DEBUG=false,
an HTTPS callback and PAYSTACK_LIVE_ENABLED=true; this flag is an operator gate,
not evidence that the owner or provider has approved activation. Do not set it now.
FOUNDATION_DONATIONS_ENABLED must remain false: donations are deferred and are
not a condition for live DIC payment readiness.

Every new attempt/donation records provider_mode. Settlement requires stored mode,
runtime mode and verified provider domain to match, alongside existing exact amount,
NGN currency, reference and settlement protections. Existing test attempts cannot
be replayed as live checkouts. Use a fresh production database, not mode switching
with unresolved transactions. Completed payment snapshots remain immutable.

Participant entitlement independently rechecks the stored attempt mode on every
read. Production settings permit paid entitlement only with runtime live mode and
stored live evidence; successful test payments never become live entitlements.
Non-production test-mode policy remains available without granting production
access. PaymentAttempt is the existing Paystack-only record: its trusted verifier
checks the fixed Paystack provider response, reference, unique transaction ID,
amount, currency and verified domain before settlement. Matching mode alone is
insufficient. Existing accepted-price/payment-time and reconciliation gates still
apply. The authorized complimentary tutor branch remains independent of payment.

Legacy X-Paystack-Signature HMAC remains supported. PAYSTACK_WEBHOOK_SECRET selects
the timestamped Paystack-Signature scheme with a five-minute tolerance and no
fallback to the legacy header. Configure the correct mode-specific signing secret
only after verifying delivery format; synchronize server clocks and plan rotation.
Webhook acknowledgement still follows durable processing, so provider retries can
recover failures. Existing deduplication and server verification remain required.
Verify dashboard webhook URL, callback route, key mode, signature format, settlement,
retry/duplicate behaviour and authorized reconciliation before collection approval.
Real payment/refund tests incur financial effects and need separate approval.

## Validation and owner decisions

Database-free backend policy command (does not read .env, migrate or create a DB):

```powershell
& .\backend\.venv\Scripts\python.exe -I -B .\scripts\test_production_policies.py
```

Full registration/payment/concurrency and migration behavior remains unverified.
An owner-approved acceptance protocol is still required; this release plan does
not authorize creating a local/demo/staging target or reusing an old receipt.
Complete browser/email/payment acceptance without putting synthetic records into
the clean production database. No full-backend pass may be inferred from source.

Outstanding owner approvals: production provider/domain/budget, exact database
identity, migration manifest, named administrators/roles, SMTP/recovery/private
storage, Early Bird cutoff and registration window, housing inventory/policies,
official classes/timetable publication as needed, payment activation and launch.
Keep registration draft/closed until windows and cutoff policy are approved.
Millionaire and Family Feud remain deferred and do not block launch.

## Implementation evidence, 6 November 2026

The sections below retain historical correction evidence, alternative topology
analysis and earlier test results. They are not current provisioning instructions
or proof of deployed configuration. The authoritative correction-pass-4 section
above governs the first production release; historical local/test/transfer
procedures must not be executed as production initialization.

Branch remains staging/dawana-e2e, HEAD 986b863; this branch name is historical,
not a plan for hosted staging. All pre-existing tracked and untracked fee work
was preserved. No .env changes, database connections, migrations, service control,
payment requests, commits, pushes or deployments were performed.

### Files changed in this implementation

| Files | Reason |
| --- | --- |
| backend/config/settings/base.py | Add default-off live activation and optional webhook signing-secret settings. |
| backend/config/settings/production.py | Certificate/hostname-verified PostgreSQL, explicit proxy trust and configurable conservative HSTS. |
| backend/config/release_security.py | Validate mode/key separation, explicit live activation and secure live callback configuration. |
| backend/dic/payments.py | Guard live client creation; retain strict test keys; validate legacy and timestamped signatures. |
| backend/dic/payment_views.py | Persist attempt mode, reject cross-mode replay/verification and verify the selected webhook scheme. |
| backend/dic/models.py | Add attempt provider_mode alongside the preserved existing fee changes. |
| backend/dic/admin.py | Show/filter payment mode in finance views; preserve the existing fee-admin change. |
| backend/dic/foundation_api.py | Apply the same guarded mode/key/signature policy to donations, preserving its separate activation switch. |
| backend/dic/foundation_models.py, foundation_admin.py | Persist donation mode and display it read-only to authorized operators. |
| backend/dic/registration_accounts.py, portal_account_api.py | Align verification email/API wording with ordinary-payment and authorized-tutor eligibility. |
| backend/dic/management/commands/setup_dic_2026.py | Correct official name/venue and supply the approved theme for newly created drafts. |
| backend/dic/migrations/0035_production_payment_mode_and_official_details.py | Unapplied additive mode fields and selective forward official-details correction. |
| backend/dic/tests.py | Update the setup command's expected venue/theme; preserve the existing mixed-fee fixture fix. |
| backend/dic/test_launch_completion.py | Extend synthetic donation fixtures with stored test mode. |
| backend/dic/test_payment_hardening.py | Add database-backed cross-mode rejection and live-proof settlement regressions (not executed here). |
| backend/dic/test_production_payments.py | Add database-free activation/key, mode and signature regression coverage (not executed here). |
| dawana-platform/src/components/dic/PortalAccountAccess.jsx | Explain normal registration versus legacy recovery; remove obsolete Google messaging. |
| dawana-platform/src/components/dic/PrimaryRegistrantFields.jsx | Preserve email/password collection and explain tutor payment exemption. |
| dawana-platform/src/pages/ParticipantPortal.jsx | Replace obsolete Google failure messaging with email/password recovery guidance. |
| dawana-platform/src/pages/DIC.jsx | Correct confirmation journey, show API-supplied theme and use mode-neutral checkout wording. |
| backend/production-build.sh, production-start.sh | Explicit production entry points with no migration, seeding or activation hooks. |
| deployment/nginx.production.example.conf | Reviewable same-origin routing and private backend boundary; not installed. |
| scripts/test_production_policies.py | Standalone no-dotenv, no-database, no-network policy runner. |
| PRODUCTION_INITIALIZATION_PLAN.md | Clean initialization, operations, migration risks, dependencies and approval gates. |

Other pre-existing fee files and the abandoned preview plan were not removed or
repurposed. Historical migration 0034 was not changed or executed.

### Actual checks

- Frontend: `npm.cmd test` — 226 tests, 226 passed, 0 failed/skipped; final run
  duration 23281.9385 ms. These include frontend authentication/tutor regressions;
  they are not evidence of real backend authentication or provider operation.
- Frontend: `npm.cmd run lint` — exit 0, no diagnostics.
- Frontend production build: session-only VITE_API_BASE_URL=/api/v1 and
  `npm.cmd run build -- --outDir ../output/production-readiness-build-1ecf036b09a043b3921fa63c617e38e7`
  — exit 0, 363 modules transformed. Bundle warning: main JS 666.14 kB
  (183.08 kB gzip), above the 500 kB warning threshold. New output directories
  preserved existing artifacts; Vite explicitly did not empty the outside-root path.
- `git diff --check` — exit 0; Git printed LF/CRLF conversion notices.
- `backend/.venv/Scripts/python.exe -I -B scripts/test_production_policies.py`
  — interpreter failed before tests: `did not find executable at
  'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.`
- Safe alternate `py -3.13 -I -B -c "print('available')"` — could not start the
  registered WindowsApps Python interpreter: `Access is denied.` No interpreter
  installation, environment modification or security bypass was attempted.
- Initial PowerShell `npm run lint/build` calls were blocked by npm.ps1 execution
  policy; npm.cmd ran successfully without changing execution policy.

Backend policy tests, Django deploy checks, model/migration autodetection, full
PostgreSQL suites, nginx syntax validation, real email and live-provider acceptance
remain NOT VERIFIED. Existing paid/tutor eligibility, snapshot and permission
enforcement were inspected and left intact; runtime preservation still requires
backend regression execution. This release is prepared for review, NOT approved
or verified for production launch.

## Correction pass 1: proxy boundary and media decision

The registration handoff now explicitly distinguishes ordinary paid access from
authorized complimentary tutors, retaining email verification, email/password
sign-in and supported contact-code recovery. This is copy only. Authentication,
tutor entitlement, all fees and snapshots, and age rules are unchanged. In
particular a non-tertiary 17-year-old declared a minor remains eligible for the
Graduates & Adults payment category. Foundation donations remain deferred; do not
enable FOUNDATION_DONATIONS_ENABLED. This pass changes no collection flags.

### Historical same-host topology — superseded for the Render release

gunicorn.conf.py now binds exactly 127.0.0.1:10000, matching all three Nginx
upstreams. It accepts forwarded scheme headers only from 127.0.0.1 and only
X-Forwarded-Proto. PORT no longer changes this shared-config bind. This is a
same-host proposal; a container or managed-host topology must be explicitly
reviewed before adapting the bind. Existing services were not restarted.

Nginx overwrites Host, X-Forwarded-Proto, X-Forwarded-For and X-Real-IP rather than
appending arbitrary client headers. Do not configure real_ip_header or broaden
Gunicorn's forwarded_allow_ips without an approved trusted-proxy topology.
Django keeps exact ALLOWED_HOSTS and defaults to not trusting forwarded HTTPS;
enable DJANGO_TRUST_PROXY_HTTPS only behind this verified, private backend boundary.
Django does not automatically turn X-Forwarded-For into REMOTE_ADDR: IP-based
application throttles may see the loopback proxy, so evaluate expected traffic
before launch rather than trusting client-supplied IP headers in application code.

The example redirects to the approved fixed hostname, blocks both /media and
/media/, retains a 105 MiB request cap for 100 MiB MP4 plus multipart overhead,
and adds 60s client-body, 5s upstream-connect and 65s send/read inactivity timeouts.
Gunicorn's existing 60s worker timeout is retained; with gthread it is not a
guarantee of a 60s per-request execution limit. Capacity and slow-upload/streaming
behaviour require validation on the selected host. Nginx buffers requests by
default; configure restricted temporary disk capacity for large uploads.
These are inactivity limits, not a complete abuse/traffic policy.

No certificate, hostname routing, firewall or installed Nginx configuration has
been verified. The example still contains placeholders and is not deployable
until reviewed. No TLS deployment or direct-exposure test is claimed.

### Media inventory and authorization boundary

Inspected file fields: participant enrollment portraits, camp photographs/video
thumbnails, promotional videos/posters/flyers, lecturer photographs and activity
photographs. They explicitly use PrivateMemoryStorage or PrivatePromoStorage;
none relies on the production STORAGES default filesystem backend. There is no
generic participant document upload field in this inspected inventory.

Production's generic FileSystemStorage default does not establish durability and
is not approved for future sensitive uploads. Do not add such a field using the
default backend without reviewing storage and its download authorization.
Do not place uploads in frontend public/, Django static paths or the deploy tree.

PrivateMemoryStorage rejects local mode outside DEBUG, and the production default
for these upload classes is disabled. Existing S3-compatible capability uses a
private bucket through Django server-side reads; storage.url() deliberately
raises instead of publishing an object URL. PrivatePromoStorage shares the private
object-store boundary with bounded/range video delivery. No provider is configured
or selected by this plan, and no public object URL or bucket ACL is enabled.

Logical public/private separation currently occurs in Django views, not separate
buckets or object prefixes: photographs are assigned random memories/ names,
including protected portraits. Public gallery/editorial/showcase endpoints serve
only published records; draft previews require active staff and model permission.
Participant ID/PDF access passes through scoped enrollment and eligible-session
checks before portrait rendering. These source checks must remain in the download
path. Object possession or guessed paths must never authorize a protected download.
Source inspection is not a runtime cross-account download acceptance test.

### Exact decisions requiring owner approval

1. Select hosting topology and approve a durable private S3-compatible object store
   supported by the existing backend, or commission a reviewed alternative. A
   persistent local volume would require code changes: production local mode is
   currently rejected. Do not substitute ephemeral application disk.
2. Approve account/provider, region and data-residency policy, costs, private bucket,
   HTTPS endpoint, runtime IAM identity and scoped read/write permissions. Review
   public-access blocking, encryption, retention, object versioning, backups and
   off-target restore tests. Credentials remain in deployment secrets only.
3. Decide whether logical publication separation in one entirely private store is
   acceptable, or whether participant portraits/documents require separate physical
   buckets/prefixes and IAM. Existing random keys are not a physical isolation
   boundary. Public CDN/bucket access to the shared store is prohibited. Separate
   stores/prefixes would need a forward source and existing-object migration plan;
   no objects or records are moved in this correction pass.
4. After approval, set DIC_MEMORY_STORAGE=s3 and the approved bucket/endpoint/region
   in deployment configuration, validate upload/download authorization and restart
   durability, and verify removal of publication immediately revokes public view
   access. This is future approved configuration, not an action taken here.

Public approved imagery may be delivered through the existing published-only API
while the entire store remains private. Sensitive participant content must stay
behind authenticated, scoped, no-store responses; no direct Nginx media alias,
static export, shared public CDN, or blanket signed-URL endpoint is approved.

### Correction pass 1 verification

Files changed in this pass only: dawana-platform/src/pages/DIC.jsx (one handoff
sentence), backend/gunicorn.conf.py (loopback bind and forwarded-header allowlist),
deployment/nginx.production.example.conf (fixed-host redirect, media blocking and
explicit limits/timeouts), and this document. Production startup/build scripts and
Django storage/settings were inspected but not changed in this pass.

- `npm.cmd test`: 226 passed, 0 failed, 0 skipped; 22138.6142 ms.
- `npm.cmd run lint`: exit 0, no diagnostics.
- Session-only VITE_API_BASE_URL=/api/v1;
  `npm.cmd run build -- --outDir ../output/production-correction-build-13c27d93b8464a308b8831cba79f3897`:
  exit 0, 363 modules, 3.55 seconds. Main JS 666.28 kB (183.13 kB gzip);
  the existing >500 kB bundle warning remains. Existing output was not emptied.
- `git diff --check`: exit 0 with LF/CRLF notices.
- Python launch probe, database-free policy runner and in-memory compilation of
  gunicorn.conf.py all failed before execution with:
  `did not find executable at 'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.`
- Alternate `py -3.13` failed to launch the registered WindowsApps Python with
  `Access is denied.` No dependencies or interpreter permissions were changed.
- A stdin production-settings check harness disabled dotenv loading, supplied
  synthetic configuration and forbade database/network access before Django setup.
  It attempted to launch production deploy checks, MigrationLoader(None) graph
  validation and `makemigrations --check --dry-run`; Python launch failed before
  any of them executed. Those checks remain NOT VERIFIED, as do backend payment,
  authentication, fee/age and tutor regressions and Python compilation.
- Full database-backed tests were not started: no approved disposable target is
  available, and this pass forbids database creation and existing-database use.
- nginx and bash were not found through Get-Command. Nginx configuration syntax
  and shell-script execution are not verified here; neither script was executed.

No database, migration, credential, .env, fee/eligibility logic or authentication
logic was changed. No payments or donations were activated. Branch remains
staging/dawana-e2e at 986b863. Existing untracked review archives/directories and
all prior work remain untouched. Production readiness still requires the selected
host/proxy/TLS/storage configuration and actual backend acceptance results.

## Correction pass 2 — Render and isolated production R2 stores

This section supersedes the earlier pending hosting/storage selection discussion.
Render is the proposed host. The approved production bucket names are
`dawana-production-media` and `dawana-production-private`. Neither was created
or contacted. Both must remain private: disable public bucket access, custom public
domains and public CDN delivery. Do not reuse or change `dawana-staging-media`.

### Source architecture and isolation

The existing boto3 storage backend is extended rather than replaced. Editorial
images, memories, showcase imagery, thumbnails and promotional MP4 objects use
the media store. CampEnrollment portraits use PrivateParticipantStorage and the
private store. All downloads remain application-mediated; storage.url() refuses
direct URLs and no signed URLs are introduced. Publication rules still gate
editorial media; participant cards/portraits still require the existing authorized
portal grant and enrollment scope. Private responses must remain no-store.

Production requires two independently scoped backend identities. Restrict each
identity to its respective bucket; different key IDs are checked in source but
actual IAM scope cannot be proved by configuration validation. Production rejects
missing configuration, the staging bucket and non-HTTPS/nonstandard R2 endpoints.
It never falls back to staging, local files or the other production bucket.
The normal account-specific endpoint is supported; jurisdiction-specific endpoint
requirements need review before configuration. Legacy staging settings retain
their existing bucket and SDK credential chain; no staging service is maintained
or deployed by this work.

0036_private_participant_storage is a forward AlterField storage-state migration,
dependent on 0035. It has not been applied. It copies no objects and changes no
historical migrations. Fresh production starts empty. Existing production objects,
if any, would require a separately reviewed relocation plan; there is deliberately
no fallback lookup into the old bucket. Legacy staging portraits retain their old
keys and bucket when using config.settings.staging.

Replacement writes a fresh UUID key with conditional creation, verifies object
length through HEAD, then allows the model to persist its new reference. Old
objects are never automatically deleted, including on upload or database failure.
Database failure can leave a new orphan, retained for reviewed maintenance.
Direct storage.delete() is refused. The explicit delete_unreferenced_object helper
requires approval, exact production bucket/key validation, PostgreSQL table locks
and reference checks across every registered matching FileField. It is not wired
to requests, signals, startup or scheduled jobs. All writers/background jobs must
be quiesced during any future approved maintenance: SQL and R2 cannot form one
atomic transaction. Provider deletion is irreversible and no automatic cleanup
or retention period is authorized. Missing objects return generic 404 and provider
failures generic 503 before response streaming; errors after streaming begins
cannot be converted to a fresh HTTP status. Provider error details are not returned.

### Future Render configuration — do not execute during this pass

Backend service root: repository root. Build: `bash backend/production-build.sh`.
Start: `bash backend/production-start.sh`. Settings: `config.settings.production`.
WSGI: `config.wsgi:application`. Health check: `/api/v1/health/`.
The health endpoint checks database availability and returns no database identity
or credentials; it does not certify R2, email or payment readiness.
Build/start scripts do not run migrations. Gunicorn binds `0.0.0.0:$PORT` only
when DJANGO_DEPLOYMENT_TARGET=render, as required by Render ingress. Self-managed
mode keeps 127.0.0.1:10000 and the separate Nginx example. A Render-managed
ingress must be verified to terminate TLS, sanitize forwarded headers and prevent
direct public container-port access; no TLS certificate has been verified here.

Set in the backend deployment secret/configuration interface, never the frontend:

```
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_DEPLOYMENT_TARGET=render
DJANGO_TRUST_PROXY_HTTPS=True
DIC_MEMORY_STORAGE=s3
DIC_MEDIA_S3_BUCKET=dawana-production-media
DIC_MEDIA_S3_REGION=auto
DIC_PRIVATE_S3_BUCKET=dawana-production-private
DIC_PRIVATE_S3_REGION=auto
```

Additionally supply DIC_MEDIA_S3_ENDPOINT and DIC_PRIVATE_S3_ENDPOINT using the
approved account HTTPS endpoint; separately supply each prefix's S3_ACCESS_KEY_ID
and S3_SECRET_ACCESS_KEY through backend secrets only. Existing AWS_* credentials
are not a production fallback. No real endpoint or secret is recorded here.

Supply a fresh approved production DATABASE_URL, Django secret, exact
DJANGO_ALLOWED_HOSTS, exact HTTPS DJANGO_CSRF_TRUSTED_ORIGINS and
DJANGO_CORS_ALLOWED_ORIGINS, and approved email settings. DB_SSLMODE defaults to verify-full;
retain certificate/hostname verification and DB_SSLROOTCERT where supported.
Correction pass 3 removes the Render internal TLS downgrade entirely. Both
staging and production require DB_SSLMODE=verify-full. RENDER_INTERNAL_DB_HOST
no longer grants an exception. Prefer Render's authenticated external PostgreSQL
endpoint with the appropriate trusted CA configuration (DB_SSLROOTCERT where
needed). Actual certificate/hostname validation, connectivity from the service,
and restrictive network access remain unverified: deployment is blocked until
those checks pass. An internal endpoint that cannot authenticate is unsupported.
No database connection was attempted.

Use same-site HTTPS custom frontend/API domains for the existing cookie policy.
Do not silently weaken SameSite cookies for separate onrender.com sites; domain,
cookie, CORS, CSRF and real-browser acceptance testing remain launch gates.
Gunicorn's forwarded IP allowlist remains loopback; Django's opt-in proxy setting
trusts only X-Forwarded-Proto=https behind a verified sanitizing ingress. It does
not authorize arbitrary client-IP headers or wildcard proxy trust.

Frontend static site root: `dawana-platform`; build: `npm ci && npm run build`;
publish: `dist`; SPA rewrite: `/*` to `/index.html`.
Set VITE_API_BASE_URL to the approved HTTPS backend origin plus `/api/v1` before
building. It is public configuration, never a place for R2 credentials.
The shared media resolver preserves API paths/query parameters, resolves against
that API origin, and rejects foreign object-store URLs. Participant card downloads
use it too; external video embeds keep their separate provider validation.

### MP4 runtime, retention and remaining approvals

ffprobe is not assumed to exist. The optional build step requires
DIC_INSTALL_FFPROBE=1, DIC_FFPROBE_DOWNLOAD_URL and DIC_FFPROBE_SHA256. Approve a
pinned raw Linux executable matching the Render architecture, its source/license
and SHA-256 before using this route; an archive URL is not accepted. The installer
downloads over HTTPS, verifies the hash, installs into backend/.runtime (ignored
by Git) and checks the executable. Startup selects that artifact unless an explicit
DIC_FFPROBE_BINARY is configured. No URL/hash/version was invented and no binary
was installed locally. MP4 upload stays blocked until runtime validation succeeds.

Remaining decisions: actual Render plan/region/costs, domains and TLS verification,
R2 account/jurisdiction and scoped identities, upload/download limits at ingress,
approved ffprobe artifact, privacy/retention/deletion policy, audit logging and
backup ownership. Approve encrypted independent object backups with a reference
manifest and matching PostgreSQL backups, RPO/RTO, access/rotation policy and
documented isolated restore exercises. Do not assume R2 provides S3 versioning or
point-in-time restore. No lifecycle expiration or bulk-delete task is enabled.
Production migrations, shared cache table creation, official seed initialization,
secure administrator creation and live payment/public registration release each
remain separately approved future operations. Donations remain deferred.

### Correction pass 2 verification

- Final frontend tests: 228 passed, 0 failed, 0 skipped (18792.0536 ms).
- `npm.cmd run lint`: exit 0, no warnings after correcting the two new warnings.
- Vite production build with configFile=false, build.write=false and a synthetic
  separate HTTPS API origin: exit 0; no deployment bundle written to disk.
- `git diff --check`: exit 0. Branch remains staging/dawana-e2e at 986b863.
- Python database-free mocked storage/authorization/lifecycle/Render tests were
  added to scripts/test_production_policies.py. Attempting the runner failed before
  execution: `did not find executable at
  'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.`
- Backend tests, Django checks, migration graph/autodetection and Python compilation
  remain NOT VERIFIED due to that interpreter blocker. No database-backed tests
  or migrations were attempted. Mocked tests do not prove deployed IAM/proxy policy.
- No Cloudflare operation, database connection, credential/.env change, service
  change, provisioning, deployment, commit or branch change was performed.

Exact files changed in correction pass 2 (all other existing work preserved):

```
.gitignore
PRODUCTION_INITIALIZATION_PLAN.md
backend/config/deployment_security.py
backend/config/settings/base.py
backend/config/settings/production.py
backend/dic/storage_configuration.py
backend/dic/memory_storage.py
backend/dic/promo_storage.py
backend/dic/models.py
backend/dic/migrations/0036_private_participant_storage.py
backend/dic/object_lifecycle.py
backend/dic/media_delivery.py
backend/dic/memory_views.py
backend/dic/showcase_views.py
backend/dic/promo_views.py
backend/dic/video_views.py
backend/dic/test_storage_production.py
backend/dic/test_render_configuration.py
backend/dic/test_promotions.py
backend/gunicorn.conf.py
backend/install-ffprobe.sh
backend/production-build.sh
backend/production-start.sh
scripts/test_production_policies.py
dawana-platform/src/services/mediaUrl.js
dawana-platform/src/services/mediaUrl.test.js
dawana-platform/src/services/participantIdentity.js
dawana-platform/src/components/dic/CampShowcase.jsx
dawana-platform/src/components/dic/DICEditorial.jsx
dawana-platform/src/components/dic/MemoriesGallery.jsx
dawana-platform/src/components/dic/VideoGallery.jsx
```

Runtime R2 identities should have only the necessary bucket-scoped read/write
permissions; do not grant routine deletion merely to exercise the maintenance
helper. Any future deletion identity and retention execution require separate
approval. Authentication, eligibility, fees, payment snapshots, tutor exemption,
donation release policy and existing migrations were not changed in this pass.
