# Phase 3 authentication completion — source delivery

Current email/password behavior and acceptance instructions supersede the public Google-login steps below: see `DIC_2026_PHASE3_EMAIL_PASSWORD_ACCEPTANCE.md`.

Status: source implementation prepared; **not database-accepted, deployed, or Google-accepted**. The seven-phase roadmap is unchanged. No database was accessed, migrated, seeded, reset, or deleted during this work. Retained tutor evidence and receipts must remain untouched.

## Implementation and boundaries

- Credentials use the existing `accounts.User`, Django password hashing/validators, and a 12–128 character password policy. No default credentials, staff flags, Django staff sessions, or automatic Google email matching.
- A booking-contact OTP session no older than ten minutes can activate an account, reset its password, or explicitly link Google. A password/Google session cannot serve as that recovery proof. Optional login email must match the just-verified **email** contact. A phone-managed guardian can choose a username without supplying email.
- Persistent authorization is an explicit account-to-booking binding. Additional bookings require separate booking OTP proof plus the existing account password and the same verified contact/channel. No bulk association by email, housing guardian relationship, participant ID, or Google claims. Switching children within an authorized booking reuses the existing camper selector and guardian checks.
- Returning login issues the existing participant cookie/grant/scopes. Every account scope is intersected with active bindings, unchanged primary contact, and the existing paid/tutor eligibility service. Cancelled, refunded, revoked tutor, restricted, or ambiguous-source registrations do not become eligible through credentials.
- Existing default 30-minute expiry, explicit personal-device persistence (maximum eight hours), fixed expiry, CSRF, HTTP-only/SameSite cookie, logout and cross-tab clearing remain in use. Password reset and Google unlink increment credential version and revoke account sessions. Reset racing with login fails closed. Disabled/staff/superuser accounts cannot use participant credentials.
- Google uses authorization code + state + browser binding + nonce + S256 PKCE, ten-minute single-use attempts, server-encrypted verifier, fixed redirect destinations, and server token exchange. `google-auth` validates signed ID tokens, issuer, audience and token times; additional checks enforce nonce, verified-email claim, authorized party and stable `sub`. Google email does not determine identity or access. Revoked subjects are retained and cannot be reassigned to conflicting accounts; changing to a different Google subject is deliberately unsupported without a reviewed recovery policy.
- Existing tutor housing/competition exclusions, paid settlement, Paystack, digital IDs, class-pending display and future-module placeholders are unchanged. No later-phase feature was activated.
- New account features default **off**. Existing OTP remains available without querying the new tables. Account credentials use a distinct token prefix; disabling the feature rejects those cookies rather than treating them as ordinary OTP sessions. When enabled, account endpoints require all five new tables and fail closed if setup is missing. Do not enable before schema acceptance.

## Files in this delivery

Backend additions: `backend/dic/portal_account_models.py`, `portal_accounts.py`, `portal_account_api.py`, `portal_google.py`, `portal_auth_logging.py`, `test_portal_accounts.py`, and `backend/dic/migrations/0030_portal_account_authentication.py`.

Backend connections: `backend/dic/models.py`, `participant_api.py`, `portal_phase3.py`, `urls.py`, `apps.py`, `backend/config/settings/base.py`, `backend/requirements.txt`.

Frontend additions: `dawana-platform/src/components/dic/PortalAccountAccess.jsx`, `src/services/portalAccount.js`, `src/services/portalAccount.test.js`.

Frontend connections: `src/pages/ParticipantPortal.jsx`, `src/components/dic/PortalPhase3.jsx`, `PortalPhase3.css`. Validation: `scripts/validate_dic_phase3_policy.py` and this document. Unrelated pre-existing working-tree changes are not part of this delivery.

## API routes

All below use `/api/v1/dic/participant/`; POST requests retain the existing CSRF-token fetch and cookie protections.

| Method / suffix | Purpose |
| --- | --- |
| GET `auth/capabilities/` | Feature availability, no credentials or provider secrets |
| GET `auth/account/` | Current verified account/setup state |
| POST `auth/account/activate/` | Fresh OTP + chosen username/password/optional verified email |
| POST `auth/account/link-booking/` | Fresh OTP + existing credentials, explicit same-contact binding |
| POST `auth/password/login/` | Identifier/password + optional `remember_device` |
| POST `auth/password/reset/` | Fresh OTP; only `password`, no caller-selected target identity |
| POST `auth/google/start/` | `intent=login` or fresh-OTP `intent=link`; optional persistence |
| GET `auth/google/callback/` | Provider code callback, single-use state/browser proof |
| POST `auth/google/unlink/` | Fresh OTP; usable password required; session revocation |

## Source-only migration plan

Prepared ordering: `0026 → 0028 → 0029 → 0030_portal_account_authentication → deferred 0027`.

0030 depends on 0029 and the swappable Django user model and declares `run_before` 0027. It creates `PortalAccount`, `PortalAccountBooking`, `PortalAccountSession`, `PortalGoogleLink`, and `PortalOAuthAttempt`. Historical migrations were not edited. The database-free runner checks the explicit 0030 dependency closure excludes 0027, no graph conflicts, and matching states for these five models. **That runner has not executed successfully here because Python cannot start.** Static source review is not a verified migration graph.

No migration execution is authorized in this delivery. After separate approval, provision a **new** isolated Phase 3 database with a dedicated restricted role and its own receipt; review the exact explicit 0030 plan before applying. Never run ordinary `migrate`, the existing unrestricted `backend/render-migrate.sh`, or apply 0027. Existing Phase 2 schema guards/receipts target 0029 and do not authorize 0030; do not repurpose the retained tutor database or edit its evidence. Legacy databases with 0027 already applied are unsuitable for this demonstration.

## Google Cloud Console setup (project owner)

1. Select the approved Google Cloud project. Open **Google Auth Platform** (or APIs & Services → OAuth consent screen). Configure branding, support contact, audience and authorized domains. Keep the app in Testing for the isolated demo and add only approved real Google test accounts.
2. Request only `openid` and `email`. No Contacts, Drive, offline access or refresh token is needed.
3. Create an OAuth client of type **Web application**. For the local demo, use authorized JavaScript origin `http://127.0.0.1:5173` and the exact authorized redirect URI below. Do not mix `localhost` and `127.0.0.1` during a flow.
4. Copy the client ID and secret into backend environment variables only. Never use `VITE_` variables for either secret or OAuth token, commit credentials, or paste them into test logs.
5. Production requires a separately approved client/consent configuration, HTTPS canonical origin, exact HTTPS callback, secure cookies, proxy/header review and acceptance. Replace the entire origin with the actual approved host; no production host is assumed here.

```powershell
# Backend terminal — set only after approval for the NEW isolated environment.
$env:DIC_PORTAL_ACCOUNTS_ENABLED = 'True'
$env:DIC_GOOGLE_CLIENT_ID = '<Web application client ID>'
$env:DIC_GOOGLE_CLIENT_SECRET = '<server-only client secret>'
$env:DIC_GOOGLE_REDIRECT_URI = 'http://127.0.0.1:5173/api/v1/dic/participant/auth/google/callback/'
$env:DIC_PORTAL_FRONTEND_URL = 'http://127.0.0.1:5173/dic/participant'
$env:DJANGO_CSRF_TRUSTED_ORIGINS = 'http://127.0.0.1:5173'
```

Leave `DIC_PORTAL_ACCOUNTS_ENABLED=False` in unapproved/current environments. With credentials absent or the provider library unavailable, Google stays disabled and the UI explains why. Install the updated backend requirements in the approved local virtual environment before enabling. Production configuration must use `DEBUG=False`, HTTPS, `SESSION_COOKIE_SECURE=True`, secure CSRF cookie and request-log redaction at the reverse proxy/access logger. Django callback logs are redacted by this change; upstream logs must also omit callback query strings. Google tokens and authorization codes are never returned to the SPA or retained as account identity.

Provider references: [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect), [Google ID-token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token), [google-auth verifier](https://googleapis.dev/python/google-auth/latest/reference/google.oauth2.id_token.html).

## Checks safe to run now (no database)

From the repository root:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\validate_dic_phase3_policy.py
```

Expected: zero system-check issues; explicit 0030 graph excludes 0027; all five model/migration states agree; **53 database-free tests**, no failures/errors/skips (including callback and token-exchange diagnostic regressions). The wrapper selects an unused synthetic database name and blocks database connections and external side effects. It does not create that database or execute migrations. Here it was blocked before Django startup: the virtual environment's Python 3.13 executable reports Access is denied. The installed `py -3.13` launcher is also blocked. Backend static checks, graph and policy tests therefore remain unverified.

```powershell
Set-Location .\dawana-platform
node --test --test-reporter=spec src/services/portalAccount.test.js src/services/portalPhase3.test.js src/services/participantApi.test.js src/services/participantSession.test.js src/services/participantThrottle.test.js src/services/camperExperience.test.js src/services/camperDashboard.test.js src/services/tutorRegistration.test.js src/services/paymentReturnApi.test.js
npm.cmd run lint -- src/components/dic/PortalAccountAccess.jsx src/components/dic/PortalPhase3.jsx src/pages/ParticipantPortal.jsx src/services/portalAccount.js src/services/portalAccount.test.js
npm.cmd run build
```

`npm.cmd` avoids the local PowerShell execution-policy block on `npm.ps1`. Combined frontend tests: **65 passed, zero failures/skips** (7 new + 58 existing). Focused lint passed with no findings after correction; build passed with the existing large-chunk advisory. Re-run the combined command after any follow-up changes.

## Working demonstration — requires isolated approval first

1. Repair local Python access; run the database-free command above. Review 0030 and obtain explicit permission for a **new** isolated database, controlled synthetic fixture preparation and writing integration/browser tests. No working demo is claimed until that succeeds.
2. Configure a dedicated PostgreSQL role limited to that database. Explicitly clear `DATABASE_URL` so a pre-existing `.env` URL cannot override the isolated `DB_NAME`. Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, loopback `DB_HOST`, `DB_PORT`, and a distinct `test_...` `DB_TEST_NAME` for the approved environment. Do not use the retained tutor database. Keep Paystack in test mode, real outgoing providers disabled except separately approved test-contact OTP delivery, and migrations explicitly targeted/reviewed.
3. Prepare synthetic paid-eligible registration evidence through the existing approved isolated settlement test helpers (never fake production settlement), a two-child guardian booking, a foreign booking, and a separately authorized synthetic tutor using existing Phase 2 test helpers. Do not create demo fixtures in live databases. Existing OTP mail delivery needs the approved worker/test inbox configuration; no code is printed by the portal.
4. In an isolated backend terminal configured as above, from repository root:

   ```powershell
   & .\backend\.venv\Scripts\python.exe .\backend\manage.py runserver 127.0.0.1:8000 --noreload
   ```

   In a separate frontend terminal:

   ```powershell
   Set-Location .\dawana-platform
   $env:DJANGO_API_PROXY_TARGET = 'http://127.0.0.1:8000'
   npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
   ```

5. Open `http://127.0.0.1:5173/dic/participant`. Choose First-Time Account Setup → existing booking reference/contact OTP → Sign-in settings → choose username, optional just-verified email and strong password. Phone-managed guardians use username. Log out; sign in by username and, when verified at activation, email. Wrong/unknown credentials must show the same generic error; repeated attempts must receive throttling.
6. Verify only the two authorized children appear and switch correctly. Requesting the foreign enrollment/ID directly must fail. Separately OTP-verify another booking with the same account contact/channel and explicitly link it using existing credentials; returning login may then include it. No email match alone may add it.
7. Use Forgot Password → OTP on an **already linked** booking → reset. Old password and prior account cookies must fail. A password/Google-only session, expired OTP proof or unrelated booking must not reset the account.
8. Fresh OTP on an account-linked booking → Link Google → real Google consent/code callback → participant `/auth/me/` and authorized bookings. Log out and return using Google. A Google identity not linked explicitly must fail even if its email matches. Replayed/wrong-browser/expired state and wrong nonce/audience/issuer must fail. Test actual signature/time validation with the real provider; do not count mocks as provider acceptance.
9. Fresh OTP → set a password if Google-only → Unlink Google. Old Google account sessions and returning Google login must fail. Revocation must not release the subject for another account. A changed Google email with unchanged verified `sub` must not expand or change booking ownership. Cancellation/refund/tutor revocation must remove corresponding credential-session access.
10. Leave persistence unchecked: session expires after 30 minutes. Check it on a personal device: returning browser session remains only until the configured ceiling (maximum eight hours), with no sliding refresh. Test logout in one tab clears other tabs; offline logout warns and supports retry. Test expiration, cancelled/foreign IDs, approved guardian ID rules and tutor housing/house-competition exclusions.
11. Inspect post-payment continuation at `/dic/register/payment-return` with existing isolated Paystack test evidence: backend confirmation still precedes continuation, and continuation without identity proof still requests OTP. No payment flag or callback fragment authenticates. Class remains pending for campers and not applicable for tutors.
12. At 320px/mobile width, keyboard through identifier, password, visibility toggle, persistence checkbox, Google, recovery and OTP. Check visible focus, labels, masked password default, loading/disabled controls, error announcements, camper selector and sign-out. Never share a browser profile with actual production accounts.

## Remaining acceptance / production blockers

- Python execution unavailable: backend system checks, policy suite, model state and migration graph need local execution.
- No new-schema database, writing integration tests, real OTP deliveries, real Google flow or browser acceptance have been executed/approved here. Existing prior Phase 3/Phase 2 results do not cover the new authentication storage.
- `google-auth[requests]` requirement must be installed/resolved and the real Google client configured. No successful Google authentication is claimed.
- A new isolated provisioning/acceptance guard and receipt for explicit target 0030 must be reviewed before any schema writes. Existing tutor receipts remain immutable and cannot certify this schema.
- Unrestricted `backend/render-migrate.sh` remains a deployment risk because 0027 is deferred; it was not modified. Resolve the deployment gate before release. Review proxy/client-IP trust, upstream callback-log redaction, provider timeouts, key rotation, OAuth-attempt retention and account lifecycle operations before production rollout.
