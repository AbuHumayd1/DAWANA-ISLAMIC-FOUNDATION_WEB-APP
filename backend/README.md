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
configurable and do not trigger automatic allocation.

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
  alone does not grant access. The access token is signed using Django's secret
  key; do not log or share it.

The create response includes the server-calculated total, per-item fee
snapshots, a non-guessable order UUID, and the order access token. Repeating an
identical request with the same idempotency key returns the original order;
reusing the key for different request data returns HTTP 409. Do not log
idempotency keys or access tokens. Client-supplied totals are rejected.
Public registration endpoints have scoped anonymous request throttles. A
production deployment should configure a shared cache backend so throttling is
consistent across application workers.

The current React registration prototype does not yet select a configured
category or collect order-level primary-registrant details. The API requires
an explicit category ID per participant rather than inferring categories from
academic status. Frontend/API integration and any UI changes are outside this
backend milestone. Registration age limits, when configured, are evaluated on
the order's local registration date. Payment is not collected by these
endpoints.
