# DIC Phase 2 complimentary tutor registration

27 October 2026. Source implementation and migration preparation only. No database
connection, creation, migration, permission grant, deployment or existing receipt
change was performed. This source requires 0028 and 0029; do not serve it against
the unchanged development schema. Backend runtime acceptance is pending.

## Implemented behavior

Only explicitly designated active staff may authorize, issue/reissue or revoke
tutors. The permission is `dic.can_authorize_dic_tutors`; the standard staff-role
command excludes it. Even superusers need an actual user/group grant. No grants
are made by the migration or source implementation.

Django Admin creates an edition-specific authorization with name, normalized email,
authorizer, timestamp and reason. Enable tutor registration on the edition before
issuing. The one-time copy response contains a random fragment invitation, with
no-store/no-referrer headers. Select the existing allowed frontend origin if Admin
and the public website have different origins. Distribute the link privately.
Stored credentials are digests only. Invitations expire exactly seven days after
issue; reissue of an unused, unrevoked authorization invalidates its old invitation,
codes and capabilities. Revoked authorizations remain historical evidence; a new
authorization is needed to restore a revoked entitlement.

The existing `/dic/register` form handles the invitation in memory and removes the
fragment. It does not instantiate the normal draft/payment workflow in invitation
mode. Before revealing authorized identity or the form, a code must be delivered
to and verified through the authorized email. This uses existing configured email
delivery utilities; delivery configuration must already be available. No provider
or feature configuration was enabled. This increment supports authorized email,
not additional SMS/WhatsApp invitation channels.

Verification codes have five attempts and ten-minute expiry, existing request/contact
rate limits and endpoint throttles. Verification creates a ten-minute HttpOnly,
SameSite Strict, browser-bound capability; cookies are Secure on HTTPS. Existing
CSRF enforcement applies. Unknown/expired/revoked invitation requests use the same
response shape. No invitation credential is sent in a URL query, payment metadata,
analytics call, draft or browser storage. Existing same-site credentialed frontend
and API/CSRF configuration remains required; no cross-site cookie policy was relaxed.

Redemption locks edition, authorization and verification, rejects identity/contact
changes and possible existing edition registrations, and consumes one authorization
for one tutor. Name/email are canonicalized to the authorization. The shared
participant serializer retains all ordinary fields, optional adult DOB and optional
measurements. Exact DOB must prove adulthood; withheld DOB requires adult assertion.
No ordinary category age limits or public registration dates apply. Edition must
be active, not ended and explicitly enabled for new tutor registrations.

The order is confirmed with registration_basis=tutor, payment_status=not_required
and zero due. The inactive internal `DIC Tutor` category preserves existing protected
category/source FKs and snapshots. It is not a public registration option and cannot
be activated through model validation, including after renaming once referenced.
No PaymentAttempt, payment settlement or price revision is created. Ordinary public
creation rejects role/payment/price claims and possible duplicate tutor identities.
Mixed paid/tutor bookings and camper-to-tutor conversion are unsupported.

Shared eligibility keeps the existing verified-payment branch and adds an exact
redeemed, verified, unrevoked tutor-authorization branch. Shared source review,
restrictions and cancellation still apply. The tutor order must contain exactly
one item, no price revision or payment attempt, and zero due. The existing booking
OTP portal, staff ID issuance, QR verification, check-in and movement services are
reused. IDs are never automatically issued by registration or contact verification.
Staff source review cannot convert between paid/tutor sources.

Tutor housing, queue insertion/discovery, guardian accommodation groups and house
competition eligibility are rejected in backend services/models. Portal responses
omit tutor housing assignment; tutor screens omit housing and points/house sections
and show digital ID, arrival, booking and approved noncompetitive programme links.
The house scoring API returns no tutor competition data. No new activity or portal
system was introduced. Tutor accommodation stays entirely offline.

Revocation records actor/time/reason, invalidates active credentials, browser
capabilities and booking/portal scopes, and leaves historical attendance/movement
and audit intact. Manual movement permits a documented, separately authorized
departure for a revoked tutor already inside; QR-based arrival/return is denied.
Invitation expiry governs redemption, not an already-redeemed tutor's entitlement;
existing camp-end ID expiry still applies. Disabling edition tutor registration
stops new registrations; revoke specific authorizations to remove existing access.

Operations/exports identify tutor basis and authorization state, suppress false
repricing and retain paid-only revenue/unpaid metrics. Campsite housing-wait counts
exclude tutors. Finance explicitly excludes complimentary registrations from
settlement revenue. Regular Paystack logic is preserved with additional tutor-order
rejection at payment initialization, repricing, settlement lock and model saves.

## Files created

- backend/dic/tutor_models.py
- backend/dic/tutor_registration.py
- backend/dic/tutor_registration_api.py
- backend/dic/tutor_admin.py
- backend/dic/templates/admin/dic/tutor_authorization.html
- backend/dic/migrations/0029_authorized_tutor_registration.py
- backend/dic/test_tutor_registration.py
- dawana-platform/src/components/dic/TutorRegistration.jsx
- dawana-platform/src/services/tutorRegistration.test.js
- scripts/validate_dic_tutor_registration.py
- scripts/DIC_2026_TUTOR_REGISTRATION_IMPLEMENTATION.md

## Files modified for this increment

- backend/dic/models.py; admin.py; urls.py; serializers.py; views.py
- backend/dic/participant_services.py; participant_api.py; portal_dashboard.py
- backend/dic/identity_cards.py; identity_admin.py; templates/dic/identity_cards.html
- backend/dic/checkin_services.py; campsite_api.py
- backend/dic/allocation.py; housing_policy.py; housing_models.py
- backend/dic/activity_scoring.py; activity_scoring_api.py
- backend/dic/payment_views.py; pricing.py
- backend/dic/operations_api.py; operations_exports.py
- backend/dic/management/commands/setup_dic_staff_roles.py
- backend/dic/test_registration_privacy.py (allow only the new tutor isolated DB
  pattern in addition to the existing privacy pattern for shared regression tests)
- backend/dic_movement/services.py; backend/dic_finance/services.py; backend/dic_finance/tests.py (regular-payment fixture basis)
- dawana-platform/src/pages/DIC.jsx; pages/Operations.jsx
- dawana-platform/src/components/dic/RegistrationPrivacyFields.jsx; CamperExperience.jsx
- dawana-platform/src/services/participantIdentity.js

Earlier uncommitted work is retained. Neither the successful privacy database/receipt
nor any historical migration/validation evidence database was touched.

## Migration and validation boundaries

Static source ordering: `0026 -> 0028 -> 0029 -> 0027`. New 0029 depends on 0028
and the swappable accounts initial migration, with run_before 0027. Historical
0027/0028 files were not changed. 0027 SHA256 remains
`269a8935f68dd660c8bf1d82ddcf44c1a574fa0262d4efb06fa9c94292a59aed`.
Runtime Django graph/model-state validation has NOT run here.

The new runner targets core 0029 plus the initial Movement and Scoring supporting
apps for operational tests. Its exact prerequisite allowlist excludes 0027 and
checks model drift, conflicts, graph edges, expected migration set and absent
feedback/welfare sentinel tables. It refuses operational, privacy and legacy DB
names: only fresh generated `test_dic_tutor_<timestamp>_<hex>` names are accepted.
Loopback/development-only configuration, role privileges, empty-schema checks,
owner/OID/server/comment markers and migration digests bind every receipt. No
ordinary test runner, unrestricted migrate, post_migrate, flush or cleanup action
is used. External provider calls are blocked during validation; tests use mocks.

The unrestricted `backend/render-migrate.sh` remains unchanged and is a separate
deployment blocker while 0027 is deferred. Do not point this graph at the six legacy
0027-applied evidence databases. Do not reuse the successful privacy database.

## Checks and commands

Executed: 36 focused frontend tests passed (including Operations regressions),
affected-file oxlint passed, production build passed with the existing bundle-size
warning. Python preflight failed before interpreter
startup: configured Python313 executable returned Access is denied. No backend
test, model-state/system check, migration executor or database operation ran here.

Run these database-free commands in local PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
$tutorPython = Join-Path (Get-Location) 'backend\.venv\Scripts\python.exe'
$tutorRunner = '.\scripts\validate_dic_tutor_registration.py'
& $tutorPython -B $tutorRunner preflight
if ($LASTEXITCODE -ne 0) { throw 'Tutor graph/model/system preflight failed; stop.' }
& $tutorPython -B $tutorRunner policy
if ($LASTEXITCODE -ne 0) { throw 'Tutor/privacy policy checks failed; stop.' }
```

Expected policy manifest: 49 methods (9 tutor, 9 privacy, 10 preparation,
19 existing Finance regressions, 2 existing Paystack client checks).
The prepared rollback integration suite has 28 methods (16 tutor, 7 privacy,
4 existing trusted Paystack settlement/webhook safeguards and 1 existing paid public
multi-camper regression). It covers authorization, expiry,
reissue/revoke, verified contact/code replay/attempts, capability binding,
out-of-window creation, privacy/adult validation, no payments, duplicate review,
existing portal scope, QR/check-in/movement, controlled revoked departure, housing
and scoring exclusion, reports and ordinary public role rejection. It has NOT run.

Only AFTER separate explicit approval to create a NEW isolated test database:

```powershell
$tutorReceipt = Join-Path (Get-Location) ('output\acceptance\tutor-' + [guid]::NewGuid().ToString('N') + '.json')
& $tutorPython -B $tutorRunner create --receipt $tutorReceipt --approve-isolated-writes
if ($LASTEXITCODE -ne 0) { throw 'Creation failed; retain receipts; stop.' }
& $tutorPython -B $tutorRunner schema --receipt $tutorReceipt --approve-isolated-writes
if ($LASTEXITCODE -ne 0) { throw 'Schema failed; retain database and receipts; stop.' }
& $tutorPython -B $tutorRunner integration --receipt $tutorReceipt --approve-isolated-writes
if ($LASTEXITCODE -ne 0) { throw 'Integration failed; retain evidence; stop.' }
& $tutorPython -B $tutorRunner verify --receipt $tutorReceipt
if ($LASTEXITCODE -ne 0) { throw 'Isolated verification failed; stop.' }
```

Expected: exact allowlisted schema without 0027, 28 tests with no skips/failures,
then no retained participant/order/payment fixtures. The DB and receipt are retained.

Separately approved concurrency evidence can run LAST on that verified empty tutor
database, with the same explicit write flag. It starts two real connections behind
a barrier and requires one order/person/enrollment/redemption audit. It deliberately
retains committed synthetic fixtures and a sibling `.concurrency.json` receipt;
never run rollback suites or empty-business verification against it afterward.

```powershell
& $tutorPython -B $tutorRunner concurrency --receipt $tutorReceipt --approve-isolated-writes
if ($LASTEXITCODE -ne 0) { throw 'Concurrency failed; retain all partial evidence; stop.' }
```

Before any operational migration, backend checks, paid-provider regression suites
and browser acceptance remain mandatory in approved isolation. Exercise real Admin
forms/origin selection, mocked email delivery, invitation refresh/reissue, errors,
mobile/keyboard behavior, existing portal handoff, ID formats, revocation races and
ordinary paid registration. No real provider/payment operation is authorized here.
Migration application, permission designation, feature enablement and deployment
remain separate future actions, not completed or authorized by this handover.
