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
- Health path: `/_container/ready` over the verified HTTPS ingress. Do not accept
  the SPA homepage as readiness. Docker also probes a private loopback endpoint.
- Defaults use Node 22.19.0 Bookworm and Python 3.13 Bookworm image tags. These are
  mutable registry inputs; release CI continues supplying resolved NODE_IMAGE,
  PYTHON_IMAGE digests and SOURCE_REVISION. Without that override the image label
  honestly reads `unversioned`; record the ZevCloud source commit/build/image ID.

## Essential runtime variables

| Name | Exact value / format |
| --- | --- |
| PUBLIC_HOST | `dawanaislamicfoundation.org`, or the exact assigned ZevCloud hostname used for initial acceptance; one hostname, no scheme/path |
| DJANGO_SECRET_KEY | Independent random secret of at least 50 characters; do not reuse database credentials |
| DATABASE_URL | Existing `dawana-postgres` PostgreSQL connection URL with certificate-matching hostname and restricted runtime role; secret |
| TRUSTED_EDGE_CIDRS | **Unresolved:** provider-confirmed bounded immediate ingress networks, comma-separated; never guess or use /0 |
| EDGE_TRUST_VERIFIED | `1` **only after** the guarantees below are verified |

If the database uses a custom CA, also set `DB_SSLROOTCERT` to its absolute
readable certificate-file path. Provision that file with ZevCloud's supported
secret/file mount mechanism; do not commit it or put PEM text in the path variable.
If system/libpq trust is sufficient, prove that with a real verify-full connection.
Do not add sslmode=require to the URL or use an IP not covered by the certificate.

Do not supply Paystack credentials. No SMTP, R2, Google, worker, Vite or duplicate
Django host/proxy settings are needed for this website-only launch. The entrypoint
derives exact hosts/CSRF, loopback proxy trust and verify-full; conflicting
overrides fail closed. DAWANA_WEBSITE_ONLY defaults to true. Live collection,
portal/recovery, contact submissions and uploads remain disabled. Do not set
DAWANA_WEBSITE_ONLY=false until the separate application release is approved.

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
