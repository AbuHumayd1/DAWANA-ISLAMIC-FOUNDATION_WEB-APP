# Single-origin production container — packaging, not deployment approval

Accepted application baseline: `116a3f626bd6baa7cea6dc2929f55c7731186d21`.
Owner reports main acceptance run 42412886596 passed 9/9. That is not evidence
for this new container. No image has been built, published or deployed locally.

## Architecture and deployment paths

```
https://dawanaislamicfoundation.org
  -> verified provider TLS edge -> unprivileged Nginx :$PORT
       -> / and client routes: immutable Vite dist
       -> /api/, /admin/, /static/: Gunicorn 127.0.0.1:10000
       -> /media/, raw /health/: 404
Gunicorn -> verify-full PostgreSQL and independently configured R2 buckets
Tini -> validating entrypoint -> Supervisor -> Nginx + Gunicorn
```

Naijacloud accepts public GHCR images and does not currently expose a GitHub
Dockerfile build option. Use its Docker image source for the complete Django +
React image. Do not use a generic Node/Python build command for this container.
Architecture, digest support, ingress and health-probe behavior still require
provider confirmation before deployment.

## GHCR publication (requires approval before push/merge)

The existing .github/workflows/container-packaging.yml now verifies every pull
request and every push to main, with an optional workflow_dispatch. Publication
runs only in AbuHumayd1/DAWANA-ISLAMIC-FOUNDATION_WEB-APP on refs/heads/main for a
push or manual dispatch, and only after the packaging job succeeds. A dispatch on
another branch verifies only. Merging this workflow enables publication on future
main pushes, including the merge itself; obtain explicit approval first.

Verification retains all pure gateway tests, offline packaging checks, fail-closed
startup, direct-TLS and trusted-edge smoke tests, unavailable-DB readiness and
shutdown coverage. It builds the existing production Dockerfile with repository
root context for linux/amd64. Node/Python bases are resolved to digests before the
build and recorded with the source revision and dependency inventories. The exact
loaded image that passes verification is transferred by a same-run artifact to a
separate publish job; publication never rebuilds it. A failed verification skips
publication. Backend production acceptance remains a separate required PR check;
configure branch protection to require its nine jobs and container packaging.

All actions in this workflow use immutable commit SHA pins. Docker action pins
were checked against their upstream commit pages; this is not a full dependency
security audit. Only the publishing job gets contents: read and packages: write;
it authenticates to ghcr.io using secrets.GITHUB_TOKEN. No PAT or production
secrets are required. Checkout disables persisted credentials. The publishing job
does not check out or execute application code. No pull_request_target or
cross-run artifact promotion is used.

Only a clean hosted-runner checkout is built. Local untracked artifacts are never
uploaded. Preserve the default-deny .dockerignore and its exclusions for .env,
credentials, keys, databases, media, uploads, caches and Git metadata. Never add
production secrets as build arguments or copy local directories into CI context.

Published image references:

- ghcr.io/abuhumayd1/dawana-web:sha-<full-40-character-commit-SHA>
- ghcr.io/abuhumayd1/dawana-web:main (moving convenience tag)
- ghcr.io/abuhumayd1/dawana-web@sha256:<published-digest> (preferred deployment)

No latest tag is generated. Commit tags identify source; registry tags are
technically mutable, so retain and deploy the digest reported in the publish job
summary. A rerun can rebuild different dependency versions for the same source;
do not treat a SHA tag as a substitute for a content digest. Retain prior release
digests and avoid deleting versions needed for rollback. Serialized main runs
prevent concurrent publishing jobs; manually rerunning an older run can still
move main backwards, so never use main as a pinned production release.

After the first approved publication, open GitHub profile Packages > dawana-web >
Package settings, confirm its linked repository and Actions access, and change
visibility to Public. Public visibility is a separate owner action, not performed
by this workflow; review that decision before enabling anonymous pulls. If an
existing package denies GITHUB_TOKEN writes, grant this repository Actions write
access in package settings rather than introducing a PAT. Verify an anonymous
pull of the exact digest from a clean client before configuring Naijacloud.

In Naijacloud select Docker image and use the published digest above, or the full
sha-commit tag if the provider cannot accept digests. Confirm linux/amd64 support.
Set the service ingress port and PORT to 8080. Keep the image entrypoint/default
startup; it runs Tini, validates production settings and gateway configuration,
then starts Supervisor with Nginx and private Gunicorn. Missing/unsafe settings
fail startup. No migrations, seeds, superuser creation or workers run at startup.
Inject approved runtime secrets separately using the inventory below.

Use /_container/ready as the provider readiness path only after verifying the
trusted TLS-edge headers and separately approving database access; database
unavailability must return 503. /_container/live checks Nginx only. Docker's
internal healthcheck uses loopback :9090; expose only 8080, never 9090 or 10000.
Retain the TLS/client-IP contract below and allow at least 45 seconds shutdown
grace. Image publication does not authorize deployment, DNS, payments or DB work.

Rollback: select the previous retained image@sha256 digest in Naijacloud, preserve
its compatible runtime configuration, and verify schema compatibility before an
approved redeployment. Check readiness and browser/API routes afterward. Image
rollback does not reverse migrations; never restore or modify a production DB as
an automatic rollback action.

The dashboard's repository/branch/root, commands, variables, secret files, region,
size, port and health-path controls are owner-confirmed. Multi-process compatibility,
TLS ingress/peer/header guarantees, database TLS/roles, cron and independent restores
remain unverified. Public web-service documentation was inaccessible during review.

## Build, provenance and reproducibility

Use a clean reviewed checkout/CI SHA descended from the accepted application SHA.
Do not package a dirty tree for publication or use local main merely by name.
The current workspace has read-only Git metadata and stale cached origin/main.
Fetch/main-merge verification and a new branch/commit could not be completed here.
Use a fresh checkout from current origin/main before committing this patch.

Example Bash procedure on an approved builder (build only; no registry push):

```bash
git status --porcelain=v1
git rev-parse HEAD
git merge-base --is-ancestor 116a3f626bd6baa7cea6dc2929f55c7731186d21 HEAD
# Review outputs and bind these variables to actual approved immutable digests.
NODE_IMAGE='node@sha256:APPROVED_NODE_22_BOOKWORM_DIGEST'
PYTHON_IMAGE='python@sha256:APPROVED_PYTHON_313_BOOKWORM_DIGEST'
SOURCE_REVISION=$(git rev-parse HEAD)
docker build --build-arg NODE_IMAGE="$NODE_IMAGE" \
  --build-arg PYTHON_IMAGE="$PYTHON_IMAGE" \
  --build-arg SOURCE_REVISION="$SOURCE_REVISION" -t dawana-package:reviewed .
bash ops/container/smoke.sh dawana-package:reviewed
bash ops/container/smoke-edge.sh dawana-package:reviewed
```

Replace placeholders; do not execute them literally. Build stages use npm ci and
the existing backend requirements/constraints. Node/build dependencies stay outside
the runtime stage. Debian installs Nginx, Supervisor, Tini, fonts-liberation, ffmpeg
(including ffprobe), and CA certificates. Runtime user/group is 10001; only
/run/dawana and /tmp need writes. Backend/frontend/source/venv remain root-owned.
The Docker build performs static collection using isolated build-only settings,
without dotenv, application model setup, secrets or a database. Static output uses
the production WhiteNoise compressed manifest backend. Normal production scripts
remain unchanged; the image deliberately bypasses their production-secret-dependent
build check and validates production settings during container startup instead.

Frontend lockfile and immutable base digests are supported. Existing backend
requirements are NOT a complete hash lock, and apt packages are not snapshot-pinned.
Consequently byte-for-byte rebuild reproducibility is NOT claimed. The image records
resolved Python/system packages; CI records base digests and source SHA. Retain the
tested immutable IMAGE DIGEST as the release artifact. Full dependency/snapshot
locking remains an explicit release-reproducibility gate; never invent versions.

.dockerignore is default-deny with explicit source inputs and repeated exclusions
for env files, credentials, keys, DB files, media, caches, virtualenvs and Git data.
Do not pass secrets through build args. No migrations, seed, cache table or admin
creation occurs in the build/entrypoint. The image performs no payment activation.

## TLS and client-IP contract (mandatory gate)

`GATEWAY_TLS_MODE=trusted-edge` is intended for a verified HTTPS hosting edge. It
requires EDGE_TRUST_VERIFIED=1 plus bounded TRUSTED_EDGE_CIDRS. This acknowledgement
is not proof: obtain actual provider evidence first. The immediate edge MUST strip
client-supplied X-Real-IP/X-Forwarded-Proto and replace them with one validated
visitor IP and the exact scheme `https`. App/container networking must restrict
access to that edge. Chained/append-only X-Forwarded-For is unsupported by this
adapter. The renderer rejects wildcard CIDRs. Nginx rejects untrusted peers,
missing IPs and non-HTTPS schemes before routing. Django rejects malformed IPs.

Nginx overwrites Host, X-Dawana-Client-IP and X-Forwarded-Proto for Django, clears
Forwarded/X-Forwarded-For, and keeps Gunicorn private. Django trusts only its local
gateway; DRF and durable throttles share the resolved REMOTE_ADDR. Do not substitute
the provider proxy's IP for every visitor or disable trust checks for health probes.
Provider health probes must arrive with the same verified headers, or use another
separately reviewed health protocol. No public HTTP-to-HTTPS bypass is provided.

`GATEWAY_TLS_MODE=direct` terminates TLS in Nginx using read-only injected cert/key
files readable by UID 10001. It takes client identity from the socket and ignores
external scheme/IP headers. Direct mode is not appropriate behind an unverified
proxy: it would throttle the proxy address. It needs external certificate issuance
and renewal; no certificate or private key is embedded in the image.

Container startup enforces production settings, exact host, same-origin CSRF/CORS,
local Gunicorn binding and local-gateway trust. Failures exit nonzero without echoing
supplied values. It does not query PostgreSQL. Nginx configuration is validated
before Supervisor starts. Any Nginx/Gunicorn process exit triggers whole-container
shutdown/nonzero exit; normal SIGTERM/INT drains and reaps children. Allow at least
45 seconds termination grace. Runtime binaries/fonts must pass the existing gate.

## Routing, readiness and logging

* Public origin: https://dawanaislamicfoundation.org; browser API /api/v1 only.
* Callback: /dic/register/payment-return (React deep link).
* Webhook: /api/v1/dic/payments/paystack/webhook/ (Django).
* /api, /admin, /static namespaces always go to Django; backend 404s never become SPA.
* Missing /assets files return 404 with appropriate MIME types, not index.html.
* Hashed assets are immutable-cacheable; index.html is no-store. API/admin/static
  gateway responses are private/no-store; no proxy response cache exists.
* /media raw access is denied. Private R2 access remains authorization-gated in Django.
* /_container/live proves Nginx is responding only, not Django/DB/payment health.
* /_container/ready proxies the existing Django /api/v1/health/ SELECT 1 readiness.
  It returns 503 when DB is unavailable. It does not prove schema/cache/R2/SMTP or
  Paystack readiness. Recommended Naijacloud health path: /_container/ready once
  database operations are separately approved. Never accept a SPA 200 as readiness.
* Docker HEALTHCHECK uses a private loopback :9090 readiness socket. Do not expose
  9090 or 10000 in provider networking. Health never disables public HTTPS rules.

Nginx emits aggregate status/time only to stdout; emergency errors go to stderr.
No access URI, query, cookie, token, participant identity or IP is logged. Django's
privacy filtering and Gunicorn warning stderr/no-access-log policy remain intact.
Supervisor emits lifecycle logs to stderr. Do not enable provider body/header/URL
capture without privacy review. Alert on readiness, restarts, DB/backups, queue age
and scheduler failures. The Docker health status requires provider monitoring;
Docker alone does not automatically restart an unhealthy but running container.

## Runtime variable inventory

All examples below are synthetic/placeholders; supply secrets through approved
runtime injection/secret files, never image layers or frontend variables.

| Name | Required/purpose | Format/example | Validation/start behavior |
| --- | --- | --- | --- |
| PUBLIC_HOST | Required packaging host | dawanaislamicfoundation.org | Exact hostname; injection rejected. |
| PORT | Required ingress agreement | 8080 | 1024–65535, excluding internal 9090/10000. |
| GATEWAY_TLS_MODE | Required packaging TLS model | trusted-edge or direct | No default; fails closed. |
| EDGE_TRUST_VERIFIED | Required edge-mode approval acknowledgement | 1 | Other values rejected. |
| TRUSTED_EDGE_CIDRS | Required edge-mode immediate peers | provider-confirmed comma-separated CIDRs | Strict networks, no /0. |
| GATEWAY_TLS_CERT_FILE, GATEWAY_TLS_KEY_FILE | Required direct-mode secret-file paths | /run/tls/cert.pem, /run/tls/key.pem | Absolute safe paths; Nginx validates readability. |
| DJANGO_SETTINGS_MODULE | Required, image default | config.settings.production | Other settings rejected by entrypoint. |
| DJANGO_DEPLOYMENT_TARGET | Required, image default | self-managed | Container uses local proxy model, not provider-name alias. |
| DJANGO_BIND_ADDRESS, DJANGO_BIND_PORT | Required, image defaults | 127.0.0.1, 10000 | Entry rejects external Gunicorn exposure. |
| DAWANA_TRUSTED_GATEWAYS | Required | 127.0.0.1/32 | Exact local gateway only. |
| DJANGO_TRUST_PROXY_HTTPS | Required | true | Required by entrypoint after trust acceptance. |
| DJANGO_ALLOWED_HOSTS | Required | dawanaislamicfoundation.org | Must equal PUBLIC_HOST exactly. |
| DJANGO_CSRF_TRUSTED_ORIGINS | Required | https://dawanaislamicfoundation.org | Exactly one matching public origin. |
| DJANGO_CORS_ALLOWED_ORIGINS | Optional | empty or matching HTTPS origin | Cross-origin configuration rejected. |
| DJANGO_SECRET_KEY | Required SECRET | independent 50+ character value | Existing production validation; preserve for credential recovery. |
| DJANGO_DEBUG | Optional, keep false | false | Production DEBUG stays false. |
| DATABASE_URL | Required OR DB_* alternative, SECRET | PostgreSQL URI supplied securely | Existing base settings parsing; never print URI. |
| DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT | Alternative DB config, password SECRET | fresh name/restricted role/certificate hostname/5432 | Existing PostgreSQL settings; no startup migration. |
| DB_SSLMODE | Required policy/default | verify-full | Weaker modes rejected. |
| DB_SSLROOTCERT | Required when custom CA needed | /run/secrets/postgres-ca.pem | Trusted file must match server chain/hostname. |
| DB_CONN_MAX_AGE | Optional | 60 | Size connections across web and workers; provider limit pending. |
| PAYSTACK_MODE, PAYSTACK_LIVE_ENABLED | Required safe initial state | test, false | Existing mode/key checks; no automatic activation. |
| PAYSTACK_SECRET_KEY, PAYSTACK_WEBHOOK_SECRET | Conditional SECRETS | test keys only during test acceptance | Existing provider authentication checks retained. |
| PAYSTACK_CALLBACK_URL | Conditional payment test | https://dawanaislamicfoundation.org/dic/register/payment-return | Existing provider URL checks. |
| DIC_MEMORY_STORAGE | Optional initially disabled; required s3 for media acceptance | disabled or s3 | Local production uploads remain prohibited. |
| DIC_MEDIA_S3_BUCKET, DIC_PRIVATE_S3_BUCKET | Required for s3 | dawana-production-media, dawana-production-private | Exact distinct production buckets. |
| DIC_MEDIA_S3_ENDPOINT, DIC_PRIVATE_S3_ENDPOINT | Required for s3 | account-specific HTTPS R2 endpoint | Existing strict R2 hostname validation. |
| DIC_MEDIA_S3_REGION, DIC_PRIVATE_S3_REGION | Required for s3 | auto | Existing storage validator. |
| DIC_MEDIA_S3_ACCESS_KEY_ID, DIC_MEDIA_S3_SECRET_ACCESS_KEY | Required for s3, SECRETS | independent backend credentials | No staging fallback. |
| DIC_PRIVATE_S3_ACCESS_KEY_ID, DIC_PRIVATE_S3_SECRET_ACCESS_KEY | Required for s3, SECRETS | independent private credentials | Editorial/private key independence required. |
| DIC_PORTRAIT_CUTOVER_VERIFIED | Optional, false until approval | false | Fresh empty target inventory acceptance; no demo portrait copying. |
| DIC_FFPROBE_BINARY | Optional | ffprobe | Runtime executable gate; never skip media validation. |
| DIC_PORTAL_ACCOUNTS_ENABLED | Conditional after schema/acceptance | false initially | Existing account rollout checks. |
| DIC_PORTAL_EMAIL_VERIFY_URL, DIC_PORTAL_FRONTEND_URL | Conditional portal delivery | https://dawanaislamicfoundation.org/dic/participant | Existing email verification URL checks. |
| DIC_EMAIL_RECOVERY_ENABLED, DIC_RECOVERY_DELIVERY_WORKER_ENABLED | Conditional, false initially | false | Enable only with approved delivery/scheduler. |
| DIC_RECOVERY_ENCRYPTION_KEY | Conditional SECRET | separately generated Fernet key | Existing encryption validator; back up securely. |
| EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD | Conditional SMTP; password SECRET | approved SMTP endpoint /587 | Existing email configuration; no test SMTP assumed. |
| EMAIL_USE_TLS, EMAIL_USE_SSL, DEFAULT_FROM_EMAIL | Conditional SMTP | true, false, verified sender | Confirm SMTP/provider compatibility. |
| DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS | Optional | 8 | Existing 1–30 second bounds. |
| DIC_FEEDBACK_PRIVACY_KEY | Conditional SECRET | independent 32+ character value | Existing feedback checks. |
| FOUNDATION_DONATIONS_ENABLED | Required policy | false | Must remain disabled; no donations rollout. |

Packaging names PUBLIC_HOST/PORT/GATEWAY_*/EDGE_*/TRUSTED_EDGE_CIDRS configure the
new wrapper, not invented replacements for existing Django variables. Other
optional feature/contact/SMS/WhatsApp/Google settings remain authoritative in
backend/config/settings/base.py; leave unapproved features disabled/unset. Google
credentials remain unset. Registration opening dates are database owner decisions,
not invented environment variables. No registration-opening action is packaged.

## Database, workers, storage and recovery gates

Use a fresh separate PostgreSQL database; never transfer local/demo records or
portraits. Confirm available CI-covered PostgreSQL 14/18, verify-full CA/SAN support,
restricted runtime role and separate migration role. release_migrations still needs
independently approved host/port/name/role/system_identifier, pg_control_system()
inspection privileges, exact manifest hashes and owner approval. Do not bypass if
the provider cannot support it. Migrations/cache table/admin creation are separate
authorized one-off operations using the same image, never startup commands.

Workers are not started inside the web container. Use approved scheduler jobs with
the same image and explicit ENTRYPOINT overrides, bounded batches and DB claims.
For Docker the override is `--entrypoint /opt/venv/bin/python IMAGE manage.py
send_dic_portal_messages --limit 100` (analogous for recovery). A plain command
argument does not override this image's web entrypoint. Verify the provider can
override ENTRYPOINT before selecting its scheduler; otherwise use a reviewed
separate worker image. Never assume the web process is a delivery worker.
Use the existing ops/production/delivery.cron.example only after confirming provider
one-minute scheduling, overlap protection, environment, queue health and alerting.
No production housing worker, automatic R2 cleanup or cutover is added.

R2 network access and authorized retrieval remain runtime acceptance tests. Backups
must cover DB, R2 objects, source/image digest, configuration and independent key
recovery. Verify a separate disposable restore; in-place provider restore alone is
insufficient. Never exercise recovery by overwriting production. Keep keys outside
the image/backups accessible to application users; assign restoration custodians.

## Sizing and controlled launch

Minimum controlled synthetic test candidate: 1 CPU/1GB RAM; recommended initial
production candidate: 2 CPU/2GB RAM plus separately sized paid PostgreSQL. These are
unmeasured starting assumptions, not capacity guarantees. 0.25 CPU/256MB free
instances are not recommended for this combined Python/Nginx/PDF runtime. Builds
need a separate builder with more memory for npm; final runtime excludes Node.
Budget web compute, PostgreSQL, backups/export retention, R2, SMTP, monitoring,
domain renewal, registry storage/pulls and scheduled jobs. No new provider price
or uptime guarantee is asserted here. Printing remains bounded; load tests pending.

1. Owner reviews the GHCR workflow and explicitly approves push/PR and later merge/publication.
2. Run existing nine backend jobs and new container-packaging synthetic workflow.
3. Resolve any build/smoke failures; retain exact image digest, source SHA, package
   inventories and successful job artifacts. Publication is gated on packaging success.
4. Verify provider Docker/image source, multi-process, UID/filesystem, network,
   port, edge headers, termination grace and health-probe protocol.
5. Confirm public GHCR visibility; separately approve hosted tests, deployment and costs.
6. Approve production DB/TLS/roles, R2, secrets, SMTP/scheduling, backup/restore,
   domain/HTTPS and migration manifest. No existing database access here.
7. Controlled browser/security/payment test-mode acceptance, then separate live
   merchant/settlement approval. Keep registration closed and payments test-only.
8. Owner separately approves production deployment and later opening registration.

Rollback selects the previously tested immutable image digest, not a rebuild from
a branch. Check schema compatibility first; image rollback does not undo migrations.
Keep evidence and explicit rollback/restore approval; never auto-restore a database.

## Validation status

Local Node packaging contract checks and eight focused frontend service tests
passed. The complete frontend service suite also ran: 234 passed, zero failed,
skipped or cancelled (21.31 seconds). Git diff --check passed. Docker, Nginx and
Python commands are unavailable in this terminal; image
build, Python tests, production-settings startup, nginx -t, Gunicorn, runtime routes,
readiness, TLS and signals have NOT executed locally. The GHCR workflow changes have not executed in Actions. Verification builds a
local image before publication and tests unavailable-DB readiness (503),
not a successful PostgreSQL connection. Real DB/schema readiness remains a gate.
Byte-for-byte rebuilding and actual Naijacloud ingress remain unverified.

## Packaging completion review

The focused review included all 14 new files as well as .gitattributes. It fixed
traversal permissions on the disposable smoke-test certificate directory (UID
10001 could not traverse mktemp's default 0700 directory), disabled environment
HTTP proxies for the internal loopback health probe, and bounded shutdown waits
at 60 seconds. These changes do not alter production certificate permissions.
Git index.lock was absent; no Git process was visible at inspection. Explicit
deny-write Git metadata ACLs in the Codex sandbox explain the branch-creation
failure. No permissions or locks were changed. Use the ordinary owner terminal
for separately approved exact-path branch publication; never stage all untracked
files. No actual base-image digests have been resolved in this environment.

## GHCR change validation in this workspace

The offline Node packaging contract check passed with the Dockerfile and test
scripts unchanged. Git diff whitespace validation and structural YAML/workflow
checks are recorded in the change report. Docker is not installed in this shell;
Python resolves to an inaccessible interpreter. Full gateway Python tests, image
build and smoke tests must run on the PR in GitHub Actions. No image was published.
Fetch failed because .git/FETCH_HEAD is read-only; direct GitHub Git access is also
unavailable here. The owner-reported PR #1 merge could not be verified locally.
Existing untracked files were preserved; no branch or commit was created.
