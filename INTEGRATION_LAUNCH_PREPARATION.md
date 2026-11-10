# DA’WANA consolidated integration and payment-launch handoff

Source preparation only. No shell, Git, Python, npm, tests, builds, network requests,
database operations, migrations, DNS changes, deployment or live transactions were run.
All command blocks below are instructions for the owner, not execution records.

## Evidence and preservation

Owner-reported incoming baseline: 246 database-free backend policy tests passed;
295 frontend tests passed; frontend lint had zero warnings/errors; the latest
production build stopped because VITE_API_BASE_URL was missing. These results
precede this sprint. No new passing result is claimed. Database integration,
browser acceptance and deployed artifact identity remain pending.

Historical recovery reports were reused. Existing Paystack production-mode,
Operations serializer and guarded Render migration repairs were retained. No
migration, financial policy, authentication cookie policy, permission or recovered
feature was replaced. Exact files read/searched and changed are recorded in
output/integration-launch-preparation/FILE_REVIEW.json. Read/search inventory does
not mean every file received a complete security audit. Existing files receive
narrow edits; historical reports and untracked work are not reset or removed.

## Confirmed corrections

1. Payment-return preparation/resolution wrongly required equal browser origins.
   It now retains same-origin operation and narrowly permits the intended HTTPS
   DA’WANA apex/www frontend to api.dawanaislamicfoundation.org, only when that
   API is explicitly configured. Arbitrary pages.dev/onrender.com cross-site
   combinations remain blocked. No DNS or endpoint readiness is inferred.
   Bearer authorization for grant creation, credentialed fetch, CSRF, Lax cookies,
   server-side grants and provider verification remain unchanged.
2. Staff ID presentation reused participant-only card URLs. Separate staff paths
   now use the existing /dic/ids/cards/<id>/ endpoint; participant paths remain
   under /dic/participant/enrollments/<id>/card/. Backend authorization is still
   mandatory. The shared authorized card response now includes its enrollment ID,
   which staff presentation previously lacked. No ID is issued during rendering.
3. Timetable Admin navigation used a backend-relative URL on the frontend host.
   It now resolves through the existing configured backend-origin helper.
4. Donation options/results and UI always said test mode, even though the existing
   approved-live configuration path can collect live donations. Mode labels now
   reflect configured/stored mode. Collection flags and credentials are unchanged;
   donations remain independently gated and must stay off until separately accepted.
5. Payment-return UI could call a cancelled paid order confirmed. Confirmation now
   requires both server payment_status=paid and status=confirmed. Authorization
   failures no longer direct production users to a staging-only login.
6. The registration client accepted successful JSON null/arrays/primitives, causing
   later crashes or ambiguous flow state. It now rejects those responses clearly,
   retains uncertainty, and never retries a charge automatically.
7. Local-only API examples were misleading for Pages. A separate explicit production
   example was added, and Render schema documentation now uses the existing guarded
   manifest process rather than suggesting raw migration application.

Focused regressions cover allowed/denied return origins, confirmed/cancelled
payment display, malformed successful responses without automatic retries, staff
versus participant card URLs and rendered links, authorized card identity and
configured/stored donation mode. All are prepared and unexecuted.

## Contract review across the application

| Area | Inspected integration | Remaining acceptance |
|---|---|---|
| Public/editorial/media/contact | API prefix, publication/media resolver, foundation options/contact and CSRF | Published content, R2 objects, mobile pages, actual enquiry submission |
| Registration/pricing/tutors/assisted | Existing order/pricing/recovery/tutor routes and server-authoritative gates | Real PostgreSQL fixtures, quote expiry, guardian/account rules and retry acceptance |
| Accounts/OTP/password | Participant endpoints, verification fragments, credentialed fetch, expiry/logout and staff CSRF rotation | Real delivery, wrong/expired codes, password reset/revocation, browser cookies |
| Payment/return | Existing bearer initialization, grant preparation, cookie-bound return, signed webhook and verification | Provider sandbox in isolated nonproduction setup; production mode-denial and live acceptance gates |
| Camper World/Earn Points | Existing Home/My Day/Arena/Explore/Me clients, scoped scoring/catalogue/timetable/updates dependencies | Real publication, selection changes, missing data and expired access |
| Housing/check-in/classes/timetables | Existing staff/participant paths and permission boundaries | PostgreSQL locks, allocation eligibility/capacity, transfer and publication concurrency |
| IDs/QR/scanning | Separate staff/participant authority, ID formats, media/API routing and scanner services | Physical QR/print, private media, staff-only and foreign-booking denial |
| Feedback/welfare | v2/v3 payloads, staff/participant endpoints and scoped confidentiality | Duplicate submissions, privacy thresholds and unauthorized report access |
| Operations/finance/reports | Shared credentialed transport, editor routes, permission separation and exports | Full database/browser workflows and finance-role acceptance |

No additional endpoint mismatch was established in the inspected unchanged paths.
Source inspection and passing policy tests never substitute for database/browser acceptance.

## Cloudflare Pages: intended configuration

Only after owner-approved domain/DNS/TLS configuration:

- Frontend custom domain/canonical origin: https://dawanaislamicfoundation.org
- Root directory: dawana-platform
- Node: 22, matching .nvmrc; use a Vite-compatible installed release.
- Build command: npm run build (clean dependency installation: npm ci).
- Build output: dist (relative to the selected frontend root).
- Production environment: VITE_API_BASE_URL=https://api.dawanaislamicfoundation.org/api/v1
- Same value must be supplied independently to any approved preview build that uses it.
  A pages.dev preview is not an authenticated production acceptance origin.
- No trailing slash, query, fragment, credentials or non-443 port in the HTTPS API base.
- /api/v1 remains supported for a real same-origin proxy/local setup. Pages currently
  has an SPA fallback, not an API proxy; do not use that relative base on plain Pages.
- .env.production.example is inactive: Vite does not load .example files automatically.
  Never put private values in VITE_*; these variables are public compiled code.
- Existing public/_redirects serves deep links through index.html. Test direct loads of
  /dic/participant, /dic/register/payment-return and /dic/operations/classes.

The existing Render origin can be used for an explicit build/connectivity check:
https://dawana-islamic-foundation-web-app-1.onrender.com/api/v1
It remains cross-site from the intended frontend and is not a valid substitute for
cookie-authenticated production acceptance. No request to either origin was made.

## Render: intended configuration

Use backend/render.env.example as an inactive checklist, not a ready-to-launch env.
It deliberately disables collection, delivery, account rollout, workers and uploads.

| Variable | Intended value / requirement |
|---|---|
| DJANGO_SETTINGS_MODULE | config.settings.render |
| PUBLIC_HOST | api.dawanaislamicfoundation.org, after custom-domain acceptance |
| FRONTEND_ORIGIN | https://dawanaislamicfoundation.org, no trailing slash |
| DAWANA_WEBSITE_ONLY | false |
| DJANGO_SECRET_KEY | Independent secret, at least 50 characters; Render secret only |
| DATABASE_URL | Approved PostgreSQL target with full hostname; secret only |
| DB_SSLMODE | verify-full |
| DB_SSLROOTCERT | Existing readable trusted CA bundle if OS default is unsuitable |
| DIC_PORTAL_FRONTEND_URL | https://dawanaislamicfoundation.org/dic/participant |
| DIC_PORTAL_EMAIL_VERIFY_URL | https://dawanaislamicfoundation.org/dic/participant |
| PAYSTACK_CALLBACK_URL | https://dawanaislamicfoundation.org/dic/register/payment-return |
| PAYSTACK_MODE / PAYSTACK_LIVE_ENABLED | test / false until separate live approval |
| PAYSTACK_SECRET_KEY | Absent during disabled preparation; never a frontend variable |

native_defaults derives exact allowed-host, CORS and CSRF lists from PUBLIC_HOST and
FRONTEND_ORIGIN. Keep SESSION_COOKIE_DOMAIN and CSRF_COOKIE_DOMAIN unset/host-only;
secure cookies and SameSite=Lax remain. The backend does not automatically trust
both apex and www: approve one canonical frontend and redirect the other to it.
If www is selected, align FRONTEND_ORIGIN, links and callback configuration consistently.

Repository-root Render build setting:
  bash backend/native-install.sh && bash backend/native-build.sh
Repository-root web start:
  bash backend/native-start.sh web
If Render root is backend, omit the backend/ prefix. Explicit Render settings and
RENDER=true must be verified. Do not use retired-provider manifests or the older
staging-only render-build.sh/render-start.sh for this production service.

Runtime gates: supported Python 3.12/3.13, pinned dependencies, Liberation fonts,
ffprobe, Gunicorn, WhiteNoise and PDF/media dependencies. The current scripts do
not provision missing OS packages automatically; resolve runtime failures explicitly.
Web health: /api/v1/health/web/. Database connectivity: /api/v1/health/.
A healthy web probe proves neither schema/cache readiness nor worker health.

Full application launch additionally requires explicitly approved values:
DIC_PORTAL_ACCOUNTS_ENABLED=true; DIC_BACKGROUND_WORKER_ENABLED=true;
DIC_EMAIL_RECOVERY_ENABLED=true; DIC_RECOVERY_DELIVERY_WORKER_ENABLED=true;
EMAIL_BACKEND=config.https_email.EmailBackend (or an accepted existing real backend),
verified DEFAULT_FROM_EMAIL, RESEND_API_KEY when using that backend, existing valid
DIC_RECOVERY_ENCRYPTION_KEY and reviewed DIC_AUTOMATION_ACTOR_ID. Do not rotate an
existing encryption key casually. Worker uses the same database/config and
bash backend/native-start.sh worker on a separately approved worker resource.
Verify shared-cache heartbeat and actual durable queue progress.

DIC_AUTO_FULFILLMENT_ENABLED and DIC_AUTO_FULFILLMENT_ACTOR_ID are separate ID
rollout gates. Keep default-off until accepted; preserve the existing authorized
staff issuance path meanwhile. Assisted registration is separately gated.

For R2 use DIC_MEMORY_STORAGE=s3 and separate DIC_MEDIA_S3_* / DIC_PRIVATE_S3_*
credentials. Buckets: dawana-production-media and dawana-production-private;
region auto; validated account R2 endpoint. Keep private objects private and verify
portrait inventory/copy before DIC_PORTRAIT_CUTOVER_VERIFIED=true. Accept actual
uploads, published delivery, private downloads, missing objects and access denial.
FOUNDATION_DONATIONS_ENABLED must remain false until its separate acceptance.

## One local owner-run verification batch

Use the existing dependencies/interpreter. Run from the repository root, stopping
at the first failure; do not interpret later output as acceptance after a failed step.
The API variable below configures the build only; it does not verify connectivity.

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
python -I -B scripts/test_production_policies.py
git diff --check
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP\dawana-platform"
npm test
npm run lint
$env:VITE_API_BASE_URL = 'https://api.dawanaislamicfoundation.org/api/v1'
npm run build
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
git status --short --untracked-files=all
```

No dependency reinstall is needed if the current accepted environment is intact.
If dependencies are missing, resolve that explicitly rather than skipping checks.
The API assignment affects only the current PowerShell process and child builds.
Review all changed/untracked files, including this handoff and the examples. No
commit/push is performed by this batch.

## Isolated database and migration gates

After approval of a complete remote candidate, owner dispatches the existing
Backend production acceptance workflow. The PG14/PG18 matrix runs all core, tutor,
movement and assistance partitions. Source guards use unique disposable database
names, exact loopback service identity, no dotenv loading, cleared DATABASE_URL/
libpq overrides, blocked external sockets and strict result accounting.
Within that provisioned workflow only, the core command is:
  python -I -B scripts/run_backend_ci.py --partition core
Do not run it locally or fake GitHub Actions markers. No generic local manage.py
test command is recommended against normal settings.

Accept fresh migrations and a representative approved restore rehearsal. 0033
already owns class/announcement schema; 0039 creates the ID outbox after 0038.
Do not generate migrations for these source corrections. Production applied state
is unknown. Verify backups and restore ownership. Use the corrected guarded release
manifest command in backend/RENDER_COMPATIBILITY.md with all five independently
verified target identifiers. Pending plans intentionally fail inspection without
applying. Approval must match hashes/settings/target and include backup, restore
and rollback evidence. Shared cache-table approval remains separate. Stop if the
managed database cannot provide the required cluster identity.

## Owner-controlled deployment and payment opening sequence

1. Accept local verification and exact candidate review; then accept all isolated
   PostgreSQL jobs. Commit/push and workflow execution are separate owner actions.
2. Approve canonical apex/API domains. Manually configure Cloudflare DNS/Pages,
   Render custom domain and valid certificates. Keep current backend-origin
   connectivity diagnosis distinct from same-site cookie acceptance.
3. Rehearse the release on approved isolated infrastructure with synthetic data,
   verified storage/delivery and nonproduction Paystack configuration. Production
   Render must deny test evidence; do not bypass that gate to test production.
4. Back up and accept restore evidence; inspect and separately approve the exact
   production migration/cache plan. Deploy the reviewed backend and frontend only
   after release approval. Retain previous compatible artifacts/configuration.
5. Verify canonical HTTPS, both health probes, API JSON (not SPA HTML), exact CORS
   and CSRF origins, staff login/token rotation/logout and participant login,
   verification/reset/OTP/expiry. Confirm foreign origins and missing CSRF fail.
6. Verify registration edition/category/quote data and payment handoff. Exercise
   grouped registration, explicit guardians, account email delivery, duplicate
   submissions and recovery. Confirm unchanged idempotency keys on uncertain retries.
7. Accept the refund/reversal decision below and name finance/support operators.
8. Only after explicit live-payment approval configure matching sk_live_ credentials,
   PAYSTACK_MODE=live, PAYSTACK_LIVE_ENABLED=true and accepted registration availability.
   Callback: https://dawanaislamicfoundation.org/dic/register/payment-return
   Registration webhook: https://api.dawanaislamicfoundation.org/api/v1/dic/payments/paystack/webhook/
   Confirm dashboard environment, signature configuration and reachable HTTPS route.
   Foundation donations use a separate endpoint and remain disabled.
9. Owner runs check_dic_launch with Render settings on the verified target after
   registration is configured open. With approved live configuration, --require-live
   checks configuration only; it does not call Paystack. This command reads the
   database and therefore requires the approved production inspection context.
10. Separately authorize a controlled live acceptance transaction. Verify authoritative
    amount/currency/reference/domain/paid_at/price revision and exact order binding;
    callback alone grants nothing. Confirm entitlement, queued housing, authorized
    ID issuance and portal access. Verify duplicate notification creates no second
    allocation/ID/charge. Do not open general traffic before acceptance.
11. Browser smoke the complete public -> registration -> verification -> payment ->
    housing -> portal -> five Camper World sections -> Earn Points -> IDs/QR ->
    feedback/welfare -> staff Classes/Announcements/finance/scoring/reports journey.
    Include unavailable services, false/forged callbacks, pending/failed attempts,
    wrong amount/currency/reference/mode, stale edits and unauthorized booking access.
12. Open registration payments under active monitoring. Watch verification exceptions,
    duplicate charges, queue age/retries/holds, email delivery, API errors and private
    media failures. Reconcile provider evidence without marking unverified attempts
    successful. On incident, stop new collection through approved availability gates,
    preserve verification/webhook/recovery access where safe, and follow the reviewed
    rollback/restore decision. Never delete financial history or blindly reverse schema.

## Decisions and remaining blockers

- Domain setup and same-site browser acceptance are unverified. No insecure cookie
  workaround, wildcard CORS or CSRF exemption is approved or implemented.
- Refund/reversal/dispute policy remains unapproved. Finance adjustment evidence does
  not suspend entitlement; non-charge.success webhook events do not implement a
  reversal lifecycle. Approve full/partial refund and dispute treatment, independent
  verification, idempotent audit records, session/ID/queue consequences, welfare-led
  occupied-housing review, notification and reviewed reinstatement. Existing ID
  restrictions/revocation and housing release are separate controls, not a complete
  integrated reversal workflow. An enforceable, accepted procedure is a live-launch gate.
- Database acceptance, production schema/cache state, actual runtime packages, worker
  availability, verified email delivery, R2/portrait acceptance and restore evidence
  are still outstanding. Source preparation cannot establish them.
- No live key, live flag, real transaction, DNS record or deployment was changed.
  The shortest safe path is to accept this candidate, complete the external gates,
  and conduct separately approved controlled live acceptance; no redesign is required.
