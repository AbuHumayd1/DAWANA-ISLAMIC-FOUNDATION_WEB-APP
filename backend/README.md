# Dawana backend

The Django project lives beside `dawana-platform/` and uses modular settings:
`config.settings.development` by default and `config.settings.production` for
production configuration. The initial custom user model is `accounts.User`.

## Local setup

From the repository root, create and activate a Python 3.13 virtual environment,
then install the pinned dependencies:

```powershell
py -3.13 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Set a unique `DJANGO_SECRET_KEY` and the development database password in
`backend\.env`. Keep that file local and never commit it.

The PostgreSQL application role should own `dawana_dev` and
`test_dawana_dev`, and must not be a superuser or have `CREATEDB`. Create both
databases as an administrator before running Django tests. The application
role needs ownership of the dedicated test database so Django can apply its
migrations; tests must never use the development database.

```powershell
python backend\manage.py check
python backend\manage.py makemigrations
python backend\manage.py migrate
python backend\manage.py test health dic --keepdb
```

The public health endpoint is `GET /api/v1/health/`. Do not create a default
administrator with a hardcoded password; create one interactively with
`python backend\manage.py createsuperuser` when needed.

## DIC configuration

The `dic` app provides historical camp editions, edition-specific participant
categories and NGN fees, and configurable houses. No official category names,
eligibility ages, fees, house names, or capacities are preloaded. Categories
use `fee_ngn` as the current configured amount; a future registration order
must copy that amount into its own immutable fee snapshot when the order is
created. House capacity may remain blank until confirmed. Reserve houses and
the separate fathers/authorised-male-administrators accommodation are
configurable. Allocation is disabled by default and does not run during
registration or payment.

House allocation is managed from each edition's Django Admin allocation
console. The supported automatic strategy balances occupancy across eligible
houses, with stable participant and house ordering. An administrator must
select that strategy and separately record committee approval before batch
allocation is available. Any house configuration change invalidates the
approval fingerprint until the strategy is approved again. Batch allocation
is atomic: if a selected participant is unpaid, ineligible, or cannot fit, the
batch is rejected without partial assignments.

Assign staff only the dedicated allocation permissions needed for their
duties: `dic.can_allocate_participants`, `dic.can_approve_allocation_strategy`,
`dic.can_activate_reserve_houses`, `dic.can_reassign_allocations`,
`dic.can_release_allocations`, and
`dic.can_authorize_dedicated_accommodation`. Standard Django Admin view/change
permissions for the relevant configuration models may also be needed to access
their changelists. Reserve houses are unavailable until explicitly authorized
with a reason. Dedicated accommodation eligibility is an explicit
administrator-only participant flag; it is never inferred from sex, age, or
marital status. Reassignments and releases require reasons and retain history.

House `eligibility_rules` are intentionally fail-closed: because no approved
rule format or evaluator has been defined, any house with non-empty rules is
not allocatable through either batch or manual assignment. Define and approve
the rule schema before using such restrictions.

The backend apps are nested under `backend/`, so specify their labels when
running the test suite from the repository root. `--keepdb` reuses the
pre-created `test_dawana_dev` database owned by `dawana_app`; this role does
not need `CREATEDB`. Django settings reject a test database name that equals
the configured development database name.

## Registration API

The registration endpoints are versioned under `/api/v1/dic/`:

- `GET /api/v1/dic/registration-options/` returns the active edition, its
  registration-window state, and active categories with their configured NGN
  fees and optional age bounds.
- `POST /api/v1/dic/orders/` creates an order and its participant registrations.
  Send a cryptographically random UUIDv4 in the `Idempotency-Key` header.
  Each participant supplies a `category_id` and the required fields represented
  by the current prototype: `full_name`, `address`, `phone`, `email`,
  `date_of_birth`, `sex`, `height_cm`, `weight_kg`, `academic_status`,
  `occupation`, and `marital_status`. An optional `primary_registrant` object
  can contain `full_name`, `phone`, and `email`; none are required.
- `GET /api/v1/dic/orders/{order_id}/` returns an order only with its
  `Authorization: Bearer <access_token>` credential. The UUID order reference
  alone does not grant access. The opaque access token is stored only as a
  one-way digest, expires after 30 days, and is rotated when the same
  idempotent order-creation request is replayed. The previous token is invalid
  after rotation. Django Admin staff can revoke order access explicitly; never
  log or share access tokens.

The create response includes the server-calculated total, per-item fee
snapshots, a non-guessable order UUID, and the order access token. Replaying an
identical request with the same idempotency key returns the original order and
rotates its access token; reusing the key for different request data returns
HTTP 409. Do not log idempotency keys or access tokens. Client-supplied totals
are rejected.
Public registration endpoints have scoped anonymous request throttles. A
production deployment should configure a shared cache backend so throttling is
consistent across application workers.

The React DIC registration flow retrieves configured categories and requires
an explicit category ID per participant rather than inferring categories from
academic status. The existing form does not collect order-level
primary-registrant details; the API keeps those optional and uses the first
participant's email for Paystack if no primary registrant email is available.
Registration age limits, when configured, are evaluated on the order's local
registration date.

## Frontend development connection

The frontend's `VITE_API_BASE_URL` defaults to `/api/v1`. Vite proxies `/api`
to `http://127.0.0.1:8000` by default; set `DJANGO_API_PROXY_TARGET` when the
local Django server uses another address. Copy `dawana-platform/.env.example`
to `dawana-platform/.env` to override the API base URL. For deployments,
prefer a same-origin reverse proxy or set an absolute API URL and explicitly
configure `DJANGO_CORS_ALLOWED_ORIGINS` with the exact frontend origins. CORS
is limited to `/api/`, credentials are disabled, and production defaults to no
allowed cross-origin sites. Never use wildcard CORS origins. Local Django
development defaults to the Vite origins `http://localhost:5173` and
`http://127.0.0.1:5173`. The registration API uses bearer authorization
without cookies; CORS explicitly permits the UUIDv4 `Idempotency-Key` and
bearer `Authorization` headers. No frontend CSRF token is sent; keep the Django
Admin and any cookie-authenticated endpoints under normal CSRF protection.

The browser keeps the order bearer token only in React memory. A tab-scoped
`sessionStorage` draft, retained for at most 30 minutes to support order
idempotency and recovery after reload, contains registration details and the
order/payment references but never the bearer token or Paystack checkout URL.
On reload, the user explicitly restores checkout by replaying the same order
request with its UUIDv4 idempotency key; the backend rotates the access token
and returns the existing order. The draft is removed after trusted payment
verification or when the user resets the registration. Users should keep the
checkout tab open until verification completes.

## Secure registration recovery

The DIC page provides **Already registered? Recover your registration**. Recovery
uses the participant or primary-registrant contact already stored on non-cancelled
orders; it does not create registrations. A verified contact can select only the
orders matched to that contact and stored on its challenge. Multiple children or
orders sharing one verified contact are listed only after the one-time code is
accepted.

The versioned recovery endpoints are:

- `GET /api/v1/dic/recovery/channels/` returns channel availability and the
  optional configured WhatsApp support link; it never checks a contact.
- `POST /api/v1/dic/recovery/challenges/` accepts `channel` and `contact`.
- `POST /api/v1/dic/recovery/challenges/{challenge_id}/resend/` accepts the
  same channel and contact.
- `POST /api/v1/dic/recovery/challenges/{challenge_id}/verify/` accepts the
  six-digit `code` and returns a short-lived, scoped recovery grant.
- `GET /api/v1/dic/recovery/orders/` requires that grant as a bearer token and
  returns minimal summaries for only the grant's eligible orders.
- `POST /api/v1/dic/recovery/orders/{order_id}/restore/` redeems that grant for
  one selected order and returns its rotated order-access token and authoritative
  payment status. A grant can restore each listed order once.

After delivery, OTPs and grant values are stored only as keyed hashes; queued
delivery payloads are encrypted with Fernet and cleared after processing.
Contact identifiers used for throttling/matching are keyed hashes as well.
Codes expire after 10 minutes, are single-use, and allow at most five
verification attempts. Resends invalidate the prior code and are subject to a
60-second cooldown. Database-backed contact and source-address request buckets
enforce limits across application workers; the regular DRF scoped throttles
remain an additional layer. The source address uses `REMOTE_ADDR`; configure a
trusted reverse proxy to pass the actual client address safely rather than
trusting arbitrary forwarded headers.

Recovery requests are queued before the generic response is returned; the API
does not wait for a delivery provider, preventing provider latency from
revealing whether a contact matches a registration. Delivery payloads are
Fernet-encrypted at rest and cleared after processing. The worker suppresses
messages for unknown contacts, so they receive the same response but no code.
Delivery failures are stored as failed and logged with the channel only—never
contact details or codes. Enable the worker only when a supervised scheduler
is running `python backend\manage.py send_dic_recovery_messages` repeatedly
(recommended interval: five seconds). The command processes a bounded batch
and exits; multiple worker processes may run concurrently. Channels are
reported unavailable unless the worker flag and a valid encryption key are
configured. Generate a key with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
and store it only in the server environment as `DIC_RECOVERY_ENCRYPTION_KEY`.
Losing or rotating this key invalidates queued deliveries, which will then be
marked failed; it does not affect sent codes or recovery grants. The periodic
cleanup command also clears encrypted payloads for expired deliveries. Run
`python backend\manage.py cleanup_dic_recovery` periodically to remove recovery
records and rate-limit rows older than one day. This does not modify registration,
payment, or allocation records.

All recovery channels are disabled by default. Email becomes available only
when `DIC_EMAIL_RECOVERY_ENABLED=True`, a non-console Django email backend is
configured, an SMTP host is present when using SMTP, and `DEFAULT_FROM_EMAIL` is
set, and `DIC_RECOVERY_DELIVERY_WORKER_ENABLED=True` with a valid
`DIC_RECOVERY_ENCRYPTION_KEY`. The development console and in-memory email
backends are deliberately not accepted for recovery because they expose
message bodies locally.

SMS requires `DIC_SMS_RECOVERY_ADAPTER` to name a deployment-provided Python
class with a `send(destination, code)` method. Select only an approved provider
and implement its credential handling, timeouts, and safe error behavior before
enabling it; the adapter is invoked by the supervised recovery-delivery worker.

WhatsApp OTP uses the official WhatsApp Business Cloud API template-message
endpoint. Configure `DIC_WHATSAPP_ACCESS_TOKEN`,
`DIC_WHATSAPP_PHONE_NUMBER_ID`, `DIC_WHATSAPP_OTP_TEMPLATE`, and the approved
template language. The template must be approved for authentication codes and
support the single body parameter used by the adapter. The API version,
provider timeout, and verified support number are set with
`DIC_WHATSAPP_API_VERSION`, `DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS`, and
`DIC_WHATSAPP_SUPPORT_NUMBER`. WhatsApp recovery remains unavailable until all
OTP credentials, the approved template, and the recovery worker configuration
are set. A support chat is never treated as identity verification.

Keep all provider credentials in the server environment. Do not use browser
storage, query strings, analytics, or client logs for OTPs, recovery grants, or
order bearer tokens. Recovery never starts payment automatically; the user must
explicitly request checkout, and only the existing Paystack verification flow
can confirm payment. Administratively revoked order access cannot be restored
through this recovery flow.

## Paystack test-mode payments

Payment initiation and verification are available under `/api/v1/dic/`:

- Configure public camp dates, venue, registration windows, and prices in
  Django Admin. DIC dates and cutoff inputs use `Africa/Lagos`. Early-bird and
  regular fees are stored per category; the edition-wide cutoff determines
  which quote is available. Do not open registration until all approved fees,
  deadline, and registration dates are configured.
- If an unpaid early-bird order reaches its cutoff, payment initialization
  returns a signed, short-lived repricing quote. The registrant must explicitly
  accept it through `POST /orders/{order_id}/pricing/accept/` before another
  payment attempt is created. Old Paystack authorizations are not assumed to be
  cancellable; a later charge against a superseded early-bird quote is held for
  reconciliation and does not confirm the order.
- `POST /orders/{order_id}/payments/initialize/` requires the order's bearer
  access token and returns a payment reference, status and Paystack checkout
  URL. The amount is derived exclusively from the current accepted immutable
  price revision and converted from NGN to integer kobo on the server. The
  billing email is the optional primary registrant email, falling back to the
  first participant's required email.
- `POST /orders/{order_id}/payments/{reference}/verify/` requires the same
  bearer token and verifies the reference directly with Paystack. A verified
  success must include a valid provider `paid_at` timestamp as well as a
  matching reference, amount and NGN currency. The provider-confirmed
  completion time, not order creation time or callback arrival time, enforces
  the early-bird cutoff. Missing or out-of-window timestamps are held for
  reconciliation. Browser redirects are not trusted.
- `POST /payments/paystack/webhook/` verifies `X-Paystack-Signature` against
  the exact request body with HMAC-SHA512, deduplicates events by a body digest,
  and independently verifies `charge.success` with Paystack before settlement.
  Raw webhook bodies and payment-card data are not stored.

Configure only a Paystack **test secret key** in `PAYSTACK_SECRET_KEY`.
`PAYSTACK_MODE` must remain `test`; live keys are rejected. Configure
`PAYSTACK_CALLBACK_URL` as an absolute HTTPS URL when using browser checkout,
and optionally adjust `PAYSTACK_HTTP_TIMEOUT_SECONDS` (1-30, default 10).
Values belong in the untracked `backend/.env`; never print or commit them.
Payment endpoints are throttled. Production must use a shared cache for
consistent anonymous throttling across workers and must configure Paystack to
send webhooks to the public HTTPS webhook URL. Failed webhook delivery can be
reconciled by the authenticated order-access holder calling the verification
endpoint again. Payment attempts and webhook audit records are read-only in
Django Admin.

Automated tests mock all provider calls; they never make real payment requests.
Live keys and transactions are intentionally unsupported in this milestone.
To set up the confirmed DIC 2026 listing when no edition exists, run
`python manage.py setup_dic_2026`. The command creates a draft listing with the
confirmed 23 December 2026–1 January 2027 dates and Faisal Omar Memorial School
venue; it does not configure registration dates, categories, fees, directions,
or open registration. It leaves existing editions unchanged.
For Paystack test-mode verification, configure the test key locally, set an
HTTPS callback URL, start the backend, create an order and initialize checkout.
Complete a test-mode payment using Paystack's current test instructions, then
verify through the API or a correctly signed test webhook and confirm the
result in Django Admin. Never use real card details or enable live mode here.
