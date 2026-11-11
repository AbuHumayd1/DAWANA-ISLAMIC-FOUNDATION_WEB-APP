# Production Django Admin Bootstrap

Preparation only: do not run until the owner separately authorizes the production
operation. This does not deploy either service, change DNS, migrate, seed DIC,
activate registration, enable payments or reset an existing account.

## Before execution

1. Review/publish only the bootstrap workflow, Python script, synthetic test and
   this runbook through the approved publication process. Prevent unintended
   Render auto-deployment during publication. The existing reviewed
   `backend/config/github_schema_recovery.py` must be present on the selected
   main revision: its exact Render environment loader is reused, not replaced.
2. Confirm `production-initialize` still requires owner approval, restricts refs
   to main and prevents approval bypass where supported. A workflow environment
   reference alone does not configure GitHub required reviewers.
3. Retain the established environment secrets unchanged:
   `RECOVERY_DJANGO_ENV`, `RECOVERY_EXPECTED_HOST`, `RECOVERY_EXPECTED_SCHEMA`,
   `RECOVERY_EXPECTED_CLUSTER_ID`. The initialized schema and deployed release
   must match the reviewed main migration graph. Do not bypass a schema mismatch.
4. In that same GitHub environment, manually add:
   - `DJANGO_BOOTSTRAP_ADMIN_USERNAME`: the owner's chosen Django admin username.
   - `DJANGO_BOOTSTRAP_ADMIN_PASSWORD`: a unique password of 16–128 characters
     satisfying Django's configured password validators. Store it securely.
   Never supply credentials in workflow inputs, command arguments or chat.

No administrator email is required by the existing `accounts.User` model.
This workflow retains the recovery loader's existing pre-live payment checks;
it does not alter any payment setting.

## Authorized manual operation

Before authorizing production, require successful checks from the independent
`Admin bootstrap validation (no production access)` workflow. That workflow runs
on scoped pull requests or its own manual dispatch, has no production environment
or secret references, and never invokes the production bootstrap entry point.
Its synthetic job runs the original scenarios plus write-gate and log-redaction
tests on in-memory SQLite. Its PostgreSQL job repeats the scenarios against a
new UUID-named disposable database on a fresh, loopback-only PG18 cluster with a
synthetic self-signed TLS certificate. It also exercises real encrypted versus
plaintext connections, connection refusal and concurrent attempts with equal or
different usernames. Only test credentials are hardcoded; production endpoints
and settings are rejected. No keys, database files, logs or artifacts are uploaded.
The original 11 scenarios remain; additional security/concurrency cases extend
the suite. The PostgreSQL job verifies its private data directory and cluster ID
before creating the disposable database and removes that database afterward.

After explicit owner authorization, open Actions > Production Django Admin
Bootstrap > Run workflow, select main and enter `CREATE INITIAL SUPERUSER` in
the approval input. No username or password belongs in that input.

The unprotected validation job installs the reviewed backend requirements and
runs `python -I -B scripts/test_admin_bootstrap.py`. It uses only an in-memory
synthetic SQLite database, real Django password hashing and blocked network
connections. It does not load dotenv or Render settings.

Only after validation succeeds can the protected bootstrap job proceed. The
owner reviews/approves `production-initialize` access. The production script:

- Refuses non-manual events, non-main refs and GitHub rerun attempts.
- Reuses the established Render settings/environment loader and verifies the
  configured database/role/port/host plus `verify-full`.
- Verifies actual database, session/current role, schema, PostgreSQL system ID
  and an encrypted connection. It also binds the user table to the expected
  schema and refuses pending/conflicting/inconsistent migration history.
- Validates/hashes the password through Django outside the write-lock window.
- Rechecks identity/TLS, acquires the existing recovery advisory lock and a
  bounded user-table write lock, then refuses a case-insensitive username match
  or ANY existing superuser. It never resets credentials or elevates an account.
- Inserts exactly one active/staff/superuser through the configured user model
  in one transaction, verifies the stored hash/flags and commits. Failure rolls
  back that transaction. No migration/application data operations are called.
- Emits only `CREATED` or a fixed `STOP` category. No exception text, username,
  password, SQL, host, connection string or model validation details are logged.

On CREATED, the owner can sign in at the existing backend `/admin/` using the
secret credentials. This script does not sign in or change camp settings.

## Retire and handle failures

After confirming admin access, remove the two bootstrap secrets and retire the
bootstrap workflow through a reviewed change. Do not delete the new admin.
The existing username/superuser is the state-based repeat guard; this is not a
permanent execution receipt surviving deletion of all superusers. Removing the
secrets and retiring the workflow completes the one-time operational procedure.

On STOP, inspect the fixed category without sharing credentials. Existing
accounts are left untouched. Do not rerun jobs or reset a password through this
workflow. After any ambiguous post-commit failure, verify whether the admin
already exists before considering a fresh, separately approved dispatch.

The independent PostgreSQL tests exercise the same advisory/table lock helper and
the same insert logic as production. Production database/role/host/schema/cluster
guards remain mandatory in the production orchestration; synthetic database
names are not accepted by that orchestration. Tests do not prove production
connectivity or the GitHub environment's external reviewer configuration.
No production access or operation is authorized merely by passing tests.
