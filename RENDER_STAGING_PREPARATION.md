# Render staging preparation

Status: prepared locally, not deployed. Cloud resources, application database migrations, accounts and messages were not created.

## Render configuration

| Setting | Exact value |
| --- | --- |
| Root directory | Leave blank: repository root |
| Python | `3.13.14` via `PYTHON_VERSION` |
| Build | `bash backend/render-build.sh` |
| Pre-deploy | `bash backend/render-migrate.sh` after confirming the NEW staging database |
| Start | `bash backend/render-start.sh` |
| Health check | `/api/v1/health/` |
| Auto-deploy | Off; deploy only a reviewed staging branch/commit after approval |

Repository root is required because Django Admin consumes existing sibling `dawana-platform/public` assets. Render excludes files outside a configured service root. Build installs dependencies, runs deployment checks and collectstatic. Migrations are deliberately separate from builds and worker startup. Gunicorn uses the existing WSGI app, one gthread worker and four threads; Render supplies PORT. Scripts require the staging settings module and preserve LF endings.

## Environment variables

Use `backend/staging.env.example`; never upload local `.env` or reuse development credentials.

- `DJANGO_SETTINGS_MODULE=config.settings.staging`
- `DJANGO_SECRET_KEY`: unique generated secret, at least 50 characters.
- `DJANGO_DEBUG=False` (also forced false by staging).
- `DJANGO_ALLOWED_HOSTS`: exact Render hostname, plus approved backend custom hosts if needed; no schemes/wildcards.
- `DJANGO_CORS_ALLOWED_ORIGINS` and `DJANGO_CSRF_TRUSTED_ORIGINS`: exact staging frontend HTTPS origin, no trailing slash.
- `DATABASE_URL`: secret internal PostgreSQL URL of the NEW staging database.
- `STAGING_DATABASE_NAME`: exact database name from that URL; mismatches prevent startup.
- `DB_CONN_MAX_AGE=60`, `PYTHON_VERSION=3.13.14`.
- `PAYSTACK_MODE=test`; `PAYSTACK_SECRET_KEY` empty until approved sandbox testing, then only an `sk_test_` key. Never put this secret in Vite variables.
- `PAYSTACK_CALLBACK_URL=https://<staging-frontend>/dic/register/checkout`.
- `STAGING_EMAIL_ENABLED=False` initially; `DIC_OFFICIAL_LOGO_URL` empty until approved original asset is supplied.

Optional OTP sandbox only: `STAGING_EMAIL_HOST`, `STAGING_EMAIL_PORT=587`, `STAGING_EMAIL_USER`, `STAGING_EMAIL_PASSWORD`, `STAGING_EMAIL_RECIPIENTS`, `DIC_RECOVERY_ENCRYPTION_KEY`, then `STAGING_EMAIL_ENABLED=True`. Use a dedicated SMTP capture sink. Recipients must be explicit synthetic `.test` addresses. The mail backend checks all recipients including BCC before SMTP. SMS/WhatsApp remain forcibly disabled. Codes are never displayed/logged. No real operational contact should be loaded into staging.

DB_* remains the established local fallback. Do not supply it alongside DATABASE_URL on Render. DB_TEST_NAME is for isolated tests only, must start `test_`, and must differ from the application database. Do not run Django tests against the staging application DB.

## PostgreSQL and migration strategy

After approval, provision a NEW paid Render PostgreSQL instance in the same region as the web service. Free PostgreSQL expires and does not meet persistent staging requirements. Agree backup/restore ownership and access. Use its internal URL; staging enforces PostgreSQL and TLS. Never reuse the development/application DB URL.

Review `migrate --plan` and the target database without printing credentials. The approved pre-deploy command runs migrate, createcachetable and migrate --check. If the chosen service tier lacks pre-deploy support, use an approved one-off job/shell before traffic; do not move migration into every worker startup. The cache table provides shared PostgreSQL-backed DRF throttling.

Reviewed accounts and DIC migrations 0001-0015, including recovery-scope preservation and price-revision backfills. Empty-table backfills are safe on a new DB. 0014 adds portal/ID tables and PostgreSQL triggers; 0015 adds integrity guards and rejects existing mismatches without rewriting history. Neither migration was edited. PostgreSQL locking, trigger SQL and regex operations are intentional; SQLite is not supported.

Fresh migration rehearsal PASSED: all 15 DIC migrations plus Django/accounts migrations applied in an empty isolated schema in the separate TEST PostgreSQL database. Four custom triggers were present; portal tables were empty; database cache add/get succeeded. The complete schema/transaction was rolled back. Application DB was not migrated or reset. This does not replace a Render restore/provisioning rehearsal.

After separate approval, provision isolated staging accounts and synthetic registration configuration. Existing setup_dic_2026 creates a draft listing only. Fees/dates/categories and opening synthetic registration require explicit staging-only configuration. No live registration state was changed.

## Separate Netlify staging frontend

Leave live Netlify main settings/build untouched. Create a NEW site after approval, using a reviewed staging branch/commit:

- Base: `dawana-platform`; install `npm ci`; build `npm run build:staging`; publish `dist`.
- `DAWANA_STAGING_FRONTEND=true`.
- `DAWANA_STAGING_SITE_ID=<new site ID>`; build requires this to match Netlify's SITE_ID.
- `STAGING_BACKEND_ORIGIN=https://<approved-backend>.onrender.com`.
- `VITE_API_BASE_URL=/api/v1`.

The opt-in build writes API/Admin/static proxy rewrites before SPA fallback in generated dist/_redirects. Existing source public/_redirects and normal build remain unchanged. Verified a staging build generates all three rules, then a normal build restores SPA-only output.

Same-origin proxy paths preserve Django session/CSRF and participant cookie paths without weakening SameSite=Lax or adding cookie-domain overrides. Direct cross-site Netlify-to-Render API URLs alone are not accepted for cookie-auth testing. Configure the exact staging frontend origin in BOTH CORS and CSRF lists. Verify proxy Host/Origin/Referer, Set-Cookie paths, redirects and no-store behavior in real staging. Direct Render Admin and proxied Admin have separate host cookies; use one origin consistently for shared-session tests.

## Security review

Staging inherits production HTTPS redirects, secure HttpOnly/Lax cookies, HSTS, CSRF, host validation and frame protection. Only staging trusts Render's forwarded HTTPS header; verify edge sanitization. USE_X_FORWARDED_HOST remains false. Existing Operations/participant permissions and OTP/session logic are unchanged.

Existing Paystack code rejects live keys/mode. HMAC-SHA512 raw-body webhook authentication and independent provider verification remain intact. Approved test webhook URL: `https://<backend>/api/v1/dic/payments/paystack/webhook/`. No provider call was made.

Shared DB cache replaces process-local DRF cache in staging. NUM_PROXIES=1 assumes Render's direct edge; verify the actual chain through Netlify. Recovery request buckets still use REMOTE_ADDR and may group proxied visitors. Validate deployment IP behavior rather than trusting arbitrary forwarded IP headers or weakening limits.

Health returns only generic ok/unavailable (200/503), performs SELECT 1 and sets no-store. Gunicorn access logs are disabled; staging Django request/security logs omit paths, payloads and exception details. Configure upstream Render/Netlify log access/retention separately.

Optional approved jobs: `cd backend && python manage.py send_dic_portal_messages --limit 50` and `cd backend && python manage.py cleanup_dic_participant_access --limit 500`, with identical staging env. Uncertain OTP claims must never be manually requeued. No workers/cron resources created.

## Validation

- Focused configuration/health tests: 10 passed in 14.843 seconds before final full run.
- Complete Django suite: **186 tests passed in 379.290 seconds** using the separate PostgreSQL test database. Expected mocked recovery-delivery warning only; no failures.
- Frontend: 28 tests passed; lint, production build and opt-in staging build passed.
- Fresh PostgreSQL migration/cache rehearsal passed and rolled back.
- Final staging deployment checks passed with zero issues, including the database-name guard.
- Django migration drift/history checks passed; existing application 0015 remains unapplied. Final diff check passed.
- Bash syntax checks passed for all three scripts.
- Dependency installation BLOCKED by network socket restrictions. Gunicorn/WhiteNoise versions verified against PyPI, but installation failed. collectstatic dry-run FAILED because WhiteNoise is unavailable. Linux clean dependency installation, static serving and Gunicorn startup remain unverified. No fallback or stubs bypassed the failure.
- Real browser/proxy/cookie, sandbox payment/OTP, physical print and cloud persistence acceptance remain pending.

## Files inspected and commit scope

Inspected base/development/production settings, WSGI/ASGI, requirements/env examples, root/DIC/health routes, all migrations, OTP/session/worker/payment security code, Admin templates/static assets, frontend APIs/Vite/redirects, architecture/implementation/audit/remediation documents and tests.

Modified for staging: `backend/config/settings/base.py`, `backend/requirements.txt`, `backend/health/views.py`, `backend/health/tests.py`, `dawana-platform/package.json`.

Added: `.gitattributes`; `backend/config/settings/staging.py`; `backend/config/staging_email.py`, `staging_logging.py`, `tests.py`; `backend/constraints-staging.txt`; `backend/gunicorn.conf.py`; `backend/render-build.sh`, `render-start.sh`, `render-migrate.sh`; `backend/staging.env.example`; `dawana-platform/scripts/build-staging.mjs`, `staging-config.mjs`; `dawana-platform/src/services/stagingConfig.test.js`; `dawana-platform/staging.env.example`; this report.

Future commit scope: ONLY the above staging files; hunk-stage base.py because it already contains 1L-A changes. Never git add all: exclude .env, credentials, .vscode/settings.json, generated dist/staticfiles/reports, acceptance artifacts and unrelated appearance work. Separately review/checkpoint existing 1L-A/remediation files and migrations 0014/0015 before choosing a deployment commit; currently untracked prerequisites are not included by a deployment-only commit. Avoid pushing main because it triggers the live Netlify site.

Remaining blockers: Linux dependency/static/Gunicorn validation; approved separate resources/domains; prerequisite 1L-A checkpoint; sandbox provider credentials and synthetic configuration; staff provisioning approval; proxy/IP/cookie/browser acceptance; official logo/print acceptance; backup/restore readiness. No commit, push, cloud creation, application migration or deployment performed. Await approval.

References: [Render Django](https://render.com/docs/deploy-django), [monorepos](https://render.com/docs/monorepo-support), [deploys](https://render.com/docs/deploys), [free limits](https://render.com/docs/free), [health checks](https://render.com/docs/health-checks), [Netlify proxies](https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/).
