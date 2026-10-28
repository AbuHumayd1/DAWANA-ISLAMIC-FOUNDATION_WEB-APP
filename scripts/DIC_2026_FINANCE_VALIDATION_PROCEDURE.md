# DIC 2026 — isolated Finance validation and migration preparation

Prepared only. **No database creation, migration, test fixture write or cleanup has been executed.** Application code and historical migrations are unchanged. Python is reported working in the developer's normal VS Code PowerShell; this procedure must run there. The new helper itself has not been runtime-validated inside Codex.

Files prepared:

- `scripts/validate_dic_finance.py`: constrained validation helper; no protected-database write action.
- This procedure: exact commands, expected plans, test manifest and release checks.

## 1. Test manifest and database requirements

`backend/dic_finance/tests.py::FinancePolicyTests` has exactly **19 database-free `SimpleTestCase` tests**. ORM interactions are mocked; command tests call the undecorated function to avoid transactions. The helper additionally blocks Django connection establishment during this phase.

```text
dic_finance.tests.FinancePolicyTests.test_money_exact_minor_units
dic_finance.tests.FinancePolicyTests.test_money_rejects_nonfinite_negative_fractional_and_oversized
dic_finance.tests.FinancePolicyTests.test_finance_requires_active_staff_operations_and_finance
dic_finance.tests.FinancePolicyTests.test_action_permission_is_independent
dic_finance.tests.FinancePolicyTests.test_verified_receipt_uses_trusted_payment_evidence
dic_finance.tests.FinancePolicyTests.test_pending_failed_duplicate_and_mismatch_are_not_income
dic_finance.tests.FinancePolicyTests.test_refunded_and_cancelled_orders_are_excluded
dic_finance.tests.FinancePolicyTests.test_missing_provider_id_or_amount_mismatch_is_exception
dic_finance.tests.FinancePolicyTests.test_invalid_payment_timing_is_excluded
dic_finance.tests.FinancePolicyTests.test_formula_injection_is_escaped_by_shared_export_utility
dic_finance.tests.FinancePolicyTests.test_duplicate_order_and_provider_credit_count_once
dic_finance.tests.FinancePolicyTests.test_documented_reversal_never_credits_revenue
dic_finance.tests.FinancePolicyTests.test_creator_cannot_approve_own_expense
dic_finance.tests.FinancePolicyTests.test_approval_does_not_mark_expense_paid_and_is_audited
dic_finance.tests.FinancePolicyTests.test_stale_workflow_version_is_rejected
dic_finance.tests.FinancePolicyTests.test_api_rejects_anonymous_before_finance_storage
dic_finance.tests.FinancePolicyTests.test_budgets_and_approved_commitments_are_not_cash_expenses
dic_finance.tests.FinancePolicyTests.test_only_verified_income_and_paid_expense_count
dic_finance.tests.FinancePolicyTests.test_pending_failed_attempts_are_counts_not_revenue
```

`backend/dic_finance/test_integration.py::FinanceIntegrationTests` has exactly **four PostgreSQL-dependent `TestCase` tests**:

```text
dic_finance.test_integration.FinanceIntegrationTests.test_expense_approval_payment_reversal_and_audit
dic_finance.test_integration.FinanceIntegrationTests.test_budget_revision_replaces_allocation_without_cash_effect
dic_finance.test_integration.FinanceIntegrationTests.test_cross_edition_category_cannot_be_used
dic_finance.test_integration.FinanceIntegrationTests.test_stale_version_and_unauthorised_action_do_not_write
```

These create synthetic editions/users/Finance entries only in the disposable database, with transaction rollback between tests. They do not exercise all real payment settlement, receipt download, CSV endpoint, browser, concurrent mutation or role-assignment scenarios. A passing 23-test run is focused Finance validation, not full-platform acceptance.

The helper hardcodes this manifest and aborts on missing/added tests, import errors, skips, failures, incomplete execution or an unexpected test database declaration.

## 2. Isolation and side-effect safeguards

Protected databases: **`dawana_dev`** and **`test_dic_portal_2026_local`**. Neither is connected to during disposable test execution. The optional development-plan action connects only to `dawana_dev`, read-only, for migration inspection.

The existing environment loading convention is reused: django-environ reads `backend/.env`, preserving process-variable precedence. Only loopback PostgreSQL credentials are retained. The helper does not reuse `portal_test_booking.configure()` because that function deliberately fixes the protected OTP database, nor the older general validation runner because it creates databases and uses unrestricted Django setup.

The new disposable name must match:

```text
test_dic_finance_<14-digit UTC timestamp>_<8 lowercase hex characters>
```

Safety controls:

- Refuse both protected names, all other name formats, remote hosts, non-PostgreSQL backends, non-development settings, extra database aliases and existing databases.
- Use only the local role already configured; never grant CREATEDB, change passwords or change server/security settings. That role must already have permission to create a database.
- Bind host and host address explicitly to loopback, with connect/statement timeouts.
- Store a non-secret local creation receipt containing database identity, owner, OID, unique database-comment marker and migration-file digest. Verify it before use/drop. No credentials are written to this receipt.
- Apply only `MigrationExecutor.migrate([('dic_finance','0001_initial')], plan=reviewed_plan)` to the fresh empty disposable database. Never invoke `manage.py test`, `DiscoverRunner`, `setup_databases`, `create_test_db`, unrestricted migrate, `flush`, `loaddata` or `--keepdb`.
- Run the explicit Django `TestCase` objects via `unittest`, preserving Django's transaction setup/rollback without invoking Django database creation or automatic migration setup. No post-migrate permission/role population is needed: these four tests explicitly use synthetic superusers. This does not validate production permission assignments.
- Set Paystack to synthetic test credentials; disable delivery flags/SMS/WhatsApp, use in-memory email, disable external storage/metadata retrieval and use a synthetic Django key inside each helper process only. Existing server/worker environments and `.env` remain untouched.
- Block HTTP/Paystack network entry points, subprocess launches and Python socket connections other than the configured local PostgreSQL port. Policy tests additionally forbid Django database connections. PostgreSQL's native connection is constrained by the explicit local DSN and database checks.
- Never start an email worker, frontend/server, fixture helper, live provider verification or background task.

No automatic cleanup follows a failure. The disposable database is retained for diagnosis; cleanup is explicit and refuses active connections rather than terminating them.

## 3. Copy-paste PowerShell — preflight and policy tests

Run in **normal VS Code PowerShell at repository root**. These first commands do not create/connect to any application database; preflight inspects migration files and Django models with `MigrationLoader(None)`.

```powershell
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath '.\backend\manage.py')) {
    throw 'Start from the Dawana repository root.'
}
$financePython = (Resolve-Path -LiteralPath '.\backend\.venv\Scripts\python.exe').Path
$financeRunner = (Resolve-Path -LiteralPath '.\scripts\validate_dic_finance.py').Path
$financeStamp = [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
$financeSuffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$financeDb = "test_dic_finance_${financeStamp}_${financeSuffix}"
$financeReceipt = Join-Path ([IO.Path]::GetTempPath()) "$financeDb.receipt.json"

& $financePython -B -c 'import sys; print(sys.executable); print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'Python failed. Stop before database operations.' }

Write-Host "Disposable database: $financeDb"
Write-Host "Creation receipt: $financeReceipt"
Write-Host 'Protected: dawana_dev and test_dic_portal_2026_local'

& $financePython -B $financeRunner preflight --database $financeDb
if ($LASTEXITCODE -ne 0) { throw 'Graph/model/system checks failed. Do not create a database.' }

& $financePython -B $financeRunner policy --database $financeDb
if ($LASTEXITCODE -ne 0) { throw 'Policy tests failed or were incomplete. Stop here.' }
```

Expected: system checks succeed; dependency plan contains Finance plus approved prerequisites only; **19 policy tests pass, no skips**. These are expected results, not results already observed.

Review the printed plan before proceeding. Preserve the terminal variables for the next block. If the helper reports STOP, stop and investigate; do not edit its allowlist to force a pass.

## 4. Copy-paste PowerShell — create, target schema, test, verify

**This block performs database mutations only on the newly generated disposable name.** It is provided for the developer to execute, not executed during preparation. Do not substitute either protected database or an existing test database.

```powershell
if (-not $financeDb -or $financeDb -notmatch '^test_dic_finance_[0-9]{14}_[a-f0-9]{8}$') {
    throw 'Missing or unexpected disposable name. Rerun preflight with a fresh name.'
}
if ($financeDb -in @('dawana_dev', 'test_dic_portal_2026_local')) {
    throw 'Protected database refused.'
}
if (Test-Path -LiteralPath $financeReceipt) {
    throw 'Creation receipt already exists. Do not overwrite/reuse this run.'
}

& $financePython -B $financeRunner create --database $financeDb --receipt $financeReceipt
if ($LASTEXITCODE -ne 0) { throw 'Disposable creation failed. Stop; no reuse or fallback database.' }

& $financePython -B $financeRunner integration --database $financeDb --receipt $financeReceipt
if ($LASTEXITCODE -ne 0) { throw 'Targeted migration or integration tests failed. Retain the disposable database for diagnosis.' }

& $financePython -B $financeRunner verify --database $financeDb --receipt $financeReceipt
if ($LASTEXITCODE -ne 0) { throw 'Post-test database/schema verification failed. Stop.' }
```

Expected: database identity printed before schema application; target plan unchanged since creation; only target prerequisites applied; **four integration tests pass, no skips**; exact applied migration set confirmed before/after testing; no feedback/welfare tables or migration 0027.

The integration action refuses a nonempty database. Do not rerun it against a partly migrated/failed run or manually clear it. Retain for diagnosis, then explicitly clean up and begin a fresh preflight/name. If creation succeeded but a receipt could not be written (e.g. filesystem failure), stop and ask for manual identity review; do not guess a cleanup target.

## 5. Disposable cleanup

Run separately after reviewing results or after preserving failure diagnostics. This drops **only** the database whose name, host/port/user, OID, owner and database-comment marker match the receipt. It does not flush any database or force disconnects.

```powershell
Write-Host "Cleanup target: $financeDb"
if ((Read-Host 'Type the exact disposable database name to approve cleanup') -cne $financeDb) {
    throw 'Cleanup not approved.'
}
& $financePython -B $financeRunner cleanup --database $financeDb --receipt $financeReceipt
if ($LASTEXITCODE -ne 0) { throw 'Cleanup refused or failed. Do not force it or change database names.' }
```

The small receipt is retained for audit. If you restart PowerShell, recover the exact database name and receipt path from the previous output; the helper validates both. Never select a database by “first matching name”, delete all databases with a prefix, or use `DROP ... FORCE`.

## 6. Expected migration plan

Finance's direct dependencies are:

```python
('dic', '0026_house_score_transaction')
migrations.swappable_dependency(settings.AUTH_USER_MODEL)
```

The configured user model is `accounts.User`, resolving through `accounts.0001_initial` and auth/contenttypes prerequisites. The prepared helper checks that the direct dependency tuple is exactly dic 0026 plus `accounts.__first__` and stops if it changes.

For a fresh disposable database, expect the target closure to contain:

| Application | Expected migrations |
|---|---|
| contenttypes | `0001_initial`, `0002_remove_content_type_name` |
| auth | Existing standard `0001_initial` through `0012_alter_user_first_name_max_length` |
| accounts | `0001_initial` |
| dic | Existing `0001_initial` through `0026_house_score_transaction` |
| dic_finance | `0001_initial` |

With these files/standard Django prerequisites this is **42 nodes**. Django determines dependency order; review the exact printed filenames rather than relying solely on the count. Existing historical data/SQL operations in prerequisite migrations execute only inside the newly created empty disposable database. They are not rewritten or skipped.

Excluded: **`dic.0027_feedback_welfare`, dic_scoring migrations, sessions/admin and unrelated leaf migrations**. The helper loads the real graph; it does not hide 0027, disable migrations, fake application state or alter historical dependencies. Only the target's prerequisite closure is executed. Post-test verification requires applied migration history to equal this closure exactly.

For the intended existing development database, last inspected state is dic through 0026, accounts/auth already applied, scoring applied and Finance absent. The expected pending Finance plan is exactly:

```text
dic_finance.0001_initial
    Create Category
    Create Entry
    Create BudgetRevision
    Create Reconciliation
```

If prerequisites are unexpectedly missing, Finance already exists/applies, history is inconsistent or 0027 is applied/required, stop. Do not apply the disposable database's full prerequisite plan to development as a fallback.

## 7. Read-only development preparation and targeted command

After successful test evidence, the following action is **read-only** and can be used to inspect the intended development plan. It does not apply it:

```powershell
& $financePython -B $financeRunner development-plan --database dawana_dev
if ($LASTEXITCODE -ne 0) { throw 'Development migration state is unexpected. Stop; no application.' }
```

It forces a read-only loopback connection, checks `current_database()` and `transaction_read_only`, checks consistent history, refuses applied 0027, and requires the pending plan to contain only Finance 0001.

Configuration correction: the helper uses `test_dawana_dev_unused` as the unused
`DB_TEST_NAME` during development inspection. The earlier `dawana_dev_unused`
value violated `base.py`'s `test_` prefix requirement and raised
`ImproperlyConfigured` during `django.setup()`, before any database connection.
This setting does not create a test database. Disposable validation names retain
their existing unused test-name format. Development inspection also explicitly
checks the observed loopback address and port using `verify_connection_identity`.

### Prepared command — do not execute without separate migration approval

The explicit Django command is:

```powershell
& $financePython -B .\backend\manage.py migrate dic_finance 0001_initial --database default --settings config.settings.development
```

Do not run it with unverified environment overrides. This guarded equivalent checks Django's actual database configuration and pending plan in the same process before calling that exact targeted Django command. It does not rely on clearing an environment variable in PowerShell, which can allow `.env` to repopulate it. **The block below is preparation only; it is not authorised for execution by this procedure.**

```powershell
# FUTURE APPLICATION ONLY: separate approval and successful test evidence required.
if ((Read-Host 'Only after separate approval, type APPLY FINANCE TO dawana_dev') -cne 'APPLY FINANCE TO dawana_dev') {
    throw 'Development migration not approved.'
}
@'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
if os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings.development') != 'config.settings.development':
    raise RuntimeError('Unexpected settings module; stop.')
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.development'
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.management import call_command
if not settings.DEBUG or connection.settings_dict['NAME'] != 'dawana_dev':
    raise RuntimeError('Actual Django configuration is not the intended development database.')
if connection.settings_dict['HOST'] not in ('127.0.0.1', 'localhost', '::1'):
    raise RuntimeError('Refusing a non-loopback development connection.')
with connection.cursor() as cursor:
    cursor.execute('SET default_transaction_read_only = on')
    cursor.execute('SELECT current_database(), host(inet_server_addr())')
    db_name, address = cursor.fetchone()
    if db_name != 'dawana_dev' or address not in ('127.0.0.1', '::1'):
        raise RuntimeError('Connected database identity is unexpected.')
executor = MigrationExecutor(connection)
executor.loader.check_consistent_history(connection)
if ('dic', '0027_feedback_welfare') in executor.loader.applied_migrations:
    raise RuntimeError('Postponed migration already applied; stop.')
plan = executor.migration_plan([('dic_finance', '0001_initial')])
if [(m.app_label, m.name, backwards) for m, backwards in plan] != [('dic_finance', '0001_initial', False)]:
    raise RuntimeError('Expected exactly the Finance migration; stop.')
print('Approved target: dawana_dev; dic_finance.0001_initial only.')
with connection.cursor() as cursor:
    cursor.execute('SET default_transaction_read_only = off')
call_command('migrate', 'dic_finance', '0001_initial', database='default', interactive=False)
with connection.cursor() as cursor:
    cursor.execute('SET default_transaction_read_only = on')
    cursor.execute("SELECT app, name FROM django_migrations WHERE app='dic_finance' OR (app='dic' AND name='0027_feedback_welfare')")
    if cursor.fetchall() != [('dic_finance', '0001_initial')]:
        raise RuntimeError('Unexpected post-application migration state; stop.')
connection.close()
'@ | & $financePython -B -
if ($LASTEXITCODE -ne 0) { throw 'Finance migration failed or was refused. Stop; do not fake or rewrite history.' }
```

Before future application:

1. Record Python/Django versions, passing 19+4 counts, no skips, and reviewed Finance model/migration consistency output.
2. Preserve the exact tested application/migration files; re-run validation if they change.
3. Verify local DB host/port/user and intended `dawana_dev` identity in the deployment terminal, no unexpected `DATABASE_URL`/DB override, and no 0027 application. The optional helper is restricted to development/loopback; production needs a separately reviewed procedure.
4. Confirm backups and approved rollback/recovery arrangements. Do not assume schema rollback is harmless after financial data is recorded.
5. Inspect the one-node pending plan and the prepared migration file. Confirm four Finance tables only, no data migration, no dependency on 0027 and no historical edits.
6. Obtain explicit permission to apply to development. Creation of disposable test schemas is not approval to migrate development.
7. After separately approved application, inspect `django_migrations`/Finance tables and confirm 0027 remains absent, then restart API processes and assign approved least-privilege Finance roles. No role assignment or real transaction is part of the current procedure.

## 8. Remaining blockers and interpretation

- No backend test or helper action has been executed during preparation. There is no claimed pass result yet; run the commands in normal VS Code PowerShell and retain the output.
- The local PostgreSQL role must already have CREATEDB and ownership rights. If not, stop and ask the database administrator for an approved isolated facility; do not escalate/change grants automatically.
- Runtime model/migration drift or unexpected dependencies are stop conditions. Do not change historical migrations or filter the graph to force validation through.
- Tests may expose Finance defects; preserve the first failure and database receipt. This task prepares the procedure and does not silently fix/relabel failing tests.
- These focused tests do not establish concurrency safety, complete refund lifecycle, browser acceptance, real provider/bank reconciliation, receipt scanning or production permission assignments.
- The explicit development migration remains **prepared, not executed or approved for application**. `dic.0027_feedback_welfare` must remain unapplied throughout.
