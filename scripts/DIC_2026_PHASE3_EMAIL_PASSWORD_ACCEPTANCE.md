# Phase 3 — email/password delivery and acceptance

Superseded workflow: see `DIC_2026_REGISTRATION_PASSWORD_DELIVERY.md` for the approved registration-time password flow. Legacy OTP setup/recovery below is retained for older bookings only.

This supersedes the public Google-login demonstration instructions in `DIC_2026_PHASE3_AUTH_COMPLETION.md`. Google implementation remains in source, but public login and account-link controls are hidden. The seven-phase roadmap is unchanged.

## Source changes

- `backend/dic/participant_api.py`: every protected grant requires a currently eligible booking scope. OTP scopes now use `portal_accounts.booking_eligible()`, which delegates to unchanged `participant_services.eligibility()`. OTP verification cannot mint an unpaid portal session. Expired/revoked/ineligible sessions can still sign out and clear cookies.
- `backend/dic/serializers.py`: new public orders require an explicit primary registrant name and normalized email. No inference from a child or first participant. Phone remains optional.
- `backend/dic/assisted_registration.py`: retains the existing staff-assisted phone contact/recovery path. It still requires explicit responsible contact through its existing validation and grants no portal entitlement or email identity proof.
- `backend/dic/portal_accounts.py`, `portal_account_api.py`: post-payment activation requires fresh eligible booking-email OTP, a matching email, strong password and matching confirmation. Django stores the password hash. Existing uniqueness, explicit binding, recovery and credential-version controls remain.
- Frontend `DIC.jsx`, `PrimaryRegistrantFields.jsx`, `bookingContact.js`: explicit booking contact at checkout, preserved in the existing contact/draft storage. Contact is locked after submission or an uncertain retry to protect idempotency. No password is collected or stored before payment.
- Frontend `ParticipantPortal.jsx`, `PortalAccountAccess.jsx`, `PortalPhase3.jsx`: email/password is primary, Google controls are hidden, confirmation is submitted during First-Time Account Setup, and legacy contact review guidance is shown. Setup remains available after leaving a successfully paid booking.
- Regression coverage: new `backend/dic/test_portal_eligibility.py`, frontend `bookingContact.test.js`; updated portal/account frontend tests, registration privacy API fixture, old optional-contact expectation, and revoked-scope/contact-change expectations. `scripts/validate_dic_phase3_policy.py` includes 66 database-free tests.

No migration, credential, payment settlement or database configuration change was made. Historical migration ordering, deferred 0027, retained databases, evidence and receipts were not touched. Tutor entitlement remains the existing authorized complimentary exception; housing and competition exclusions are unchanged.

## Eligibility and recovery boundaries

- Whole-order settlement remains unchanged. All items in a paid order require trusted existing eligibility. Separate orders are independently scoped: a paid order cannot expose an unpaid sibling order. No partial child payment model is introduced.
- Payment status flags alone are insufficient. Existing accepted price revision, verified provider evidence, amount/currency, reconciliation, cancellation, restriction and tutor checks remain authoritative. Both old OTP and password sessions recheck access on each protected request.
- Existing bookings are not backfilled or reassigned. Missing or unreliable primary contact cannot be replaced by a matching participant email. Use `/dic/register/recover`; if contact proof cannot be established, authorized staff must review ownership and contact correction using the existing controlled process. Do not register or pay again just to obtain portal access.
- Existing order checkout/payment bearer capabilities and financial recovery remain separate from participant portal authorization. They continue to permit unpaid customers to complete checkout; they do not grant protected camp information.
- A legacy uncertain submission without primary contact must be recovered/reviewed, not retried as a new booking with guessed contact data. Existing known order IDs continue through their saved checkout/recovery.

## Checks

Executed: 84 focused frontend tests passed, affected-file lint passed, production build passed (existing large-chunk advisory). A concurrent run produced a Vite dependency-cache collision warning; the sequential rerun passed all 84 tests without that warning.

Backend runner attempted, but the virtual environment cannot start its base Python executable (`Access is denied`). Therefore no backend tests/system checks were executed successfully, and no backend acceptance is claimed. Writing tests were not run. All database access remains unauthorized for this delivery.

From the repository root, after restoring Python access:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\validate_dic_phase3_policy.py
```

Expected: zero Django system-check issues, explicit 0030 graph excludes deferred 0027, matching prepared account model states, **66 database-free tests**, zero failures/errors/skips. This command selects an unused synthetic database name and blocks database connections and external side effects; it does not provision a database or apply migrations.

Frontend:

```powershell
Set-Location .\dawana-platform
node --test --test-concurrency=1 --test-reporter=spec src/services/bookingContact.test.js src/services/portalAccount.test.js src/services/portalPhase3.test.js src/services/participantApi.test.js src/services/participantSession.test.js src/services/participantThrottle.test.js src/services/camperExperience.test.js src/services/camperDashboard.test.js src/services/tutorRegistration.test.js src/services/paymentReturnApi.test.js src/services/dicApi.test.js src/services/registrationControls.test.js src/services/registrationPrivacy.test.js src/services/registrationPricing.test.js
npm.cmd run lint -- src/pages/DIC.jsx src/pages/ParticipantPortal.jsx src/components/dic/PrimaryRegistrantFields.jsx src/components/dic/PortalAccountAccess.jsx src/components/dic/PortalPhase3.jsx src/services/bookingContact.js src/services/bookingContact.test.js src/services/portalAccount.test.js src/services/portalPhase3.test.js
npm.cmd run build
```

## Manual acceptance — requires separate approval for database writes

Use only the approved isolated `dic_2026_demo` environment after authorization for registration, OTP, session, audit and payment-test writes. Do not reuse retained tutor acceptance evidence or run unrestricted migrations. The existing account rollout flag/schema and email delivery must already have been approved/configured; this work does not change them. Do not start against default `dawana_dev` settings.

1. New regular registration: enter the primary adult camper/guardian name and email at `/dic/register/checkout`. Omission must fail both client validation and direct API validation. Submit two children in one order. Confirm no portal session/account is created by order submission.
2. Before verified payment, attempt OTP verification, password login, `/api/v1/dic/participant/auth/me/`, enrollment reads and direct enrollment/ID/points requests. No protected data may be returned, even with a previously issued OTP cookie or forged frontend success flag.
3. Complete the existing isolated Paystack test flow. Only independently verified full-order settlement can make the order eligible. No fake settlement row or raw webhook payload may substitute for the approved verification mechanism.
4. Continue to `/dic/participant` → First-Time Account Setup → email OTP for that booking → Sign-in settings → username, the same verified email, strong password and confirmation → Create sign-in account. Mismatched confirmation or another person's email must fail. Confirm no password/confirmation is in browser draft storage, URLs or logs.
5. Leave after successful payment and close the registration tab. Return later through `/dic/participant` → First-Time Account Setup using the saved/recovered reference and primary email. Setup must not request another registration or payment. A duplicate account attempt must not create or overwrite an account; existing users use login/recovery or explicit booking linking.
6. Log out; log in by verified email/password. Confirm only linked eligible bookings and children appear. Separately create/use an unpaid order with the same guardian contact: it must not appear or be accessible through guessed enrollment IDs. Verify another eligible order and explicitly link it using the existing OTP + account credentials flow; matching email alone must not link it.
7. In the approved isolated test harness, invalidate payment/cancel/refund/revoke scope/change contact while keeping an existing OTP or password cookie. The next protected request must fail or omit the affected order. If another linked order remains eligible, only that order remains accessible. Logout must still clear/revoke the session when all access has been lost.
8. Verify password reset through fresh booking OTP, old-password/session revocation, expiry, opt-in persistence and cross-tab logout. Foreign bookings and child IDs must remain denied. Verify authorized tutors retain complimentary access while revoked tutor authorization denies access, with no housing or competition entry.
9. Inspect mobile/keyboard operation: contact fields, email/password login, visibility toggle, confirmation, error states, OTP, child switching and logout. Google login/link controls must be absent even if old OAuth configuration remains present. Classes remain pending for campers and not applicable for tutors.
10. Legacy unreliable contact: recovery must not silently assign a child's email or grant access. Demonstrate the staff-review route without creating a second registration or payment.

Remaining blockers: Python execution; backend policy/system-check validation; separately authorized database-writing integration/browser acceptance; confirmation of approved account schema/rollout and OTP delivery. Existing unrestricted `backend/render-migrate.sh` remains a deployment risk and was not changed. No deployment is authorized.
