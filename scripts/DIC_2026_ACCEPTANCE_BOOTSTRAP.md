# DIC 2026 database-free acceptance bootstrap

Implemented preparation only. **Status: INCOMPLETE — Python safety tests and Django smoke checks have not executed in this agent environment. No acceptance environment is declared ready.** The operator's approval for a future new disposable environment remains valid, subject to the mandatory provisioning gate.

## Components

- `backend/acceptance_bootstrap/config.py`: explicit immutable configuration, safe constant diagnostics, disposable-name/loopback/port guards, dedicated role separation, observed identity/privilege checks, unused-name rejection and ownership-receipt/write-target verification. The write guard validates supplied observations only; it is not a database query, signed approval or write authorization.
- `backend/config/settings/acceptance.py`: standalone Django settings. It neither imports ordinary settings nor reads `.env`. It reuses only AST-literal app/middleware/REST/password-policy definitions from `base.py`, never executing that file. It requires an active contained runtime before loading. All remaining settings are synthetic acceptance values or Django defaults.
- `backend/acceptance_bootstrap/db_backend/`: a PostgreSQL-derived backend whose connection methods always deny. Connections remain prohibited after runtime patches are removed. No migration, test-database creation, provisioning or fixture-insertion mode is supplied.
- `backend/acceptance_bootstrap/runtime.py`: process-local context blocking socket connections/sends/binds/DNS, standard HTTP/SMTP, subprocess creation and common shell-launch functions. Django attachment blocks database connection methods, disables SMTP delivery and replaces the application's actual `PaystackClient._request` at the provider boundary. Patches are restored on exit. Ordinary production/development behavior is untouched.
- `backend/acceptance_bootstrap/payments.py`: in-memory synthetic provider supporting success, failure, pending, abandoned and incorrect-amount responses; grouped total/metadata preservation; repeated callback verification; reproducible signed duplicate-webhook evidence; conflicting reference and unmocked-operation rejection. Settlement, callback authorization and persisted idempotency remain application responsibilities and require later E2E acceptance. No live endpoint is contacted.
- `backend/acceptance_bootstrap/fixtures.py`: deterministic, deep-copied, reviewed symbolic recipes for adults, minors, multi-child guardians, unrelated users, restricted officers/admin/finance/welfare actors, synthetic category prices/houses/bookings, QR cases, feedback/confidential notes, payments/reconciliation and two small synthetic timetable recipes. Unsupported academic classes are explicitly empty. No ORM loader or import of the 188 source timetable entries exists. Recipes are not directly loadable API/ORM fixtures; future mapping must use implemented serializers/services and disposable-only IDs after the gate.
- `scripts/test_dic_acceptance_bootstrap.py`: 15 standard-library database-free unit tests covering configuration, protected targets, ambient URLs/libpq rejection, roles, observed identity/privileges, existing-name protection, ownership/migration target guards, payment scenarios, repeated callback/webhook evidence, fixture validation and network/process denial/restoration.
- `scripts/validate_dic_acceptance_bootstrap.py`: executes those tests, tool-version checks, standalone Django setup/system checks, explicit database-denial assertion, intercepted locmem email, application-client mock payment verification and synthetic webhook signature validation. Failures return nonzero without raw operational exceptions/configuration/provider output. No database access is permitted.
- `scripts/validate_dic_acceptance_bootstrap.ps1`: one Windows entry point. It never provisions, connects, migrates, inserts, sends real messages or performs cleanup.

## Explicit configuration contract

Without `-SyntheticConfig`, all of these process environment variables are required:

| Variable | Requirement |
|---|---|
| `DIC_ACCEPTANCE_DATABASE` | Exactly `dic_2026_acceptance_` followed by 32 lowercase hexadecimal characters |
| `DIC_ACCEPTANCE_HOST` | Exactly numeric loopback `127.0.0.1` |
| `DIC_ACCEPTANCE_PORT` | Explicit decimal port in 1–65535; no silent default |
| `DIC_ACCEPTANCE_APP_ROLE` | Dedicated name prefixed `acceptance_` or `dic_acceptance_`; no production/live name |
| `DIC_ACCEPTANCE_PROVISION_ROLE` | Same naming restriction; must differ from application role |
| `DIC_ACCEPTANCE_PASSWORD` | Explicit, nonempty; never inherited from application variables or printed |
| `DIC_ACCEPTANCE_SECRET` | At least 50 characters, not the insecure Django prefix; never printed |

Nonempty `DATABASE_URL` and ambient libpq target/credential/service/options variables are rejected. Ordinary `DB_*` values are never consulted. No existing environment file or credential is modified. No secret belongs in command arguments, evidence or source control.

The observed-identity guard requires exact database/host/port/role and explicit non-superuser/non-CREATEROLE status; the application role must have no CREATEDB, while the separately approved provisioner must have creation privilege. These checks do not prove cross-database privileges, server identity or role approval without authoritative future observations. Do not automatically create roles or grant privileges to satisfy them.

The migration/write guard also requires a matching exact name, owner, creating role, run UUID, endpoint and newly-created receipt. No supplied dictionary can itself establish operator approval or authenticated database ownership. Future execution must independently obtain those observations after passing the provisioning gate.

## Containment limits and future gate

Current bootstrap is intentionally **database-free**. All local and remote sockets are denied, so no localhost server or PostgreSQL session is started either. The PostgreSQL-derived backend permanently rejects all connections; bypassing its methods or merely selecting ordinary development settings is not an approved way to enable E2E testing.

This is Python process-local containment, not an OS firewall or sandbox against malicious native extensions, previously captured networking primitives or arbitrary untrusted code. Run only reviewed project code. Before a future connected harness, separately implement/review an exact owned-resource connection gate, verify its negative tests, and enforce endpoint isolation. No shell subprocess or external worker escape should be enabled to make tests pass.

Email uses Django locmem; SMTP is also blocked at the backend/network layers. SMS/WhatsApp adapters, background delivery workers, OAuth, object storage and external video integrations are disabled. There is no outbound webhook sender. Only synthetic signed webhook bodies are prepared; they are not delivered to any server during bootstrap validation. Provider-hosted checkout UI and full browser checkout interception remain work for the later isolated E2E harness, not a claim of this provider-response mock.

Missing contact/donation functionality, academic classes, announcements and games are not implemented by this work. Existing application security and release guards remain unchanged.

Remaining PostgreSQL prerequisites: approved exact endpoint/server version; approved provisioner and restricted application roles/privileges; authoritative unused-name check; verified creation/ownership evidence and exact migration plan. No catalog query, connection or CREATE was attempted. Provisioning, migrations, fixture loading, local service/browser startup and eventual cleanup remain behind later gates; cleanup still needs separate approval. The 188 real timetable recipes remain unimported/unpublished.

## Actual verification

| Check | Actual result |
|---|---|
| PowerShell runner syntax | PASS via native PowerShell parser |
| PostgreSQL tools | PASS: pg_dump, pg_restore and psql each report 18.6 using `--version` only |
| Existing Step A receipt checksum | PASS: unchanged `c70fa32d1de80e6e426a2f90d8a030548cdf5bdd96c8063a822a076b05e27d9f` |
| Changed-file whitespace check | PASS |
| 15 bootstrap unit tests | NOT RUN: Python could not start its configured interpreter; access denied |
| Django checks, application payment adapter, signed webhook and locmem email smoke checks | NOT RUN: same interpreter blocker |
| Database/role/name identity, provisioning, migrations, fixture loading and seven E2E journeys | NOT RUN; not enabled by this runner |

One consolidated runner execution was attempted and returned nonzero when Python could not start. No alternate interpreter retry, installation or security-policy bypass was attempted. Source review and PowerShell syntax do not establish that the Python components pass runtime tests. Previous 231 backend, 217 frontend and 19 Step B passing results remain historical baseline; those suites were not rerun for this backend-only bootstrap change.

## One local verification command

From the repository root, use entirely synthetic, in-memory configuration (no real PostgreSQL role/password required):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_acceptance_bootstrap.ps1 -SyntheticConfig -PgBin 'C:\Program Files\PostgreSQL\18\bin'
```

This generates a syntactic disposable identity and synthetic credentials in process memory; it does **not** approve a role, check database-name availability, create the database or connect to it. Without `-SyntheticConfig`, it validates only explicitly supplied acceptance variables and still denies all connections. A successful bootstrap run proves database-free safety/mocks only, not provisioned environment or seven-journey readiness.

No database connections/writes, creation/drop, migrations, fixture inserts, timetable imports/publication, real payments, real emails/SMS, production calls, credential edits, deployment or data/evidence deletion occurred. No application feature, migration file or ordinary settings behavior was changed.
