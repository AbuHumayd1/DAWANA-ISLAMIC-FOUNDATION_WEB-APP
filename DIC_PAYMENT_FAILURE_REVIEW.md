# DIC 2026 checkout failure review

## Confirmed findings and limits

The two displayed failures occur at different stages. There is no evidence that
they share a payment, pricing or Paystack root cause. Both paths concealed useful
error information. The source corrections address that confirmed defect; they
do not claim that either production transaction is now ready to charge.

### Preserved ₦4,000 Pre-Primary attempt

`dawana-platform/src/pages/DIC.jsx:633` initializes payment, retains its reference
and authorization URL in memory, then calls `establishReturnGrant` at line 607.
The incident message comes from that function's catch at line 621. It therefore
identifies a return-setup failure after initialization, not a rejected price or
proof of a successful charge. Previously the catch discarded the cause entirely.

The return client at `src/services/paymentReturnApi.js:19` (under
`dawana-platform`) can fail before any backend request: `paymentReturnApiAllowed`
at line 9 permits same-origin hosting or the explicit HTTPS foundation/sibling
API arrangement. It rejects a direct `onrender.com` API from the foundation
website. If that is the deployed build configuration, this exact branch explains
the incident. It must not be bypassed: cross-site Lax cookies would also prevent
reliable CSRF/session authentication. A client error now has a stable
`payment_return_origin` code and fixed, safe guidance.

If hosting passes that check, the client gets a fresh token from
`/api/v1/dic/operations/auth/csrf/`, then POSTs
`/api/v1/dic/orders/<order_id>/payment-return-grant/` with the order bearer,
`X-CSRFToken`, credentials included, and no caching. A JSON CSRF token does not
prove cookie delivery. Missing cookies, token mismatch and untrusted origins can
still fail independently. `backend/dic/payment_return.py:86` enforces CSRF before
the grant handler. Its failure is HTTP 403 with the fixed payment-return CSRF
message. The handler at line 101 then checks the order bearer; unavailable or
expired authority is deliberately HTTP 404 (`backend/dic/access.py:9`).

`backend/dic/payment_return.py:28` requires database-backed sessions and saves a
server-side marker before binding a grant to the session-key digest and current
order-token digest. A non-database session backend raises HTTP 400 with
`Server-side payment return sessions are unavailable.` Missing session tables,
failed session writes, throttles, network and CORS failures are other distinct
possibilities. The original displayed message cannot distinguish them. Production
request/response evidence is needed to identify which occurred; none was supplied
with the incident. No production request or provider call was made in this task.

The existing recovery checkout is also traced:
`dawana-platform/src/pages/DIC.jsx:377` prepares its return grant before payment
initialization, while the new-registration checkout prepares it afterward.
Changing this sequence is not necessary to fix diagnostic loss or to retry the
already preserved attempt, so neither flow's payment behavior was changed.

### Estimated ₦30,000 order rejected with HTTP 400

`dawana-platform/src/pages/DIC.jsx:732` builds the registration payload and calls
`POST /api/v1/dic/orders/`. `backend/dic/views.py:312` first validates
`RegistrationOrderCreateSerializer`; invalid data fails before order creation or
payment initialization. `backend/dic/serializers.py:253` requires nested booking
contact, participant and portal-account serializers. Password checks are at line
226 and `backend/dic/portal_accounts.py:118`; participant fields/age declarations
are at serializer line 182. Django also checks category eligibility and current
registration/pricing configuration in `backend/dic/views.py:141` (`_create_order`).

The old `errorMessage` at `dawana-platform/src/services/dicApi.js:14` only extracted
top-level strings/string arrays or `detail.detail`. It ignored nested structures
such as:

```json
{"portal_account":{"non_field_errors":["This password is entirely numeric."]}}
{"participants":{"1":{"email":["Enter a valid email address."]}}}
```

Both shapes are reproduced against the real order endpoint without a database.
The installed DRF returns a sparse participant-index map; other supported versions
can return a positional list. The correction supports both. It displays, for
example, `Account: This password is entirely numeric.` or
`Participant 2 — Email: Enter a valid email address.` The frontend's basic password
length/confirmation checks do not replace Django's stronger password policy.

These are confirmed mechanisms for the generic message, **not proof that the
participant used a numeric password or an invalid email**. The exact production
HTTP 400 body was not provided. A non-JSON edge response can also produce the
same generic message. Do not infer or change submitted data from an estimated
total alone.

## Pricing, security and duplicate-attempt review

- Estimates use `dawana-platform/src/services/registrationPricing.js:1`; server
  pricing uses `backend/dic/pricing.py:22`. Approved fees remain in
  `backend/dic/migrations/0034_approved_2026_fees.py:8`: Pre-Primary early bird
  ₦4,000/regular ₦5,000; primary ₦10,000/₦12,000; secondary ₦12,000/₦15,000;
  undergraduate ₦15,000/₦17,000; graduate/adult ₦18,000/₦18,500. No fee,
  cutoff, eligibility, historical snapshot or tutor exemption was changed.
  An estimated ₦30,000 is not evidence of an authoritative total or valid order.
- Order creation uses a UUIDv4 idempotency key and keyed fingerprint
  (`backend/dic/views.py:67`, `:82`, `:141`). Same-key/same-payload replay reuses
  the order and rotates bearer authority; different payloads conflict. Credentials
  are excluded from the fingerprint but are checked for account binding. Private
  drafts retain recovery identifiers, not participant details/passwords/bearers
  (`dawana-platform/src/services/productionContract.js:19`). After reload, use
  authorized recovery; do not recreate the registration or guess its credentials.
- Public order/payment requests remain bearer-only with cookies omitted
  (`dawana-platform/src/services/dicApi.js:70`), except the existing, narrowly
  scoped staging-gate retry. Return requests remain CSRF/cookie protected.
  Production Secure, HttpOnly session, host-only and Lax policies are unchanged
  (`backend/config/settings/base.py:41`, `settings/production.py:18`,
  `settings/render.py:28`). A foundation frontend and sibling `api` hostname are
  cross-origin but same-site; a Render hostname is cross-site.
- `retryReturnGrant` (`DIC.jsx:626`) calls only return setup. The backend grant
  uses `update_or_create` for that order/session. It never initializes a payment.
  Initialization (`backend/dic/payment_views.py:394`) locks the order, reuses a
  current pending attempt/URL, and blocks unknown/unresolved, mismatched-mode and
  reconciliation cases. Paid/refunded/cancelled and complimentary tutor orders
  cannot initiate another ordinary payment.
- Provider calls occur after an attempt is persisted. Unknown initialization
  outcomes retain their reference and require verification rather than automatic
  resubmission. The initialization URL must be HTTPS on Paystack and the provider
  must return the existing reference. No automatic charge retry was introduced.
- A redirect is only a lookup hint. `PaymentReturn.jsx` and
  `paymentReturnApi.js:56` call `POST /api/v1/dic/payments/return/` using the
  cookie grant. `backend/dic/payment_return.py:125` authorizes the grant and
  verifies the existing reference through `_verify_attempt`, never initialization.
  Manual verification uses the same service (`payment_views.py:686`).
- `_apply_verified_transaction` (`payment_views.py:158`) checks exact reference,
  integer amount in kobo, NGN currency, test/live environment, unique provider
  transaction identity, success status and provider-confirmed payment time against
  the accepted pricing window. Only verified evidence confirms the order.
- Webhooks (`payment_views.py:717`) validate a bounded raw body and signature,
  deduplicate events and independently verify through Paystack. Existing legacy
  HMAC-SHA512 and configured timestamped-signature/no-downgrade behavior
  (`backend/dic/payments.py:156`) is preserved. Keys, live activation, callback
  validation, TLS verification and provider timeout safeguards are unchanged.
- Absolute absence of external duplicate charges cannot be promised: an old
  Paystack authorization may remain payable after explicit repricing supersedes
  it (`payment_views.py:584`). The application warns about this and detects
  duplicate successful charges. Before controlled resumption, verify the original
  reference and resolve old authorizations; do not open multiple checkouts or
  accept a new quote to work around an unresolved payment. No repricing policy
  change was included in this minimal correction.
- `backend/health/views.py:15` checks database/optional worker readiness. A Live
  Render service and HTTP 200 health response do not establish browser origin,
  CSRF/session cookie persistence, valid registration input or Paystack settlement.

## Changes

Runtime changes are limited to diagnostics:

1. `dawana-platform/src/services/dicApi.js`: bounded traversal of recognized DRF
   validation fields, human-readable participant/account labels, control-character
   removal, and redaction of echoed invalid-choice values. Unknown fields and
   non-JSON responses retain a generic fallback; no response/form serialization,
   logs or browser persistence were added.
2. `dawana-platform/src/services/paymentReturnApi.js`: stable hosting rejection
   code and fixed setup guidance distinguishing hosting, CSRF/authorization,
   unavailable order access, rejected server session configuration, throttling
   and temporary failures. No allowlist or cookie weakening.
3. `dawana-platform/src/pages/DIC.jsx`: retain and display that safe setup
   guidance while preserving the existing attempt and grant-only retry.

Regression/validation changes:

- `dawana-platform/src/services/dicApi.test.js`: nested list/map validation,
  sanitized messages, safe fallback, and no mutation retry on HTTP 400.
- `dawana-platform/src/services/paymentReturnApi.test.js`: failed CSRF setup then
  fresh-token grant-only retry; fixed diagnostics do not expose raw error data.
- `backend/dic/test_checkout_validation.py`: real endpoint rejects numeric
  passwords and invalid second-participant email before order/rate-limit/provider
  mutation; nested errors contain no submitted password/contact value.
- `backend/dic/test_payment_return.py`: disposable PostgreSQL regression creates
  an authoritative ₦4,000 quote/400,000-kobo attempt, rejects a missing CSRF
  cookie, then retries setup twice with one attempt, one grant and a persistent
  database session. Only the original initialization is called.
- `scripts/test_production_policies.py`: includes the new database-free tests.
- `.github/workflows/backend-acceptance.yml`: extends the existing frontend job
  with locked dependency installation and checkout/return/pricing/privacy tests
  from the correct frontend directory. Existing PostgreSQL 14/18 core discovery
  includes the new payment-return integration regression.
- `DIC_PAYMENT_FAILURE_REVIEW.md`: this report.

Existing uncommitted work, including the earlier Operations review changes, was
retained. No production database, record, environment, deployment, merge,
credential, Cloudflare, DNS or Render setting was changed.

## Validation performed

- **29 frontend tests passed** across dicApi, paymentReturnApi, paymentProcessing,
  registrationPricing, bookingContact and productionContract. Command from
  `dawana-platform`: `node --test src/services/dicApi.test.js
  src/services/paymentReturnApi.test.js src/services/paymentProcessing.test.js
  src/services/registrationPricing.test.js src/services/bookingContact.test.js
  src/services/productionContract.test.js`.
- **25 database-free backend tests passed**: CheckoutValidationTests (2),
  RegistrationAccountPolicyTests (7), ProductionPaymentPolicyTests (7), and
  PaymentEntitlementModeTests (9). These cover preserved live-mode, signature,
  early-bird entitlement and tutor-exemption safeguards as well as the new errors.
  The existing policy runner blocks all database and outbound network access and
  does not read dotenv. It ran under bundled Python 3.12 with the workspace
  site-packages appended, as in the earlier Operations review; no dependency or
  virtualenv modification was made.
- Targeted oxlint: clean after fixing an intentional control-character regex
  warning. Three changed Python files passed AST parsing; `git diff --check`
  passed. A final targeted dicApi test rerun passed.
- Initial test harness issues were corrected: participant errors use sparse maps
  in the installed DRF; Vite-backed booking tests must run from the frontend
  directory. The corrected runs above have no failures or skips.
- **Not executed:** PostgreSQL integration tests, GitHub Actions, production
  browser acceptance or any actual Paystack request/charge. A local YAML-parser
  probe found no installed PyYAML; the workflow was reviewed but not executed.

## Safe next steps for the first controlled live payment

1. Obtain the sanitized failing request URL, status and JSON error body for both
   incidents, the actual built frontend API base and frontend origin. Remove
   participant/contact data, passwords, tokens, cookies and references from shared
   diagnostics. If no grant request occurs, inspect the local hosting guard; if
   one occurs, distinguish CSRF 403, bearer/grant 404, session-configuration 400,
   throttle 429 and infrastructure failure. Fix only the established cause.
2. Run the prepared GitHub Actions policy/frontend and PostgreSQL acceptance
   jobs on the proposed source revision. Review this patch and approve deployment
   separately. No CI job was triggered or source pushed during this review.
3. If the build calls Render directly, obtain owner approval for the same-site
   API arrangement already specified by the deployment templates:
   `api.dawanaislamicfoundation.org` with valid HTTPS;
   `PUBLIC_HOST=api.dawanaislamicfoundation.org`;
   `FRONTEND_ORIGIN=https://dawanaislamicfoundation.org`;
   frontend build `VITE_API_BASE_URL=https://api.dawanaislamicfoundation.org/api/v1`.
   An approved same-origin proxy is the alternative. DNS/Render/Cloudflare or
   environment changes and frontend rebuild/deployment remain owner actions.
   Do not broaden origins or switch cookies to SameSite=None as a workaround.
4. Owner verifies the configured callback is
   `https://dawanaislamicfoundation.org/dic/register/payment-return` and the
   configured webhook targets `/api/v1/dic/payments/paystack/webhook/` on the
   approved backend. Confirm the existing live key/mode/activation/signing setup
   without exporting secrets, rotating keys or rewriting an attempt's mode.
5. For the first preserved order, an authorized operator checks the original
   payment reference/status and provider_mode, plus expected amount/currency and
   accepted pricing window. If already successful, verify/reconcile it and do
   not charge again. A test-mode, ambiguous, mismatched, expired-price or charged
   attempt requires authorized reconciliation before any new payment. Never
   convert historical mode or pricing evidence to make a checkout work.
6. Keep the original tab open if it still has authority. Check CSRF Set-Cookie
   is accepted and sent back; use **Retry secure return setup**, which does not
   initialize payment. Confirm ready=true and that the Secure/HttpOnly session
   cookie persists across the intended callback tab. After refresh/token expiry,
   use verified existing-registration recovery instead of resubmitting a new
   order. Session/login token rotation may invalidate an old grant; re-establish
   it using valid existing-order authority.
7. Only after owner approval and the above checks, open the one existing live
   authorization once. Confirm the authoritative amount before paying. On return,
   verify that independent Paystack evidence matches reference, 400,000 kobo/NGN
   if the ₦4,000 early-bird quote is still valid, live domain and payment time.
   Confirm one successful attempt, confirmed order, one set of entitlements and
   idempotent callback/webhook handling. A redirect, health response or bank debit
   alone is not application confirmation; pending/unknown outcomes require
   verification, never another checkout.
