# ZevCloud website-only launch

For full registration/portal operation, use [FULL_LAUNCH.md](FULL_LAUNCH.md).
This guide remains the maintenance/public-pages-only path.

Local preparation only. No deployment, DNS changes, migrations or payment activation
are performed by this configuration. Public pages can launch independently of the
registration/housing rollout. APIs, Admin, registration, recovery, donations and
portal access return 503 in website-only mode. Uploaded media is unavailable;
bundled frontend assets remain available. Health checks still verify PostgreSQL.

## Builder settings

- Repository root directory: `.` (not `backend` or `dawana-platform`).
- Build pack: Dockerfile; file: `Dockerfile`; context: repository root.
- Target: final stage `runtime` (or leave target blank).
- Platform: `linux/amd64`; service port: `8080`.
- Install/build/start overrides: leave blank; use the Dockerfile ENTRYPOINT.
- Static-site mode: off. No build arguments are required.
- ZevCloud supplies PORT; keep the service setting at 8080. Nginx binds
  0.0.0.0:$PORT; Gunicorn intentionally stays private on loopback.
- Docker health command: `/opt/venv/bin/python /app/container/healthcheck.py`.
  It probes the private loopback readiness endpoint and requires Django's exact
  database-success response. It needs neither curl nor wget. Keep this exec-form
  check; do not replace it with a homepage check. A curl/wget warning alone is
  not evidence this Python command is unsupported. Ask ZevCloud to confirm it
  honors Docker HEALTHCHECK; remove a conflicting service-side command override.
  If using a provider HTTP probe, `/_container/ready` must pass through the verified
  HTTPS ingress with its required host/header contract; raw HTTP probes cannot
  bypass the gateway trust checks. The Docker check needs no public-header exception.
- Defaults use Node 22.19.0 Bookworm and Python 3.13 Bookworm image tags. These are
  mutable registry inputs; release CI continues supplying resolved NODE_IMAGE,
  PYTHON_IMAGE digests and SOURCE_REVISION. Without that override the image label
  honestly reads `unversioned`; record the ZevCloud source commit/build/image ID.

## Essential runtime variables

| Name | Exact value / format |
| --- | --- |
| PUBLIC_HOST | `dawana-islamic-foundation-web-app.zevcloud.app` for the current website-only acceptance; change to the custom domain only after separate domain authorization/verification |
| DJANGO_SECRET_KEY | Independent random secret of at least 50 characters; do not reuse database credentials |
| DAWANA_WEBSITE_ONLY | `true` explicitly; registration, portal, Admin, donations and payment remain unavailable |
| GATEWAY_TLS_MODE | `trusted-edge`, conditional on the verified managed-ingress contract below |
| TRUSTED_EDGE_CIDRS | **Unresolved:** provider-confirmed bounded immediate ingress networks, comma-separated; never guess or use /0 |
| EDGE_TRUST_VERIFIED | `1` **only after** the guarantees below are verified |

Keep the existing service port at `8080` and PORT at `8080` if explicitly supplied.
Keep the existing purchased database; no new PostgreSQL service is required.
Choose one connection configuration:

- **Keep the existing legacy connection:** retain DB_HOST, DB_NAME, DB_USER,
  DB_PASSWORD and DB_PORT with their existing provider values. Do not substitute
  the service label for a database name/hostname. Leave DATABASE_URL absent.
- **Alternatively use DATABASE_URL:** supply the existing correct PostgreSQL URL
  and delete redundant DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT fields. Existing
  Django behavior gives DATABASE_URL precedence if both are present; startup now
  reports CFG_DB_PRECEDENCE without printing any values. No automatic conversion
  or credential change occurs.

In either case edit DB_SSLMODE to `verify-full` (or omit it to use the same secure
default). A URL sslmode option must also be verify-full. Plaintext/require modes
are rejected, not downgraded or silently accepted.

If the database uses a custom CA, also set `DB_SSLROOTCERT` to its absolute
readable certificate-file path. Provision that file with ZevCloud's supported
secret/file mount mechanism; do not commit it or put PEM text in the path variable.
If system/libpq trust is sufficient, prove that with a real verify-full connection.
Do not add sslmode=require to the URL or use an IP not covered by the certificate.

### Existing variables: keep, edit or delete

| Existing variable(s) | Website-only action |
| --- | --- |
| DJANGO_SECRET_KEY | Keep if it meets production strength requirements; never print it |
| DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT | Keep unchanged when using the existing legacy connection; delete only if choosing DATABASE_URL instead |
| DATABASE_URL | Leave absent for legacy DB_*; if already correct and selected, keep it and remove redundant DB_* connection fields |
| DB_SSLMODE | Edit to `verify-full`, or delete to use that default; weaker values fail explicitly |
| DB_SSLROOTCERT | Keep/set to the mounted readable CA path when required; not PEM text; never remove a required CA to silence an error |
| PUBLIC_HOST | Edit to `dawana-islamic-foundation-web-app.zevcloud.app` now; do not list two hosts |
| PORT | Keep/set `8080`; service port also `8080` |
| DAWANA_WEBSITE_ONLY | Set `true` |
| GATEWAY_TLS_MODE | Set `trusted-edge` only with the verified provider requirements below |
| TRUSTED_EDGE_CIDRS, EDGE_TRUST_VERIFIED | Supply only verified values; if unverified this remains a release blocker |
| DJANGO_SETTINGS_MODULE, DJANGO_DEPLOYMENT_TARGET, DJANGO_BIND_ADDRESS, DJANGO_BIND_PORT, DAWANA_TRUSTED_GATEWAYS, DJANGO_TRUST_PROXY_HTTPS, DJANGO_DEBUG | Delete manual overrides and use container-owned secure defaults; genuinely different values fail explicitly |
| DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS, DJANGO_CORS_ALLOWED_ORIGINS | Delete legacy lists; derive them from PUBLIC_HOST. Equivalent single-host/same-origin entries are accepted; localhost, foreign or additional origins are rejected |
| PAYSTACK_MODE | Set `test`, or delete for the website-only default |
| PAYSTACK_LIVE_ENABLED | Set `false`, or delete for the website-only default |
| PAYSTACK_SECRET_KEY, PAYSTACK_WEBHOOK_SECRET, PAYSTACK_PUBLIC_KEY | Remove from this website-only service; do not revoke/rotate the real account credentials |
| PAYSTACK_CALLBACK_URL | Delete the unused legacy override; it is not needed while payments are disabled |
| DIC_PORTAL_ACCOUNTS_ENABLED, DIC_ASSISTED_BOOKING_ENABLED, DIC_EMAIL_RECOVERY_ENABLED, DIC_RECOVERY_DELIVERY_WORKER_ENABLED, DIC_BACKGROUND_WORKER_ENABLED, FOUNDATION_DONATIONS_ENABLED, FOUNDATION_CONTACT_FORM_ENABLED | Delete full-mode overrides, or set every one to `false` |
| DIC_MEMORY_STORAGE | Delete the override or set `disabled`; uploads stay unavailable |
| DIC_AUTOMATION_ACTOR_ID, DIC_PORTAL_EMAIL_VERIFY_URL, DIC_PORTAL_FRONTEND_URL, RESEND_API_KEY, SMTP/Google/R2 delivery settings | Not required for website-only operation; remove unused full-launch configuration from this service |

Boolean spelling/case such as True/False and equivalent duplicate/whitespace-only
host-list formatting are normalized safely. This never expands the hostname,
trusted networks or allowed origins. EDGE_TRUST_VERIFIED is never inferred.

Do not supply Paystack credentials. No SMTP, R2, Google, worker, Vite or duplicate
Django host/proxy settings are needed for this website-only launch. The entrypoint
derives exact hosts/CSRF, loopback proxy trust and verify-full; conflicting
overrides fail closed. DAWANA_WEBSITE_ONLY defaults to true. Live collection,
portal/recovery, contact submissions and uploads remain disabled. Do not set
DAWANA_WEBSITE_ONLY=false until the separate application release is approved.

## Startup diagnostics and the reported rollback

The old generic message proves entrypoint validation failed before Supervisor
started the application processes. It does not identify the failed branch, and
does not prove a database connection failure or a missing curl/wget binary.
Entrypoint does not connect to PostgreSQL; actual connection/TLS failures occur
in readiness after startup. No deployed variable values were inspected here.

Repository-confirmed compatibility defects repaired: raw string comparisons
rejected safe legacy boolean spellings and a same-origin CORS value that the
later Django contract already allowed. These are possible causes, not confirmed
values from the failed deployment. Stale host lists, enabled Paystack/portal
flags, missing edge trust, or other invalid settings remain hypotheses.

New errors log only a code and curated remedy, not original exception text,
credentials, URLs, private addresses/CIDRs, certificate paths or secret values:

| Code | Required response |
| --- | --- |
| CFG_CONFLICT_<variable> | Remove/repair the named container-policy override |
| CFG_BOOLEAN_<variable> | Correct the named boolean's format |
| CFG_WEBSITE_ONLY_<variable> | Remove an enabled feature/credential incompatible with website-only mode |
| GW_PUBLIC_HOST / GW_PORT / GW_TLS_MODE | Correct the hostname/port/mode using the configuration above |
| GW_EDGE_UNVERIFIED / GW_EDGE_CIDRS | Obtain verified managed-ingress guarantees/networks; do not invent them |
| CFG_SECRET_KEY | Supply a production-strength independent Django secret |
| CFG_DATABASE_URL / CFG_DATABASE_URL_TLS / CFG_DATABASE_CA_CONFLICT | Repair connection format/TLS settings or the selected configuration source |
| CFG_MISSING_DB_HOST / CFG_MISSING_DB_NAME / CFG_MISSING_DB_USER / CFG_DB_PORT | Complete the existing legacy connection fields |
| CFG_DATABASE_CA_FILE | Mount the required CA file readably; do not disable certificate verification |
| DJ_SETUP / DJ_CONTRACT / DJ_HOSTS / DJ_ORIGINS / DJ_WORKERS / DJ_EMAIL_URL | Review production settings/application loading; website-only must not start workers |
| RUNTIME_REQUIREMENTS | Use the reviewed image with its pinned Python/Django, fonts and ffprobe |
| NGINX_WRITE | Make /run/dawana writable by UID 10001 |
| NGINX_VALIDATE | Check generated config/direct-TLS file mounts and permissions; raw Nginx errors are suppressed to avoid disclosing paths/networks |
| SUPERVISOR_START / STARTUP_INTERNAL | Verify image contents and runtime process/directory permissions |
| HC_CONNECTION | The private readiness socket is unavailable/timed out; inspect startup codes first |
| HC_HTTP / HC_RESPONSE | Django readiness failed or returned the wrong payload; verify DB hostname/CA/connectivity (and workers only in full mode) |

Do not dump the service environment, Docker environment inspection or provider
exceptions while diagnosing. Share the safe code/remedy and image revision only.

## Provider security requirements: currently unresolved

Before deploying, obtain evidence that ZevCloud:

1. Terminates public HTTPS with a valid certificate and redirects public HTTP to
   HTTPS before requests reach this container.
2. Connects from the exact TRUSTED_EDGE_CIDRS visible at the container socket.
3. Replaces client-supplied X-Forwarded-Proto with exactly `https` and X-Real-IP
   with one valid client address; does not preserve a forged value or append a chain.
4. Prevents direct/untrusted bypass of that ingress. The gateway rejects untrusted
   peers and does not trust arbitrary forwarded headers.
5. Supplies PostgreSQL authenticated TLS with a matching hostname, trusted chain,
   and a supported way to provision any CA certificate file.

Managed SSL documentation alone does not verify those guarantees. Setting
EDGE_TRUST_VERIFIED is an acknowledgement of evidence, not a security test.

## Deployment procedure after security acceptance

1. Review/publish the approved source through a separately authorized process.
2. Connect the repository; select the builder settings above.
3. Enter only essential runtime variables and the conditional CA path/mount.
4. Keep website-only defaults. No migration, seeding, cache-table creation or
   superuser command belongs in the start command.
5. In a separately authorized deployment, validate HTTPS, rejection of spoofed
   forwarding headers, DB readiness, SPA deep-link refresh and static assets.
   Registration, payment, webhook, portal and Admin routes must remain 503.
6. Record the source commit and image/build identity. Retain existing DB/backups.

Website readiness performs SELECT 1 only; it does not require application tables
or prove migration, cache, SMTP or storage readiness. No migrations are necessary
for this website-only gate. Failed DB verification still prevents healthy status.

## Smallest alternative if ingress is incompatible

Keep the combined container and use its existing `GATEWAY_TLS_MODE=direct` with
mounted GATEWAY_TLS_CERT_FILE and GATEWAY_TLS_KEY_FILE **only if** ZevCloud supports
TLS passthrough to the container. Verify passthrough, certificate renewal and
client identity first. Otherwise the existing production-start.sh/Gunicorn path
needs a provider-specific trusted-ingress adapter and a way to serve the Vite
build. Switching to Gunicorn alone does not remove the trust requirement and is
not a verified fallback. Do not deploy by weakening HTTPS or database TLS.

## Sources checked

- https://docs.zevcloud.net/guide/dockerfile — root Dockerfile, PORT, amd64.
- https://docs.zevcloud.net/guide/web-apps — managed web apps; outbound SMTP blocked.
- https://docs.zevcloud.net/ — managed SSL and PostgreSQL offerings.

These sources did not establish ingress CIDRs/header replacement or database CA
provisioning. Later email rollout needs a supported HTTPS email adapter because
ZevCloud documents outbound SMTP restrictions; it is not a website-only dependency.
