# Phase 3 — Simplified Participant Portal Login and Class Allocation

Source implementation handover. The seven-phase roadmap is unchanged. Earlier
Interactive Camp Experience findings are evidence only, not authorization to build
movement, scoring, tasks, timetables, announcements, feedback or leaderboards here.

No database connections/writes, migrations, deployment, real permission grants,
credential changes or receipt changes were performed. No migration file was created
or edited. Phase 3 is not marked complete: backend runtime and browser acceptance
are pending, and actual Google linking/class allocation have explicit blockers.

## Architecture reused

- Public registration and multi-camper orders remain in dic.views/_create_order.
- Paystack initialization, verification, webhook, reconciliation and authoritative
  settlement remain unchanged in payment_views.py/payments.py.
- Existing payment_return.py binds a two-hour return grant to a server-side browser
  session and the order's access digest. It proves return context, not human identity.
- Existing ParticipantPortalChallenge/Grant/Scope implement purpose-isolated OTP,
  cookie sessions, expiry, revocation and exact booking scopes. No staff login,
  password system or parallel participant authentication store was added.
- Existing scoped_orders/scoped_enrollment, camper selection, request cancellation,
  digital-ID issuance and guardian card checks remain the authorization boundaries.
- Phase 2 tutor authorization and its housing/competition exclusions remain intact.

## Implemented source behavior

### Post-payment continuation

New POST `/api/v1/dic/participant/auth/continue/` accepts only order_reference.
It reuses an active participant grant only if that exact booking is already scoped
and shared eligibility confirms the paid registration's trusted settlement evidence.
It does not add booking scopes, rotate/extend sessions, link accounts or issue IDs.

Without that verified participant session, an existing browser-bound payment-return
grant can establish booking recovery context only. Registered-contact OTP is still
required before participant records or the camper selector are displayed. Payment
status flags, redirect/query parameters, email matches and OAuth claims cannot mint
participant access. There is no new continuation bearer credential to store or replay;
the existing OTP is single-use. Return-context authority is neither extended nor
consumed, preserving callback/reload recovery behavior.

Both the existing confirmation UI and authoritative payment-return page use this
continuation action. Missing/expired/foreign authority leads to ordinary OTP recovery,
not automatic authentication. Network/rate-limit failures remain retryable errors.
Only a booking UUID is passed in router state; no token/code/contact is stored there.

### Returning users and persistent sessions

The existing `/auth/me/` startup check restores valid sessions without OTP on every
visit. Login now presents a clear verification-code option with booking-reference
recovery, existing delivery checks, throttling, cooldown, expiry and logout behavior.

An explicit personal-device checkbox sends remember_device as a boolean only after
OTP verification. Default sessions remain 30 minutes. Opt-in sessions reuse the
existing SESSION_COOKIE_AGE policy, capped at eight hours, with fixed server expiry
and no sliding renewal. HttpOnly, production Secure, SameSite=Lax, narrow cookie path,
CSRF and server revocation remain. No configuration file was changed. Logout/expiry
clears the checkbox and sensitive UI state; cross-tab invalidation remains unchanged.

GET `/api/v1/dic/participant/auth/capabilities/` exposes duration bounds and explicit
Google/class availability. Failure of this optional request does not disable OTP or
existing sessions; the persistence checkbox stays unavailable without capability data.

### Booking and guardian boundaries

The selector still contains only participants in the server-verified primary-contact
booking. Switching clears the displayed ID and invalidates outstanding requests.
Separate bookings are not silently merged by contact/email. A different booking must
be verified separately under existing authentication.

This is authorized booking access, not a new assertion of legal guardianship. Existing
approved housing guardian relationships do not expand booking scope. The JSON digital-ID
endpoint now applies the same authorized_portal_card gate as card downloads, including
the existing dependent/guardian rule. Cross-booking guardian/child access remains denied.
No is_guardian input, parent account role or guardian permission grant was introduced.

Delegation to a parent who is not the verified primary contact, cross-booking household
linking, or changing dependent ID policy needs an explicit authorization policy. Do not
reuse housing relationships as a general parent login/delegation system.

### Class integration and visual experience

No teaching-class, class-assignment or reassignment schema/workflow exists in this code.
RegistrationCategory is pricing/registration classification, not a teaching assignment.
Housing and the scoring catalogue are also separate concepts.

Enrollment responses now include class_assignment with name=null and pending_setup
for campers, or not_applicable for tutors. The portal clearly separates registration
category from the pending teaching class. No age-derived or fabricated class is shown.
No administrative assignment/reassignment control was invented without storage/policy.

The official logo/fonts/palette remain. Lightweight decorative SVG geometry, architecture,
tents and trees supplement the login; artwork is hidden from assistive technology.
Cards, focus states, responsive grids and tutor navigation column sizing were improved,
without new scroll locks, inner scrolling or heavy animations.

Seven dashboard locations are prepared: today's activities, full camp timetable, house
duties, food timetable, digital ID/QR, daily feedback and final evaluation. Only existing
eligible ID access is actionable. Other locations explicitly say Coming later, contain
no statistics, and invoke no new module endpoints. House duties are omitted for tutors.
Existing scoring/movement/feedback services and their prior routes were not changed or
activated; no Phase 5 table/migration was enabled.

## Google OAuth/OIDC feasibility and exact prerequisites

No Google OIDC provider, callback, token-verification library configuration or durable
participant identity-link model was found in the repository. Google sign-in is visibly
disabled. Setting credentials alone cannot enable it: secure linking source and approved
storage are also required. No production credential or secret was read or modified.

Before a future implementation:

1. An owner configures a Google Cloud project/consent screen and a Web Application OAuth
   client, with approved public origins and an exact HTTPS callback URI. A possible future
   route is `/api/v1/dic/participant/auth/google/callback/`; it is NOT implemented now.
2. Supply client ID, server-only secret and exact redirect URI through deployment secrets.
   Proposed names are DIC_GOOGLE_CLIENT_ID, DIC_GOOGLE_CLIENT_SECRET and
   DIC_GOOGLE_REDIRECT_URI; none is currently consumed. Never use a VITE client-secret key.
3. Implement authorization-code flow with PKCE, browser-bound single-use state/nonce,
   short expiry and an approved token-verification library. Validate signature/JWKS,
   issuer, audience, azp where applicable, expiry, nonce and verified-email claim.
4. Request minimal openid/email scopes. Use immutable issuer/sub for provider identity.
   Do not automatically link registrations by email, name or Google account selection.
5. Require existing booking OTP/session authority plus explicit linking consent. Approve
   durable link/consent/revocation storage, conflict handling and cross-booking boundaries
   before enabling the button. Participant identity must never confer staff authority.

Official references: https://developers.google.com/identity/openid-connect/openid-connect
and https://developers.google.com/identity/openid-connect/reference .

## Class schema/business approval needed

Approve the class/group definition, edition scope, teaching criteria, instructor role,
capacity, unassigned state, reassignment authority/reason and audit history. Decide how
authorized tutors teach classes without being classified as competing campers. Preserve
DOB privacy and do not assume age alone determines class placement.

Expected future storage concepts are class/group definitions plus explicit participant/
enrollment assignments with assignment/reassignment provenance. This is a proposal only;
there are no model or migration files for it. Any future core migration must preserve
the approved 0026 -> 0028 -> 0029 -> deferred 0027 ordering, with an explicit receiving-
environment history review. No historical migration rewrite or ordinary unrestricted
migrate is acceptable. backend/render-migrate.sh remains unchanged and unsafe for a
Phase 2/3-only release because it migrates the deferred leaf.

## File inventory

Created:

- backend/dic/portal_phase3.py
- backend/dic/portal_continuation.py
- backend/dic/test_portal_phase3.py
- scripts/validate_dic_phase3_policy.py
- dawana-platform/src/services/portalPhase3.js
- dawana-platform/src/services/portalPhase3.test.js
- dawana-platform/src/components/dic/PortalPhase3.jsx
- dawana-platform/src/components/dic/PortalPhase3.css
- scripts/DIC_2026_PHASE3_PORTAL_IMPLEMENTATION.md

Modified:

- backend/dic/participant_api.py: bounded opt-in sessions, class projection and ID gate.
- backend/dic/urls.py: capabilities and continuation routes.
- dawana-platform/src/pages/DIC.jsx; pages/PaymentReturn.jsx: secure continuation UI.
- dawana-platform/src/pages/ParticipantPortal.jsx: login, persistence and decoration.
- dawana-platform/src/components/dic/CamperExperience.jsx: class/integration cards and
  correct tutor navigation sizing, preserving existing competitive screens for campers.
- dawana-platform/src/services/camperExperience.test.js: handoff assertion follows the
  new server-validated continuation component; dedicated tests cover its security.

## Verification and local commands

Executed: 58 focused frontend tests passed, affected-file oxlint passed, production
build passed with the existing >500 kB bundle warning. Backend policy invocation was
blocked before interpreter startup by Python313 Access is denied. No Python tests,
Django checks or database integration checks are claimed passed. Seventeen new
SimpleTestCase policy regressions are prepared; all forbid database access.

From the workspace in local PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
$phase3Python = Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
& $phase3Python -B .\scripts\validate_dic_phase3_policy.py
if ($LASTEXITCODE -ne 0) { throw 'Database-free Phase 3 checks failed; stop.' }
# Optional existing Phase 2 database-free regression suite only:
& $phase3Python -B .\scripts\validate_dic_tutor_registration.py policy
if ($LASTEXITCODE -ne 0) { throw 'Phase 2 policy regression failed; stop.' }

Set-Location .\dawana-platform
node --test --test-reporter=dot src/services/portalPhase3.test.js src/services/participantApi.test.js src/services/participantSession.test.js src/services/participantThrottle.test.js src/services/camperExperience.test.js src/services/camperDashboard.test.js src/services/tutorRegistration.test.js src/services/paymentReturnApi.test.js
npm run build
```

The Phase 3 policy wrapper disables database connections, external HTTP and subprocesses;
checks Django source/system state and a database-free migration graph; and executes only
the allowlisted 17 database-free cases. It contains no provisioning/migration action.

## Guarded isolated integration procedure — approval required first

No integration database was created/reused. Do not run standard manage.py test or reuse
any retained tutor concurrency/acceptance database or receipt.

After explicit approval, prepare a NEW dedicated disposable name/creation receipt,
loopback development-only identity/owner/OID/comment checks, a migration digest and an
exact target closure excluding 0027. Reuse the existing guarded validation helpers,
not unrestricted migrate/post_migrate/flush. Provision only that approved new database.
Run transaction-wrapped fixtures, synthetic contacts and mocked provider/delivery
responses; retain failed evidence without resets or deletion.

Required integration cases: real OTP consumption, 30-minute default/eight-hour opt-in,
cookie restart/expiry/revocation/logout, browser-bound payment-return continuation,
cross-booking denial, multiple-child selection, approved dependent guardian ID gates,
revoked tutor access, unchanged payment evidence/reconciliation and class pending states.
No Google token/network acceptance is possible before its linking/configuration work.

## Manual browser acceptance — pending

- Confirm server-verified paid continuation, including refresh/interrupted return.
- Spoof payment query flags/use foreign booking IDs: no authentication or records leak.
- Fresh browser requires contact OTP; existing valid session resumes without another OTP.
- Personal-device opt-in persists only until fixed server expiry; shared-device default
  stays 30 minutes. Logout, expiry, revoked scope and other-tab closure clear data.
- Switch authorized campers and verify ID/class/house displays never retain the previous
  participant. Try a foreign child ID and a housing link outside the verified booking.
- Check tutor ID access with no class/house duties/competition assignment or score fetch.
- Confirm Google is disabled, class state is explicit, later-module cards do not navigate
  or fabricate information, and existing regular registration/Paystack remain unchanged.
- Check keyboard focus, mobile/tablet/desktop navigation, artwork, long names, checkbox
  sizing, normal document scrolling and ID download formats.

## Remaining blockers

- Runtime acceptance: local Python access, guarded isolated DB approval and browser QA.
- External configuration/security: Google project/client/callback, verified token flow,
  explicit identity linking and revocation design. Google remains disabled.
- Database/business approval: real class allocation/reassignment storage and rules.
- Authorization policy if requested: non-primary-contact parent delegation or general
  household/cross-booking linking. Existing verified-booking access is implemented.
- Optional enhancement: longer-than-existing-policy sessions or different persistence
  durations need a separately approved policy; no silent long-lived refresh was added.

No claim of operational Phase 3 completion or deployment is made.
