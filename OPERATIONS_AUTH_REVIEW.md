# Operations authentication and Admin navigation review

## Findings and evidence

1. **Confirmed navigation defect, corrected in source.**
   `backend/dic/templates/admin/base_site.html:12` used `href="/dic/operations"`.
   An Admin page hosted on Render therefore opens the Render origin, where the
   API-only deployment has no frontend route. The link now uses the existing
   `public_site_url` context plus `dic/operations`. With
   `FRONTEND_ORIGIN=https://dawanaislamicfoundation.org`, it opens exactly
   `https://dawanaislamicfoundation.org/dic/operations`.
   `backend/config/site_context.py:6` validates that configured origin; no request
   Host header is used to construct the public URL. The existing Operations
   permission condition is preserved. The relative fallback remains suitable
   for a same-origin installation.

2. **CSRF rejection is confirmed by the incident report; its exact live rejection
   reason is not established by this workspace.**
   `dawana-platform/src/services/operationsApi.js:6` selects the API from the
   build-time `VITE_API_BASE_URL`, defaulting to `/api/v1`.
   Lines 62–67 fetch the JSON CSRF token with credentials and no caching.
   Lines 76–84 bootstrap before login and refresh after Django rotates the token.
   Lines 36–46 attach `X-CSRFToken` and include credentials on mutations.
   There is no missing credentials/header defect in this source flow.

   `backend/dic/operations_api.py:446` applies `ensure_csrf_cookie`; line 449
   calls `get_token`, and line 450 forbids caching. Django's CSRF response
   middleware writes the cookie. New middleware-level tests establish that the
   endpoint emits a Secure, host-only, path `/`, SameSite=Lax cookie and that
   the corresponding masked JSON token passes CSRF validation. They also
   reproduce HTTP 403 when the cookie is absent despite a valid JSON token.
   A JSON token alone does not establish browser cookie acceptance or replay.

   `backend/dic/operations_api.py:460` explicitly protects login with CSRF even
   before authentication. Lines 484–495 retain active-user/Operations-permission
   checks and Django session login. No authentication or permission code was
   changed.

3. **Cross-site hosting is incompatible with the existing Lax cookie policy.**
   `backend/config/settings/base.py:45` sets session SameSite=Lax; Django's
   CSRF cookie default is also Lax. `backend/config/settings/render.py:28`
   keeps both cookie domains host-only. `backend/config/settings/production.py:18`
   requires HTTPS redirects and Secure cookies.
   If the deployed frontend calls an `onrender.com` API directly from
   `dawanaislamicfoundation.org`, these are different sites: browsers do not
   send Lax cookies on those cross-site fetches. Adding `credentials: include`
   or trusting the frontend origin cannot override SameSite or third-party
   cookie blocking. This explains a missing-cookie 403 under that arrangement,
   but the actual deployed API base and browser rejection reason were not
   independently observable here. The public HTTPS connectivity probe failed.

   A second distinguishable cause is a mismatched Origin:
   `backend/config/native_defaults.py:25` derives exact host, CSRF and CORS lists
   from PUBLIC_HOST and FRONTEND_ORIGIN, replacing older DJANGO_* overrides.
   For example, a www frontend origin is different from the configured bare
   domain. `backend/config/settings/base.py:41` allows credentialed CORS while
   disabling wildcard and regex origins. Token/cookie mismatches, including
   stale tokens after login, are independently rejected as well.

## Smallest secure correction and owner-controlled configuration

The only runtime source correction is the Admin link. Keep CSRF enforcement,
Secure/HttpOnly session cookies, host-only cookie scope, Lax SameSite, HTTPS,
exact origin validation and existing permissions.

The existing `backend/render.env.example:4` and
`dawana-platform/.env.production.example:5` already describe the appropriate
same-site API arrangement. If production still uses a cross-site Render API,
the proposed configuration correction requires owner approval:

- Provision/verify `api.dawanaislamicfoundation.org` as the Render custom domain,
  with the required DNS and valid HTTPS certificate. Review Cloudflare proxy
  and ingress behavior with the owner before making any change.
- Set Render PUBLIC_HOST to `api.dawanaislamicfoundation.org` and FRONTEND_ORIGIN
  to `https://dawanaislamicfoundation.org` with no path or trailing slash.
  Confirm `config.settings.render` is actually selected. It derives the exact
  Django allowed host and CORS/CSRF origin; separately changing the derived
  DJANGO_* variables will not override configure().
- Set the frontend build's public VITE_API_BASE_URL to
  `https://api.dawanaislamicfoundation.org/api/v1`, then approve its rebuild and
  deployment. Changing a runtime variable alone does not update an existing
  Vite bundle. Use the approved canonical bare frontend domain.
- Alternatively, an owner-approved same-origin `/api/v1` gateway can preserve
  Lax cookies, but requires its own reviewed proxy configuration. This change
  does not introduce a gateway or weaken cookies to SameSite=None.

Before deciding which setting to change, collect the deployed API base,
request Origin/Host and a sanitized CSRF rejection reason (cookie missing,
incorrect token or untrusted origin). Do not collect credentials, cookie
values or token values. In browser developer tools, verify that `/csrf/`
receives Set-Cookie without a blocked-cookie reason, and that login sends the
cookie plus X-CSRFToken. Verify successful login rotates CSRF, sets a Secure
HttpOnly session cookie, `/me/` succeeds, and protected logout succeeds with
the refreshed token. Confirm an untrusted origin and missing cookie still
fail. Server test clients do not simulate browser SameSite enforcement.

No deployment, merge, DNS, Cloudflare, Render configuration, credential or
production database change was performed. Existing uncommitted files were
left intact.

## Changed files and validation

- `backend/dic/templates/admin/base_site.html`: validated frontend navigation.
- `backend/config/test_operations_security.py`: six database-free regressions
  for cookie attributes, trusted cross-origin CSRF, missing cookies, bad/missing
  tokens, foreign origins/preflight, and permission-gated Admin navigation.
- `backend/config/test_native_deployment.py`: extend real PostgreSQL session
  tests for CSRF rotation/stale-token rejection, missing cookies and staff
  without Operations permission.
- `dawana-platform/src/services/operationsApi.test.js`: bootstrap failure and
  CSRF rejection/no credential retry, alongside existing cookie/header,
  refresh and logout tests.
- `scripts/test_production_policies.py`: include the six new database-free tests
  in the default CI policy suite.
- `.github/workflows/backend-acceptance.yml`: add frontend authentication tests;
  existing core discovery includes the extended PostgreSQL tests on versions
  14 and 18. No production services or secrets are used by these jobs.
- `OPERATIONS_AUTH_REVIEW.md`: this report and proposed owner approval scope.

Executed locally:

- Frontend Operations authentication: **5 passed**, no failures/skips.
  Command: `node --test dawana-platform/src/services/operationsApi.test.js`.
- Database-free backend: **27 passed**, no failures/skips, comprising
  OperationsSecurityTests (6), RenderConfigurationTests (6), and
  ReleaseReadinessTests (15). The policy runner forbids database connections
  and outbound network access and does not load dotenv.
- AST syntax parsing: **3 changed Python files passed**.
- `git diff --check`: **passed**.

The workspace Python 3.13 interpreter is inaccessible. The backend policy
tests ran with the available bundled Python 3.12 runtime, appending
`backend/.venv/Lib/site-packages` to its import path (so compatible bundled
binary packages take precedence), then invoking the existing policy runner
through runpy with the three explicit class labels. No dependencies were
installed or workspace virtualenv files altered.

Not executed: PostgreSQL integration tests (prepared for guarded, disposable
GitHub Actions databases); GitHub Actions itself; deployed browser session
acceptance. Production login is **not claimed fixed or validated** until the
live cookie/origin evidence and approved hosting correction are completed.
