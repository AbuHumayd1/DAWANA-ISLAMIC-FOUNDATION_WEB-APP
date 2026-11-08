# DAWANA: simple ZevCloud full-application deployment

Three application services reuse the existing purchased PostgreSQL 18:
React static frontend, native Django API/Admin, persistent native worker.
No application Dockerfile, custom Nginx, Supervisor, gateway, Redis or Celery.
ZevCloud manages its serving infrastructure. No production changes were made.

## Frontend

Create a Git-backed **Web Application**, framework **React / Vite**, builder
**Native / Nixpacks**, using the reviewed branch:

| Setting | Exact value |
| --- | --- |
| Root/base directory | `dawana-platform` |
| Node | `22` (included .nvmrc/nixpacks.toml) |
| Install | `npm ci --include=dev` |
| Build | `npm run build` |
| Static site | On |
| SPA | On |
| Output / Publish Directory | `dist` (repository path dawana-platform/dist) |
| Start command / Port | None: managed static serving |
| Only required build variable | `VITE_API_BASE_URL=https://<backend-host>/api/v1` |

The API URL is public and baked into the bundle; rebuild when it changes. Never
put secrets in VITE_* variables. SPA mode preserves deep links, including
`/dic/participant` and `/dic/register/payment-return`. Vite emits hashed assets
and root-relative URLs. Use standard provider static caching; confirm new
index.html/assets after releases. No API rewrites or custom server config.

## Backend

Create a Git-backed **Web Application**, framework **Django / Python**, builder
**Native / Nixpacks**, static-site mode **Off**:

| Setting | Exact value |
| --- | --- |
| Root/base directory | `.` |
| Python | `3.12` (native selector, manifest and deployment/backend CI) |
| Install | Leave unset; use manifest command below |
| Build | `bash backend/native-build.sh` |
| Start | `bash backend/native-start.sh web` |
| Port | `8080` |
| Web service health path | `/api/v1/health/web/` (Django + database) |

Manifest install command:

```
python -m venv --copies /opt/venv && . /opt/venv/bin/activate && bash backend/native-install.sh
```

Keep /opt/venv/bin on the manifest PATH. Installation uses root requirements.txt
and existing constraints. Backend builds collect Django static files only; no
Node or React build. The manifest provides ffprobe and Liberation fonts used by
existing media validation/PDFs. Gunicorn runs config.wsgi:application from backend,
binding 0.0.0.0 to supplied PORT (8080 default). Dashboard commands need no shell
variable expansion. Build/start never migrate, seed, create users or enable live
payments.

Select **Python 3.12** in ZevCloud. The manifest and native/backend CI match it;
existing dependency requirements/constraints remain unchanged. Native CI checks
resolved package Requires-Python metadata, production/binary imports, Django
startup and worker-command imports on 3.12. Actual local Python 3.12 execution
is unavailable; those CI results are still required. Python 3.13 remains accepted
only to preserve the archived rollback path, not as a native selector requirement.

### Minimum Backend startup environment

Only these four values are needed to start the web service. PUBLIC_HOST is the
**Backend** host. Frontend has only the Vite build variable above.

| Variable | Value |
| --- | --- |
| PUBLIC_HOST | Exact backend hostname, no scheme/path |
| FRONTEND_ORIGIN | Exact frontend HTTPS origin, no trailing slash/path |
| DJANGO_SECRET_KEY | Existing independent random secret, at least 50 characters |
| DATABASE_URL | Existing PostgreSQL connection from its Overview; private |

Instead of DATABASE_URL use **DB_HOST, DB_NAME, DB_USER, DB_PASSWORD**, plus
DB_PORT when different from 5432. Choose one format; DATABASE_URL takes precedence.
Use existing internal credentials, never a new database. PostgreSQL identity is
verified using standard libpq **verify-full**. Add **DB_SSLROOTCERT** as the
readable mounted trusted CA file when that endpoint's issuer is not already
trusted by libpq. Use its certificate-matching hostname, never a guessed alias/IP.
There is no SQLite fallback or automatic migration.

### Email, recovery and worker requirements

These are validated when an operation needs them, not when Gunicorn imports
Django. Keep web feature configuration and worker configuration consistent:

| Variable | Web operations | Worker |
| --- | --- | --- |
| DIC_AUTOMATION_ACTOR_ID | Not needed by the web process | Required existing authorized active staff user |
| DIC_RECOVERY_ENCRYPTION_KEY | Required for recovery/portal OTP issuance | Required to decrypt queued OTPs; preserve the existing key |
| DEFAULT_FROM_EMAIL | Required for registration verification and email recovery | Required verified sender |
| RESEND_API_KEY | Required for those email operations with the default HTTPS backend | Required with the default HTTPS backend |

The worker also needs the four shared web configuration values above, using the
Backend PUBLIC_HOST. Its startup cycle validates encryption, delivery settings,
portal URL and all actor permissions before claiming/processing jobs. No key or
user is generated. A different accepted real HTTPS email backend can replace
Resend; supply its genuine credentials rather than dummy values.

Missing credentials do not change feature flags. New registrations needing an
email-verification link and verification resends return a generic 503 if delivery
configuration is absent. Existing verified account login, Admin and unrelated
APIs do not need worker identity or OTP encryption. Recovery/portal OTP requests
report unavailable delivery and return 503 without issuing plaintext codes.
Provider outages after valid configuration keep existing durable pending/retry
states and never activate an unverified account or reverse verified payments.
Console/locmem/dummy backends cannot report production verification delivery as
successful. Never substitute a new key for existing encrypted records.

`/api/v1/health/web/` checks web/database availability, not full launch readiness.
The unchanged full-application endpoint `/api/v1/health/` additionally requires a
recent worker heartbeat and configured email/recovery on the web service. It stays
503 while those requirements are unmet. Use web health for the Backend service
probe; use full readiness plus check_dic_launch before opening registration/live
payments. A bootable web service is not a claim that the full launch is ready.

Derived defaults: exact allowed backend host, credentialed CORS/CSRF for the
frontend only, frontend portal/email/callback URLs, full accounts/recovery/workers,
HTTPS redirects and Secure/HttpOnly host-only Lax session cookies. No proxy
acknowledgement flag. Forwarded client IPs are ignored; socket-peer throttles
remain conservative/shared. No arbitrary client identity/host headers are trusted.

### What differs from local development

| Check | Local development | Native production |
| --- | --- | --- |
| Debug / secret | DEBUG on; secret must exist | DEBUG off; independent secret at least 50 characters; insecure defaults rejected |
| Host / browser origin | Local/env hosts and origins | Exact PUBLIC_HOST and HTTPS FRONTEND_ORIGIN; no wildcard credentialed CORS |
| HTTPS / cookies / headers | Development HTTP allowed | HTTPS redirect, exact scheme handling, secure host-only cookies, HSTS, nosniff and frame denial |
| Database | PostgreSQL from local settings | PostgreSQL only, certificate-matching verify-full TLS; web health tests connectivity |
| Rate limiting / logs | Local defaults | Shared database cache; privacy-filtered request logs; unverified forwarding identities discarded |
| Uploaded files | Local storage allowed | Local uploads rejected; disabled or approved object storage with independent credentials |
| Payments | Isolated test configuration | Mode/key matching, explicit live enablement/HTTPS callback; test receipts cannot grant production entitlement |
| Application mode | Features use explicit local flags | Full-mode defaults retained; conflicting website-only/account/worker-disable settings rejected |
| Actor / recovery / email | Defaults can be absent | Also optional for web boot; actual operations and worker validate their own requirements |
| Runtime tools | Local runserver environment | Native build/start retain Python 3.12/3.13, pinned Django, package/font and ffprobe checks |

Base timeout bounds and password validation are retained. No production security
check was removed to compensate for missing operational credentials. The former
extra native import-time actor/Fernet/email checks were moved to their consumers.

Remove obsolete GATEWAY_*, TRUSTED_EDGE_CIDRS, EDGE_TRUST_VERIFIED,
ZEV_PROXY_HEADERS_VERIFIED, DAWANA_TRUSTED_GATEWAYS, DJANGO_TRUST_PROXY_HTTPS,
DJANGO_BIND_*, DJANGO_DEPLOYMENT_TARGET, DAWANA_WEBSITE_ONLY and old
DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS / DJANGO_CORS_ALLOWED_ORIGINS.
Remove old callback/portal URLs and account/worker-disable overrides so defaults
apply. Keep genuine secrets, approved business settings and existing object
storage credentials. Do not copy the old container environment wholesale.

An accepted HTTPS Django email backend can replace the default via EMAIL_BACKEND
and its credentials. Console/locmem/dummy production delivery is rejected when invoked. ZevCloud blocks SMTP;
real HTTPS sender verification/delivery are required. Existing private/public
object-storage and portrait-cutover gates remain for uploads/portraits. Ephemeral
local production uploads stay disabled. Google/SMS/WhatsApp/feedback settings
remain optional feature-specific configuration.

### Authentication across separate origins

Production arrangement: frontend `https://dawanaislamicfoundation.org`, backend
`https://api.dawanaislamicfoundation.org`. The API subdomain is proposed, not
created. Both need managed HTTPS.

These origins share one browser site. Existing Django sessions and participant
cookies stay host-only on the API; no shared Domain cookie or new authentication
system. Existing fetch calls include credentials and obtain masked CSRF tokens
from API JSON endpoints before protected writes. Foreign origins are neither
CORS-approved nor CSRF-trusted. Admin is `https://<backend-host>/admin/`; the
frontend Admin link now points there. Print/download navigation targets the API.

Unrelated domains are **not supported for cookie login** with these Lax cookies.
Provider preview hostnames do not prove SameSite compatibility. Preview public
routing/build first; full browser login acceptance requires approved same-site
HTTPS hostnames. Do not disable CSRF or relax cookies to bypass browser blocking.

## Worker

### Actor provenance and supported provisioning

`DIC_AUTOMATION_ACTOR_ID` was introduced by commit `21a7950` on 8 November 2026
at 11:40:50 Africa/Lagos as the identity passed by the persistent worker to
existing permission-checked housing commands. The web import-time requirement
was added in `1a56410` at 14:17:14 that day. The original local housing command
already required an explicit `--actor`; it did not run anonymous allocations.
Housing claims, allocations and guardian approvals record this identity in
existing audit records. Recovery and account-delivery services do not read this
variable directly. Verified payment settlement queues durable work without it.

The web check is removed from the corrected settings. A deployment still raising
the exact old settings exception is running code without that correction. Verify
the deployed commit includes the corrected settings; do not invent an actor ID
to bypass web startup.

Worker configuration still needs the existing authorized active staff user's
actual PK and these permissions: dic.can_process_housing_queue,
dic.can_allocate_participants, dic.can_approve_housing_guardians. There is no
dedicated automation-user provisioning command. setup_dic_staff_roles manages
staff groups, not this user. Under separate database-write authorization, an
authorized administrator can provision/review the user through existing Django
user administration or shell APIs, set an unusable password and grant only the
three permissions. Use no superuser privileges or automatic identity selection.
Existing eligible users can be reused only after explicit review/authorization.
No new migration or schema change is needed for this startup fix. Creating a
missing user or assigning permissions is a separate database operation.

### Render native reuse

The existing native Python path can also be selected on Render; the historical
settings module name config.settings.zevcloud does not create a hosting dependency.
Use repository root `.`, Python 3.12 (root .python-version), build command
`bash backend/native-install.sh && bash backend/native-build.sh`, start command
`bash backend/native-start.sh web`, and health path `/api/v1/health/web/`.
Render supplies PORT, which the existing Gunicorn configuration honors.
No deployment-specific actor variable is required on the Web Service.

Use the existing worker command `bash backend/native-start.sh worker` for a
Render Background Worker, with its actual authorized actor and delivery settings.
Keep the same PUBLIC_HOST/FRONTEND_ORIGIN, secret and database configuration;
use a PostgreSQL endpoint reachable from the service with verify-full TLS.
Render does not run nixpacks.toml: the build/start runtime gate still requires
Liberation fonts and ffprobe. Their availability on the actual Render runtime
is not established by this actor fix; no runtime/security check was bypassed.
No Render service or database was created or accessed here.

Provider references: [Render Python version selection](https://render.com/docs/python-version),
[native Django deployment](https://render.com/docs/deploy-django),
[persistent background workers](https://render.com/docs/background-workers).

Use one additional ordinary **Web Application**, Python / Native Nixpacks, same
root/install/build and port 8080. Supply the shared Backend configuration plus
the four worker requirements listed above. Start:

```
bash backend/native-start.sh worker
```

Health: `https://<worker-host>/health/`, a read-only generic response. Existing
bounded housing, recovery, portal OTP and verification commands run every 15
seconds. Their durable claims, leases, retries and idempotency remain intact.
Heartbeat uses the existing shared database cache, not a shared filesystem.
Worker health and full-application readiness return 503 for missing/stale heartbeat
(300 seconds). Invalid actor/configuration stops the worker visibly; transient
cycle failures retry without refreshing readiness. No queue work runs in HTTP.

A separate running service/plan is required; review its price before purchasing.
ZevCloud scheduled tasks run at most every five minutes, so they are not the
selected runtime for prompt OTP delivery and bounded queue draining. No extra
scheduler product is required.

## Database preparation and launch order

1. Obtain passing native deployment CI and existing disposable PostgreSQL 14/18
   acceptance for the reviewed commit. Never test against production.
2. Verify the hosting acceptance dependency below. Do not purchase or deploy
   services without separate authorization.
3. Review existing backup/restore and use the existing release_migrations plan:

   ```
   python backend/manage.py release_migrations --settings=config.settings.zevcloud --database-name <name> --hostname <host> --port <port> --role <migration-role> --cluster-id <verified-cluster-id> --manifest-file <new-plan.json>
   ```

   Pending migrations write a plan then deliberately return an error. Apply only
   after separate approval using existing --apply-approved-plan / --approval-file
   controls and identical target/cluster identity. Never add this to startup.
4. Separately approve existing cache-table/schema/actor/edition preparation.
   Confirm `dawana_release_cache`, active edition/prices/dates, approved housing
   inventory/fingerprint, and actor permissions `dic.can_process_housing_queue`,
   `dic.can_allocate_participants`, `dic.can_approve_housing_guardians`. Use no
   worker superuser or usable password. Ambiguous guardians/capacity holds remain
   exceptional review; verified payments survive delays. Tutors stay offline.
5. After release authorization, Backend can boot with the four web variables and
   health `https://<backend-host>/api/v1/health/web/`. Configure email/recovery on
   Backend and Worker, start Worker, then verify full readiness at
   `https://<backend-host>/api/v1/health/` before opening the static Frontend's
   transactional flows. Worker health is above. On Worker (where the actor ID is
   configured), check connectivity/TLS/schema/cache/edition/delivery read-only:

   ```
   python backend/manage.py check_dic_launch --settings=config.settings.zevcloud
   ```

6. In an isolated acceptance environment verify deep-link refresh, registration
   options, CSRF/preflight, staff login/me/logout, Admin, email verification and
   recovery, participant scope, housing/delivery pending status and duplicate
   payment notifications. Browser calls must target the API, include API cookies
   and receive exact frontend Access-Control-Allow-Origin, never `*`.
7. After preview acceptance and separate DNS authorization, add official frontend
   and API domains in ZevCloud Domains. Apply only dashboard-provided DNS records,
   verify HTTPS, update PUBLIC_HOST/FRONTEND_ORIGIN/VITE_API_BASE_URL, rebuild and
   repeat full browser authentication acceptance on those same-site domains.
8. Confirm payments remain disabled: PAYSTACK_MODE=test,
   PAYSTACK_LIVE_ENABLED=false, PAYSTACK_SECRET_KEY absent. Test-mode production
   receipts never grant paid entitlements. Later, separate approval requires the
   matching live key, PAYSTACK_MODE=live, PAYSTACK_LIVE_ENABLED=true,
   `check_dic_launch --require-live` and an approved acceptance transaction.

Derived Paystack callback: `https://<frontend-host>/dic/register/payment-return`.
Webhook: `https://<backend-host>/api/v1/dic/payments/paystack/webhook/`.
Keep PAYSTACK_WEBHOOK_SECRET absent unless the account uses the supported
timestamped signing format. Independent verification, signature/amount/currency,
unique references, transactions and durable settlement remain. Redirects are
never payment proof. No production payment is authorized by this guide.

## Exact unresolved hosting dependency

Published docs establish native builds, static SPA serving, internal database
credentials and managed HTTPS, but do not establish **(a)** ingress replacement of
client X-Forwarded-Proto/no direct backend bypass, **(b)** this purchased database's
TLS certificate hostname/issuer/trust provisioning, or **(c)** readiness probes
using the correct ingress Host/scheme. Verify those actual behaviors before
production acceptance. Standard SECURE_PROXY_SSL_HEADER and verify-full depend
on them; no acknowledgement flag, invented network/certificate or TLS downgrade
substitutes for evidence. Also confirm usable ingress throttling: application
IP limits conservatively share socket-peer identity. Real email delivery,
approved data preparation and later live acceptance remain release gates.
This release is not yet certified ready.

## Sources and checks

- [ZevCloud Git-backed static/SPA settings](https://docs.zevcloud.net/guide/web-apps)
- [ZevCloud Python commands/PORT](https://docs.zevcloud.net/guide/python-apps)
- [ZevCloud existing database/internal credentials](https://docs.zevcloud.net/guide/databases)
- [ZevCloud scheduled-task limit](https://docs.zevcloud.net/guide/scheduled-tasks)
- [Django proxy security](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header)

Native CI builds React independently, checks Django production startup and real
CORS/preflight with only the four web variables and no database, and asserts readiness
fails closed. Existing PostgreSQL core discovery covers session/CSRF login/logout,
portal cookies, worker behavior, payments and business rules. Container CI is
manual rollback only; remove its old required branch-check entry manually once
replacement checks pass. Local Python is blocked; CI results remain required.

Local validation of the startup correction: all 237 frontend tests, the
separate-HTTPS-API production build, source lint, shell syntax and git whitespace
checks passed. Python 3.12 is unavailable, so the Django regressions are not run
locally. Native smoke deliberately refuses this checkout's local dotenv file;
clean-checkout CI must prove actual minimal web startup and worker rejection.
Vite retains a non-blocking bundle-size warning. No production data or secrets
were changed, and no deployment was performed.
