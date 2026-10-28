# Phase 3 — registration-time password delivery

This supersedes the post-payment password creation steps in earlier Phase 3 acceptance notes. The seven-phase roadmap is unchanged. No database, migration, stored credential or deployment was modified during implementation.

## Resulting workflow

1. At regular registration checkout, the primary adult registrant/guardian supplies their name, email, password and confirmation. Passwords are separate transient React state, excluded from draft/session storage, order fingerprints, payment payloads, API responses and receipts. The backend applies Django password validation and hashing.
2. A new `PortalAccount` uses the existing Django User with `is_active=False`, a random internal username, and explicit binding to this submitted order. Existing account emails require the current account password before a new order is linked; matching email alone never links records or overwrites credentials. No portal grant is issued by registration.
3. The new account receives a one-time signed email-verification link, valid for one hour. The link uses `/dic/participant#verify-email=...`; the token is removed from the address bar and requires explicit confirmation. Verification creates no session and does not confirm payment. It only verifies email ownership. No OTP is required in this ordinary registration/login path.
4. Backend-verified full-order payment and existing participant eligibility are still required for email/password login and every protected request. An unpaid, pending, failed, refunded, cancelled, ambiguous/restricted or unlinked booking cannot gain access through a password or email link. Existing trusted Paystack settlement rules are unchanged. Different guardian orders remain independently eligible.
5. Returning users log in with email/password. Email verification is one-time, not per-login. Resending a link requires the selected account password, is rate-limited and returns a generic response. A mail outage does not cancel the saved order: the user can request another verification link from sign-in. No predictable password is assigned.
6. Previously registered paid campers and approved tutors retain First-Time Account Setup via fresh booking-email OTP and strong password confirmation. Forgot Password uses existing verified booking recovery; it may also recover an unverified registration account after trusted payment. An administrative account deactivation must not be treated as pending signup: a specific pending-registration audit marker and absence of earlier email verification/reset are required for signup activation.
7. Tutors preserve the approved complimentary exception, housing/competition exclusions and legacy invitation/OTP workflow. Staff-assisted phone recovery remains distinct; assisting staff never collect/set participant passwords. Google implementation is retained with public controls hidden.

## Schema and configuration

**No migration is required.** Existing User activation, PortalAccount, PortalAccountBooking, grants, audit and credential-version fields are reused. Historical migration order and deferred 0027 remain unchanged. Existing account schema 0030 must already be present before enabling account registration. No schema operation was performed.

Required backend runtime configuration before accepting new password registrations:

```powershell
# Configure only in the separately approved environment; no setting was changed here.
$env:DIC_PORTAL_ACCOUNTS_ENABLED = 'True'
$env:DIC_PORTAL_EMAIL_VERIFY_URL = 'http://127.0.0.1:5173/dic/participant'
```

The HTTP loopback URL is accepted only in DEBUG development. Production requires the approved canonical **HTTPS** URL ending exactly `/dic/participant`, without query/fragment/userinfo. An absent/unsafe verification destination fails new signup atomically. Existing verified accounts retain normal login; existing legacy recovery remains available. The owner must supply approved mail transport settings; credentials must not be committed. No live emails were sent by this implementation task.

Email dispatch uses Django mail after transaction commit; failure is kept generic and the portal supports password-protected resend. This is not a durable mail queue, so a failed dispatch requires resend. Signed links are invalidated by use, password reset/credential-version change, or expiry; they cannot restore administratively disabled accounts that previously verified/reset. Verification and payment are separate gates.

## Files

- New backend services/tests: `backend/dic/registration_accounts.py`, `backend/dic/test_registration_accounts.py`.
- Backend integration: `dic/serializers.py`, `views.py`, `portal_accounts.py`, `portal_account_api.py`, `urls.py`, `assisted_registration.py`, `config/settings/base.py`. New endpoint suffixes under `/api/v1/dic/participant/`: POST `auth/email/verify/` and POST `auth/email/resend/`.
- Frontend: `pages/DIC.jsx`, `pages/ParticipantPortal.jsx`, `components/dic/PrimaryRegistrantFields.jsx`, `PortalAccountAccess.jsx`, `PortalPhase3.jsx`, `services/bookingContact.js` and related tests. Password/account-setup recovery remains separate from the new ordinary signup path.
- Updated backend fixtures/tests: `dic/tests.py`, `test_registration_privacy.py`, `test_assisted_preparation.py`, `test_portal_accounts.py`; `scripts/validate_dic_phase3_policy.py` includes the new policy suite.
- Acceptance runner: `scripts/validate_dic_phase3_acceptance.py` now submits pre-payment credentials, mocks email-link delivery privately, verifies email via the real endpoint, denies login before email/payment, and tests password login after trusted mocked settlement. Separate legacy setup/reset and tutor scenarios remain. Browser mode fills checkout passwords and verifies the email link before login, without ordinary OTP. All existing database guards/rollback controls remain.

## Verification and acceptance

Frontend focused tests: **86/86 passed**, affected-file lint passed, and build passed with the existing large-chunk advisory. Backend Python could not start because the virtual environment's base executable reports Access is denied. Backend tests, compilation and runtime acceptance are not claimed passed. No database-writing tests or browser acceptance were run for this change.

Run database-free backend verification after restoring Python access:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\validate_dic_phase3_policy.py
```

Expected manifest: **74 database-free tests**, no failures/errors/skips; system checks and the existing account migration graph/state checks must pass. The wrapper blocks database/external side effects.

Then, only with separate approval for writing acceptance, run the guarded demo runner's preflight, integration and browser modes against explicit `dic_2026_demo`. Old receipts/results do not accept the changed workflow. Do not use ordinary migrate or Django test database creation/reset. The runner's mail mock stores synthetic verification tokens in memory only and reports no mail/password/token values.

Manual acceptance must cover: missing/mismatched/weak passwords; signup with no portal session; one-time email verification before and after payment; no login before both gates; repeated email-link rejection; expired links; password-protected resend; duplicate/existing email with wrong password; idempotent retry without credential leakage; two children/independent paid and unpaid orders; refund or revoked eligibility with an existing cookie; legacy paid setup and password recovery; tutor exclusions; and a mailbox outage with later resend. Inspect mobile fields, password visibility and confirmation, and ensure Google controls remain hidden.

Pending blockers: Python execution; real mail configuration and one-time link delivery in an approved sandbox; updated backend/integration/browser acceptance. No production readiness or acceptance is claimed.
