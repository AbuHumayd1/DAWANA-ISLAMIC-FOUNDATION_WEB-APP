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

After verifying the intended database identity and taking an approved backup,
run these inspection commands from `backend` with Render settings selected:

```sh
python manage.py check --deploy
python manage.py showmigrations --plan
python manage.py migrate --plan
python manage.py createcachetable dawana_release_cache --dry-run
```

Review the exact migration and cache-table plans. Only after separate approval,
on the verified target, apply:

```sh
python manage.py migrate --noinput
python manage.py createcachetable dawana_release_cache
```

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
