# DA'WANA full application

Follow [ZEVCLOUD_DEPLOYMENT.md](ZEVCLOUD_DEPLOYMENT.md): native Nixpacks builds,
one same-origin Gunicorn/Django/React service and one durable worker service,
using the existing PostgreSQL 18 database. No custom Dockerfile, Nginx,
Supervisor or CIDR gateway contract is needed on the recommended path.

This is full registration, verified payments, automatic housing, email recovery,
portal and Admin operation. Live Paystack still requires separate approval.
Production deployment and acceptance remain unverified; see the guide's gates.

The old container files remain under `ops/container/` for rollback. Do not mix
their configuration with the native services.
