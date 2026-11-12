# Production API hostname review

## Cause and implementation

For `DJANGO_SETTINGS_MODULE=config.settings.render`, the supplied configuration
explains the custom-domain HTTP 400: only the existing Render hostname is in
Django's allowed-host list. Render domain verification and certificate issuance
do not update Django settings. No production log or runtime environment was read
in this task; the diagnosis follows the supplied facts and this source path.

- `backend/config/settings/render.py:14` calls `configure(os.environ)` before
  importing production settings. There is no automatic inclusion of Render's
  custom domains or its external hostname.
- `backend/config/native_defaults.py:7` requires PUBLIC_HOST to be one exact
  lowercase hostname, with a dot, no scheme/path/port/wildcard. Before this patch,
  configure unconditionally replaced DJANGO_ALLOWED_HOSTS with that single host.
  An environment value such as DJANGO_ALLOWED_HOSTS=old,new was therefore ignored.
  PUBLIC_HOST=old,new failed startup validation rather than enabling both.
- `backend/config/settings/base.py:32` and
  `backend/config/settings/production.py:15` parse the derived DJANGO_ALLOWED_HOSTS
  as a list. `backend/config/release_security.py:12` requires a nonempty host list
  and rejects wildcards, leading-dot domain patterns and scheme-prefixed values.
  Multiple exact hosts are already supported by this production validator.
- `backend/config/settings/render.py:60` revalidates the final production
  configuration after applying the Render overlay. HTTPS and secure-cookie
  requirements remain mandatory (`release_security.py:22`).
- `backend/config/native_security.py:8` calls request.get_host() before routing,
  including before static responses. Django raises DisallowedHost for the new
  hostname with the old allowlist, producing HTTP 400 before the health view.
  `settings/render.py:22` disables X-Forwarded-Host, and the managed middleware
  discards forwarded identity/host headers. TLS and normal HTTPS forwarding
  requirements remain unchanged.

## Minimal prepared correction

The only runtime change is in `backend/config/native_defaults.py:10`:
PUBLIC_HOST remains a required single hostname; new optional PUBLIC_HOST_ALIASES
adds a comma-separated list of explicitly approved exact hostnames. Each alias
uses the same strict validation as PUBLIC_HOST. Empty entries, schemes, paths,
ports, whitespace, wildcards and leading-dot patterns fail startup. Duplicates
are removed; unrelated DJANGO_ALLOWED_HOSTS overrides remain ignored. With no
aliases, existing behavior is unchanged. No canonical-host redirect is added.

After an explicitly approved deployment containing this patch, use these exact
Render values:

```dotenv
PUBLIC_HOST=dawana-islamic-foundation-web-app-1.onrender.com
PUBLIC_HOST_ALIASES=api.dawanaislamicfoundation.org
```

Only PUBLIC_HOST_ALIASES is a required new variable. Keep the current PUBLIC_HOST.
The resulting effective setting is:

```python
ALLOWED_HOSTS = [
    'dawana-islamic-foundation-web-app-1.onrender.com',
    'api.dawanaislamicfoundation.org',
]
```

Do not manually set DJANGO_ALLOWED_HOSTS to implement this change: configure
derives it. Do not set a wildcard or change the settings module to bypass
configure. Settings are loaded at process startup, so application processes must
reload after an approved environment change. No environment change or restart
was performed here.

**This cannot safely enable both hosts without a code deployment on the current
implementation.** Setting the new alias variable on old code has no effect;
changing PUBLIC_HOST to the custom domain admits only that domain and drops the
Render hostname, potentially breaking existing access/health monitoring. After
the alias patch has been deployed once, future exact alias changes require an
environment update/process reload rather than another source change.

## CSRF, CORS, cookies and related settings

- FRONTEND_ORIGIN identifies the browser frontend, not the backend API. For the
  canonical production website it should remain
  `https://dawanaislamicfoundation.org` (no trailing slash). If it already has
  that value, no update is needed. Its actual current value was not supplied.
  Do not change it to the API hostname merely to fix the health endpoint.
- `backend/config/native_defaults.py:31` derives both
  DJANGO_CSRF_TRUSTED_ORIGINS and DJANGO_CORS_ALLOWED_ORIGINS exclusively from
  FRONTEND_ORIGIN. Adding an API target hostname to ALLOWED_HOSTS does not require
  adding that hostname to these browser-origin allowlists. For the canonical
  frontend, both effective lists remain
  `['https://dawanaislamicfoundation.org']`. Credentialed CORS stays enabled;
  wildcard and regex origins stay disabled. Requests from an unapproved www or
  preview origin remain rejected. Admin same-origin CSRF checks work on either
  allowed backend hostname without cross-trusting the two backend origins.
- `backend/config/settings/production.py:18` retains HTTPS redirect and Secure
  session/CSRF cookies. `settings/base.py:44` retains HttpOnly/Lax sessions;
  Django's CSRF SameSite default is Lax. `settings/render.py:28` retains host-only
  cookie domains. No cookie-domain sharing, SameSite=None, proxy-header, HSTS or
  TLS change is required. Each hostname gets separate cookies/sessions: signing
  in or preparing a payment-return grant on the Render hostname does not transfer
  that session/grant to the custom hostname. Re-establish authority on the chosen
  API hostname using the existing authenticated flow.
- Browser use of the custom API separately requires a frontend build using
  `VITE_API_BASE_URL=https://api.dawanaislamicfoundation.org/api/v1`. This is not
  needed to fix the custom health URL. It is a build-time frontend value, so an
  owner-approved frontend rebuild/deployment is needed if the existing bundle
  still calls Render. Do not alternate API hosts during a session/payment return.
- No production credential, payment variable, callback, webhook, feature flag,
  database record or DNS change is part of this hostname correction.

## Changed files and tests

- `backend/config/native_defaults.py`: optional validated hostname aliases.
- `backend/render.env.example`: documents the optional migration variable.
- `backend/config/test_public_hosts.py`: five database-free regressions for the
  current single-host behavior, exact aliases, invalid inputs, real middleware
  health routing for both domains, rejection of unrelated/spoofed hosts, unchanged
  origin/payment values and production-validator acceptance.
- `backend/config/test_render_deployment.py`: extends real Render settings/WSGI
  startup regressions to assert both allowed hosts, unchanged exact CORS/CSRF
  origin, HTTPS, Lax host-only secure cookies and foreign-host rejection.
- `scripts/test_production_policies.py`: includes PublicHostTests in the default
  database-free CI policy suite. Existing GitHub Actions core discovery includes
  the new full Render settings regression; no extra workflow is needed.
- `PRODUCTION_HOSTNAME_REVIEW.md`: this review.

Executed: **26 tests passed, no failures/skips**: PublicHostTests (5), existing
OperationsSecurityTests (6), and ReleaseReadinessTests (15). Both health hosts
return HTTP 200 with `{"status":"ok"}` using the actual managed/security
middleware and a mocked database probe; unapproved hosts return HTTP 400, and
HTTP requests still redirect to HTTPS. CSRF/cookie/CORS and production-security
policy regressions also pass. The existing policy runner forbids real database
and network connections and does not read dotenv. As in the earlier reviews,
tests used bundled Python 3.12 with workspace site-packages appended, without
changing the virtualenv. AST parsing passed for all four changed Python files;
`git diff --check` passed.

Not executed: the subprocess-based full Render settings regression, GitHub Actions
or live production hostname acceptance. The full startup regression is prepared
for CI's normal installed Python environment; the available local interpreter
does not independently contain the backend dependencies. No production request,
deployment, merge, environment update, restart or DNS action was performed.

All pre-existing uncommitted changes, including the earlier Operations and
payment reviews, were retained. After owner approval and successful CI, validate
both exact HTTPS `/api/v1/health/` URLs following the code/environment rollout,
then check frontend-origin CORS and CSRF/cookie persistence on the custom API.
