# DA'WANA: combined ZevCloud full-application release

Local implementation only. No production action or live activation has occurred.
This is the full-launch configuration; ZEVCLOUD_DEPLOYMENT.md describes the
separate website-only maintenance mode. Existing local changes remain preserved.

## Builder

Root/context `.`; Dockerfile `Dockerfile`; target blank or `runtime`; platform
`linux/amd64`; service port `8080`; static-site mode off; no command overrides or
required build arguments. Use Dockerfile ENTRYPOINT. ZevCloud supplies PORT.
Default image tags are mutable; CI can still provide digest-pinned NODE_IMAGE,
PYTHON_IMAGE and SOURCE_REVISION. Record the released commit and image digest.

## Minimal full-application environment

| Variable | Required value |
| --- | --- |
| PUBLIC_HOST | `dawanaislamicfoundation.org` |
| DJANGO_SECRET_KEY | Independent random secret, at least 50 characters |
| DATABASE_URL | Existing purchased PostgreSQL connection; restricted role, certificate-matching hostname |
| DB_SSLROOTCERT | Conditional: absolute mounted trusted CA file path; omit only after system/libpq trust is proved sufficient |
| TRUSTED_EDGE_CIDRS | Unresolved: ZevCloud-confirmed immediate proxy networks; never guess |
| EDGE_TRUST_VERIFIED | `1` only after ingress guarantees below are proved |
| DAWANA_WEBSITE_ONLY | `false` for the separately authorized full application release |
| DIC_AUTOMATION_ACTOR_ID | Existing active staff service-user PK with the three permissions below |
| DIC_RECOVERY_ENCRYPTION_KEY | Stable valid Fernet key; preserve securely in backups |
| DEFAULT_FROM_EMAIL | Sender address/domain verified with the chosen email provider |
| RESEND_API_KEY | Resend sending API secret for the included HTTPS email adapter |
| PAYSTACK_MODE | `test` while live release is unapproved |
| PAYSTACK_LIVE_ENABLED | `false` while live release is unapproved |
| PAYSTACK_SECRET_KEY | Omit until an approved isolated test or live activation; never put it in Vite/build arguments |

The entrypoint derives production settings, exact hosts/CSRF, empty CORS,
verify-full database TLS, internal loopback trust, and these full-mode defaults:

```
DIC_BACKGROUND_WORKER_ENABLED=true
DIC_PORTAL_ACCOUNTS_ENABLED=true
DIC_EMAIL_RECOVERY_ENABLED=true
DIC_RECOVERY_DELIVERY_WORKER_ENABLED=true
EMAIL_BACKEND=config.https_email.EmailBackend
DIC_PORTAL_EMAIL_VERIFY_URL=https://dawanaislamicfoundation.org/dic/participant
DIC_PORTAL_FRONTEND_URL=https://dawanaislamicfoundation.org/dic/participant
PAYSTACK_CALLBACK_URL=https://dawanaislamicfoundation.org/dic/register/payment-return
DIC_MEMORY_STORAGE=disabled
```

No SMTP variables, separate scheduler service, Redis or Celery are required.
Resend is an optional implemented HTTPS transport, not a provisioned account.
An existing accepted HTTPS Django email backend can instead be supplied through
EMAIL_BACKEND. Its credentials/configuration must be supplied and accepted too.
Do not use console/locmem delivery in production. ZevCloud documents outbound SMTP
blocking. Sender verification and real delivery remain external acceptance gates.

PAYSTACK_WEBHOOK_SECRET stays omitted for the existing secret-key signature path
unless the actual account uses the timestamped signing format supported by code.
After separate approval only, live collection requires PAYSTACK_MODE=live,
PAYSTACK_LIVE_ENABLED=true and the existing matching live secret. Never collect
production payments with test credentials. Test-mode production receipts do not
grant production portal entitlement.

Webhook: `https://dawanaislamicfoundation.org/api/v1/dic/payments/paystack/webhook/`.
The callback above is a frontend route, not the webhook or proof of payment.

## Automatic processes

Supervisor runs Nginx, Gunicorn and `python manage.py run_dic_workers` in one
container. The worker prioritizes the existing recovery/portal OTP commands, runs
bounded existing housing and email followups, and repeats after 15 seconds. No
routine administrator action is needed. A missing/stale worker heartbeat makes
health unready; a worker process exit fails the container. Website-only mode
does not start application workers.

The automation actor needs only `dic.can_process_housing_queue`,
`dic.can_allocate_participants`, `dic.can_approve_housing_guardians`. Configure once;
use an unusable password and no superuser privileges. Do not grant Admin login
credentials to the worker. Creation/permission assignment is a separately
approved database action, not part of container startup.

Explicit guardian declarations use participant identities in the same booking.
Automatic approval requires a verified booking email/account, the guardian's
matching name/email, exact adult age (18+), female accommodation eligibility,
dependent age 0-5 and independently verified settlement for the shared booking.
Missing, cross-booking, conflicting or ambiguous identities stay held. Only
guardian-awaiting-approval holds are automatically requeued after validation;
capacity holds and supervised releases are preserved. Tutors keep their existing
authorized no-payment portal/recovery route and offline accommodation.

## Release order: separate authorization required

1. Obtain passing backend policy/PostgreSQL 18 acceptance and container smoke
   results for this exact reviewed commit. Existing backend acceptance workflow
   discovers new tests and uses disposable PostgreSQL 14/18. No production test DB.
2. Verify ZevCloud ingress: exact socket-peer CIDRs, valid managed HTTPS and HTTP
   redirection, replacement of X-Forwarded-Proto and X-Real-IP, no direct bypass.
   An SSL certificate alone does not prove this contract. Verify DB hostname/CA
   with verify-full and mount the CA if required. No TLS downgrade is permitted.
3. Stage the reviewed image in website-only mode for schema preparation, without
   public registration or payment. Confirm the actual database/cluster/role and
   backup/restore procedure. Build/start commands never migrate or seed.
4. Use existing `release_migrations` to create the exact pending plan for approval:

   ```
   python manage.py release_migrations --database-name <name> --hostname <host> --port <port> --role <migration-role> --cluster-id <verified-cluster-id> --manifest-file <new-plan.json>
   ```

   Pending migrations deliberately return an error after writing the plan. Review
   the full plan, including 0037/0038 and any existing pending migrations. Only
   after approval, repeat the same identity arguments with
   `--apply-approved-plan --approval-file <approved.json>`. Do not add this to startup.
5. Separately approve/create `dawana_release_cache`, the least-privilege automation
   actor, staff access and the approved active edition/pricing/dates. Verify eight
   2026 participant houses, four per sex, capacity 30, housing reference
   2026-12-23 and the approved balanced-strategy fingerprint. Preserve tutor policy.
   Existing setup_dic_2026 creates a draft, not an open registration release.
6. Validate real HTTPS email and contact recovery against owned test identities;
   confirm account proof, duplicate callbacks/webhooks, pending/retry status,
   guardian group capacity and valid portal scope in the isolated acceptance
   environment. Never run the suite against production.
7. After separate deployment authorization, select full-mode configuration. Before
   opening registration, run `python manage.py check_dic_launch` (read-only).
   It requires the approved registration window/status, schema/cache, actor,
   authenticated DB TLS and approved inventory; it never changes them. Verify
   `/_container/ready`, frontend deep links, secure cookies, CSRF and worker activity.
8. Live Paystack activation needs a separate explicit approval after those checks.
   Configure the existing live account/callback/webhook, run
   `python manage.py check_dic_launch --require-live`, then conduct only the
   separately authorized live acceptance transaction before inviting registrants.

## Current unresolved blockers

Local Python execution and WSL are denied; Docker is unavailable. Backend,
PostgreSQL concurrency, migration graph and container startup are not locally
verified. ZevCloud proxy/header guarantees, DB CA/hostname mounting, real email
credentials/sender verification, production schema/cache/actor/edition state and
live Paystack acceptance remain unverified. No production service, migration,
DNS or payment was changed. Do not mark this release ready until these gates pass.
