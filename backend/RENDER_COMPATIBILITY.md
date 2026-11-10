# Render backend configuration

Use repository-root commands:

* Build: `bash backend/native-install.sh && bash backend/native-build.sh`
* Start: `bash backend/native-start.sh web`
* Settings: `DJANGO_SETTINGS_MODULE=config.settings.render`
* Web-process probe: `/api/v1/health/web/` (no external dependencies).
* Database probe: `/api/v1/health/` (`SELECT 1`; worker/delivery independent on Render).

If Render's Root Directory is `backend`, use `bash native-install.sh && bash
native-build.sh` and `bash native-start.sh web` instead. The start script selects
Render settings when Render supplies `RENDER=true`. Other native hosts retain
their current default. The existing native Gunicorn configuration binds to
`0.0.0.0:$PORT`; no Gunicorn change is required.

Required environment: `DATABASE_URL`, `DJANGO_SECRET_KEY` (at least 50 characters,
independently generated), `FRONTEND_ORIGIN` (one HTTPS origin, no trailing slash),
`PUBLIC_HOST` (exact backend hostname), `DJANGO_SETTINGS_MODULE` as above, and
`PYTHON_VERSION` matching the supported 3.12/3.13 runtime. Render supplies `PORT`.
Worker actor, encryption key and delivery credentials are not web-startup inputs.
Existing delivery and actor validation still apply when running a worker.

## Database transport

Use the **external PostgreSQL URL with its full hostname**, not an IP or short
internal hostname. Render documents internal self-signed endpoints as incompatible
with `verify-full`: https://render.com/docs/postgresql-creating-connecting

TLS remains `verify-full`; no unencrypted or unauthenticated fallback is permitted.
Render settings supply the OS CA bundle to libpq, which otherwise normally looks
for `~/.postgresql/root.crt`. `DB_SSLROOTCERT` may specify an existing trusted PEM
CA bundle if the system default is unsuitable. Do not use the server leaf
certificate as an unreviewed trust anchor. If the external endpoint's chain or
hostname cannot be verified, stop and obtain the provider-supported certificate
chain/endpoint. Keep external access restricted to approved service egress.

The build only installs dependencies, verifies existing runtime prerequisites
(including Liberation fonts and ffprobe), and collects static assets using
`config.settings.build`. It does not import production settings, connect to the
database, create cache tables, or apply migrations. Missing runtime packages are
build blockers, not a reason to skip media validation.

## Separately approved schema procedure (not part of build/start)

Use the guarded release command with explicit Render settings. Set the five
RELEASE_DATABASE_* identity variables required by render-migrate.sh from an
independently verified database, hostname, port, migration role and cluster ID.
The wrapper is inspection-only: pending migrations deliberately produce a
nonzero exit and cannot apply themselves. Run it only after owner approval for
production inspection; it must not be a build/start/pre-deploy application hook.

The direct planning command (from backend, placeholders replaced privately) is:

```sh
python manage.py release_migrations --settings=config.settings.render --database-name <approved-database> --hostname <approved-host> --port <approved-port> --role <approved-role> --cluster-id <verified-cluster-id> --manifest-file <new-plan-file>
```

The planning command reads the database and writes a new local manifest; it does
not apply schema. Do not use placeholders literally or bypass target binding if
pg_control_system() is unavailable. Obtain an approved identity-verification
alternative before proceeding. Review exact migration hashes, dependencies,
backup/restore evidence and rollback decision. Only a separately approved
invocation using --approval-file and --apply-approved-plan can apply that exact
manifest. Cache-table planning/creation is a separate approval gate; review
createcachetable dawana_release_cache --dry-run before authorizing creation.
Do not substitute a raw migrate command for this approval procedure.

The shared database cache is retained for production throttling. The database
probe tests connectivity only; it does not claim that application migrations or
the cache table exist. The web probe only indicates that the web process serves
requests. Verify schema, protected routes and cache readiness separately before
opening application traffic. No schema operation is executed by this repair.

## Diagnosing the reported 500

Confirmed from source: the old native settings enable worker readiness, the old
deployed routes lack the web probe, and libpq is not explicitly given the system
CA bundle. Normal database/OS errors are already caught in the original health
view and should return 503. These facts alone do **not** prove the reported 500's
cause. A redacted Render traceback is still needed to distinguish a middleware
or configuration error from a dependency failure or deployed-source mismatch.

Health probes now catch configuration and unexpected dependency exceptions,
return generic 503 responses and log only exception types, never exception text,
request payloads, credentials or connection URLs. Middleware still enforces
HTTPS, exact allowed hosts, CSRF, session security and existing authorization.
Render's Django request-error filter also retains exception types and the last
eight code locations (file basename, line and function). Exception messages,
source lines, absolute paths and local variables are omitted. This allows a
future deployed 500 to be traced without exposing its sensitive data.
