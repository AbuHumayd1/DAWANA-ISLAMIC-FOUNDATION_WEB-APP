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
| Python | `3.13` (manifest; matches pinned dependencies/CI) |
| Install | Leave unset; use manifest command below |
| Build | `bash backend/native-build.sh` |
| Start | `bash backend/native-start.sh web` |
| Port | `8080` |
| Readiness path | `/api/v1/health/` |

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

### Minimum Backend and Worker environment

Use the same values on both. PUBLIC_HOST is the **Backend** host, never the
worker host. Frontend has only the Vite build variable above.

| Variable | Value |
| --- | --- |
| PUBLIC_HOST | Exact backend hostname, no scheme/path |
| FRONTEND_ORIGIN | Exact frontend HTTPS origin, no trailing slash/path |
| DJANGO_SECRET_KEY | Existing independent random secret, at least 50 characters |
| DATABASE_URL | Existing PostgreSQL connection from its Overview; private |
| DIC_AUTOMATION_ACTOR_ID | Existing authorized active staff service-user ID |
| DIC_RECOVERY_ENCRYPTION_KEY | Existing stable Fernet key; preserve in backups |
| DEFAULT_FROM_EMAIL | Verified sender address |
| RESEND_API_KEY | Sending credential for the included HTTPS email adapter |

Instead of DATABASE_URL use **DB_HOST, DB_NAME, DB_USER, DB_PASSWORD**, plus
DB_PORT when different from 5432. Choose one format; DATABASE_URL takes precedence.
Use existing internal credentials, never a new database. PostgreSQL identity is
verified using standard libpq **verify-full**. Add **DB_SSLROOTCERT** as the
readable mounted trusted CA file when that endpoint's issuer is not already
trusted by libpq. Use its certificate-matching hostname, never a guessed alias/IP.
There is no SQLite fallback or automatic migration.

Derived defaults: exact allowed backend host, credentialed CORS/CSRF for the
frontend only, frontend portal/email/callback URLs, full accounts/recovery/workers,
HTTPS redirects and Secure/HttpOnly host-only Lax session cookies. No proxy
acknowledgement flag. Forwarded client IPs are ignored; socket-peer throttles
remain conservative/shared. No arbitrary client identity/host headers are trusted.

Remove obsolete GATEWAY_*, TRUSTED_EDGE_CIDRS, EDGE_TRUST_VERIFIED,
ZEV_PROXY_HEADERS_VERIFIED, DAWANA_TRUSTED_GATEWAYS, DJANGO_TRUST_PROXY_HTTPS,
DJANGO_BIND_*, DJANGO_DEPLOYMENT_TARGET, DAWANA_WEBSITE_ONLY and old
DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS / DJANGO_CORS_ALLOWED_ORIGINS.
Remove old callback/portal URLs and account/worker-disable overrides so defaults
apply. Keep genuine secrets, approved business settings and existing object
storage credentials. Do not copy the old container environment wholesale.

An accepted HTTPS Django email backend can replace the default via EMAIL_BACKEND
and its credentials. Console/locmem delivery is rejected. ZevCloud blocks SMTP;
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

Use one additional ordinary **Web Application**, Python / Native Nixpacks, same
root/install/build, port 8080 and environment as Backend. Start:

```
bash backend/native-start.sh worker
```

Health: `https://<worker-host>/health/`, a read-only generic response. Existing
bounded housing, recovery, portal OTP and verification commands run every 15
seconds. Their durable claims, leases, retries and idempotency remain intact.
Heartbeat uses the existing shared database cache, not a shared filesystem.
Worker health and backend readiness return 503 for missing/stale heartbeat
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
5. After release authorization, start Worker, Backend, then static Frontend.
   Backend readiness: `https://<backend-host>/api/v1/health/`. Worker health is
   above. Check connectivity/TLS/schema/cache/edition/delivery read-only:

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
CORS/preflight using synthetic configuration/no database, and asserts readiness
fails closed. Existing PostgreSQL core discovery covers session/CSRF login/logout,
portal cookies, worker behavior, payments and business rules. Container CI is
manual rollback only; remove its old required branch-check entry manually once
replacement checks pass. Local Python is blocked; CI results remain required.

Local validation: 237 frontend tests passed, followed by 21 focused API/session/
callback regressions after the final build-variable change. The separate-HTTPS-API
production build passed. Shell syntax and git whitespace checks passed. Lint
exited successfully (existing preview-bundle warnings); the changed frontend
files passed focused lint without warnings. Django startup/policy tests and the
native smoke command could not run: Windows denied Python execution and Git Bash
had no Python interpreter. Vite retains a non-blocking bundle-size warning.
