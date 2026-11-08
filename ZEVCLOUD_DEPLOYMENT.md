# DA'WANA: native ZevCloud full application

## Architecture

Use **two native Web Application services**, both built from the repository root:

1. **Web:** Gunicorn + Django + WhiteNoise serve the built React/Vite frontend,
   `/api/v1/`, `/admin/` and static files on one HTTPS origin.
2. **Worker:** the existing durable housing/recovery/account-delivery command,
   with a read-only health endpoint to fit ZevCloud's long-running Web App model.

Both use the **existing PostgreSQL 18 service** and its database-backed queue/cache.
No second database, Redis, Celery, Nginx, Supervisor or custom gateway is required.
The frontend needs no separate static service, API-origin variable or cross-origin
cookies. Client code still uses `/api/v1`; business workflows remain real services.

ZevCloud documents Nixpacks, Python/Node, custom start commands and a listening
service port. No dedicated worker/cron product was established in the documentation
inspected, so both roles use ordinary Web Apps. The included nixpacks.toml selects
Python 3.13/Node 22, ffprobe and fonts. The platform builds its own runtime image;
there is no application-maintained Dockerfile on this path.

## 1. Builder and start commands

Connect the reviewed branch to both services. Do not deploy without authorization.

| Setting | Both services |
| --- | --- |
| Root directory | `.` |
| Build pack | Native / Nixpacks, not Dockerfile |
| Install | Leave unset: use nixpacks.toml, which creates/activates `/opt/venv` and runs `bash backend/native-install.sh` |
| Build | `bash backend/native-build.sh` |
| Static-site mode | Off |
| Service port | `8080`; ZevCloud supplies PORT |

| Role | Start | Health path |
| --- | --- | --- |
| Web | `bash backend/native-start.sh web` | `/api/v1/health/` through managed ingress |
| Worker | `bash backend/native-start.sh worker` | `/health/` |

Use two services, not a background command appended to web startup. The worker's
HTTP endpoint performs no business work. The root Dockerfile was archived at
`ops/container/Dockerfile.rollback` to prevent Docker autodetection. Rollback CI
uses that explicit path. Build/start never migrate, seed, create users or enable
live collection. Builds use database-free static settings and constrained packages.
If an explicit install override is required, use exactly:
`python -m venv --copies /opt/venv && . /opt/venv/bin/activate && bash backend/native-install.sh`.
Keep the manifest's `/opt/venv/bin` runtime PATH; do not replace the Nixpacks
install phase with a bare pip command.

## 2. Minimum runtime configuration

Use the same application configuration on both services. PUBLIC_HOST is the
**Web** hostname on both; the worker's generated hostname is only for its health.

| Variable | Value |
| --- | --- |
| PUBLIC_HOST | Actual Web hostname; initially `dawana-islamic-foundation-web-app.zevcloud.app`; custom domain only after separate authorization/verification |
| DJANGO_SECRET_KEY | Existing independent secret, at least 50 characters; same on both |
| DATABASE_URL | Existing PostgreSQL connection with restricted role and certificate-matching hostname |
| ZEV_PROXY_HEADERS_VERIFIED | `true` only after the provider requirements below are confirmed |
| DIC_AUTOMATION_ACTOR_ID | Existing active staff service-user ID, no superuser rights or usable password |
| DIC_RECOVERY_ENCRYPTION_KEY | Existing stable Fernet key, same on both |
| DEFAULT_FROM_EMAIL | Provider-verified sender |
| RESEND_API_KEY | Sending secret for the included HTTPS email backend |

Instead of DATABASE_URL, existing DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT remain
supported. Choose one source; DATABASE_URL takes precedence. DB_SSLMODE stays
**verify-full**. When required, also set DB_SSLROOTCERT to the readable mounted CA
file on both services. Never guess a certificate, use an unmatched IP or disable
verification. Do not create another database.

Derived defaults include production settings, exact host/same-origin CSRF, empty
CORS, Secure/HttpOnly/SameSite=Lax cookies, full application/accounts/recovery/
workers, HTTPS email, frontend payment callback and portal verification URLs.
No frontend VITE_API_BASE_URL or external scheduler is required.

Live payments default off. An approved isolated test can use PAYSTACK_MODE=test
and its matching test key. Test-mode receipts never grant production paid access.
After separate live approval only, set PAYSTACK_MODE=live, PAYSTACK_LIVE_ENABLED=true
and the existing matching PAYSTACK_SECRET_KEY on both services. Account URLs:

- Callback: `https://<PUBLIC_HOST>/dic/register/payment-return` (frontend route).
- Webhook: `https://<PUBLIC_HOST>/api/v1/dic/payments/paystack/webhook/`.

Keep PAYSTACK_WEBHOOK_SECRET absent unless the account uses the supported
timestamped signing format. Existing signature, independent verification,
amount/currency/reference/identity checks and idempotency remain unchanged.
Use existing R2 media/private configuration for uploads/portraits when needed;
no local production upload storage is introduced. Optional Google/SMS/WhatsApp
and feedback features retain their existing configuration contracts.

### Delete obsolete container overrides

Remove GATEWAY_TLS_MODE, GATEWAY_TLS_CERT_FILE, GATEWAY_TLS_KEY_FILE,
EDGE_TRUST_VERIFIED, TRUSTED_EDGE_CIDRS, DAWANA_TRUSTED_GATEWAYS,
DJANGO_TRUST_PROXY_HTTPS, DJANGO_BIND_ADDRESS, DJANGO_BIND_PORT,
DJANGO_DEPLOYMENT_TARGET and DAWANA_WEBSITE_ONLY from the native services.
Remove stale DJANGO_ALLOWED_HOSTS/CSRF/CORS and account/worker-disable overrides
so native defaults apply. Keep required secrets/database fields. No ops/container
script is used by native build/start. Never put secrets in the build manifest.

## 3. External requirements that cannot be assumed

**Managed HTTPS:** verify ingress isolation/no direct bypass, preserved Host,
and replacement of client X-Forwarded-Proto with the real single http/https value.
Django retains HTTPS redirects and Secure cookies; missing/ambiguous schemes fail
closed. Verify X-Forwarded-For is stripped or includes the real provider-added
client address, never a client-only value. Only a single valid sanitized IP is
used; chains/invalid/absent values retain the socket peer and conservative shared
limits. Verify normal per-client throttling. There is no CIDR list or custom
identity header. A certificate alone does not justify ZEV_PROXY_HEADERS_VERIFIED.

**Database:** provider documentation does not establish authenticated TLS/hostname
or CA mounting details for this purchased endpoint. Verify them without downgrading
verify-full. No production database was accessed by this refactor.

**Email:** accept real verification/recovery delivery with a verified HTTPS sender.
ZevCloud documents SMTP restrictions. The included Resend adapter is implemented;
no provider account or sender DNS was provisioned. An existing accepted HTTPS Django
email backend can instead be configured with EMAIL_BACKEND and its credentials.

**Native runtime:** verify the resolved build log honors nixpacks.toml and supplies
Python 3.13, Node 22, ffprobe and Liberation fonts. Native builds/process startup
were not executed locally. Do not infer deployed support from configuration alone.

## 4. Short release checklist

1. Obtain passing backend/PostgreSQL 18 acceptance, native configuration tests and
   Vite tests/build for this exact commit. Never test against production.
2. Verify managed ingress, DB TLS/CA and HTTPS email requirements above.
3. Back up production and use the existing separately approved release_migrations
   process with `DJANGO_SETTINGS_MODULE=config.settings.zevcloud`. Exact target,
   cluster binding and approved manifest remain mandatory; never migrate at startup.
4. Separately approve the existing cache table and automation actor with
   `dic.can_process_housing_queue`, `dic.can_allocate_participants` and
   `dic.can_approve_housing_guardians`. Configure approved edition, fees/dates,
   inventory and allocation fingerprint. No automatic administrator creation.
5. After deployment authorization, start Worker and Web. Web readiness requires
   DB connectivity and a recent worker heartbeat in the existing shared DB cache.
   Worker failure makes health unready after heartbeat expiry. No shared filesystem.
6. Run `python backend/manage.py check_dic_launch --settings=config.settings.zevcloud`
   (read-only). Accept deep-link refresh, Admin/static files, cookies, CSRF,
   delivery/recovery, guardian group/capacity safety and scoped portal access.
7. Separately approve live Paystack activation and a controlled acceptance payment,
   then invite registrants. A redirect is never payment proof.

Existing jobs/leases/retries/holds are retained. Valid payments survive housing or
email delays. Accounts are separate from email delivery. Tutor accommodation stays
offline; ambiguous guardians/capacity failures remain holds for exceptional review.

## Sources and limits

- [ZevCloud native services](https://docs.zevcloud.net/guide/web-apps)
- [ZevCloud build detection](https://docs.zevcloud.net/guide/how-deploys-work)
- [Nixpacks multiple providers](https://nixpacks.com/docs/guides/configuring-builds)
- [WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html)
- [Django proxy trust](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header)

Local validation: all 237 frontend tests, Vite production build, native shell
syntax, rollback packaging contract and git whitespace checks passed. Python
execution is denied by this Windows environment; new backend tests have not run.
The native-packaging workflow runs a database-free build and synthetic routing/
fail-closed readiness checks in CI; PostgreSQL core discovery includes the new
configuration/heartbeat tests. These CI results are still required.

Python/Nixpacks and production connectivity are unavailable locally. Provider
guarantees, actual native build/start, real email and live payment acceptance remain
unverified. No deploy, purchase, DNS change, production access/migration, live
activation, commit or push occurred. This is an implemented path, not a live release.
