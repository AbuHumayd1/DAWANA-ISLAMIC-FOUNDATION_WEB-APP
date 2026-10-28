# Guarded Phase 3 acceptance runner

Scope: test harness only. No application, migration, credential or deployment configuration changes. **Integration and browser commands have not been executed.** Their confirmation flag does not replace the required separate approval to run them.

## Commands from repository root

Static/database-free validation:

```powershell
& .\backend\.venv\Scripts\python.exe -m py_compile .\scripts\validate_dic_phase3_acceptance.py .\scripts\test_dic_phase3_acceptance_runner.py
& .\backend\.venv\Scripts\python.exe -m unittest discover -s scripts -p test_dic_phase3_acceptance_runner.py
& .\backend\.venv\Scripts\python.exe .\scripts\validate_dic_phase3_acceptance.py preflight --database dic_2026_demo
```

Only after a successful preflight and separate approval for writing acceptance:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\validate_dic_phase3_acceptance.py integration --database dic_2026_demo --confirm-demo-writes
& .\backend\.venv\Scripts\python.exe .\scripts\validate_dic_phase3_acceptance.py browser --database dic_2026_demo --confirm-demo-writes
```

No ordinary Django test runner, migrate, provisioning, flush or cleanup-delete command is used. No confirmation flag is needed for `preflight`, which uses a read-only PostgreSQL session and cannot execute DML through the runner's SQL guard.

## Safety and operation

- The CLI database is mandatory and must be exactly `dic_2026_demo`. The runner loads only local connection credentials from existing configuration, then overwrites database selection and test-only settings **before importing Django**. It explicitly clears `DATABASE_URL`, ignores its database name, permits only loopback PostgreSQL, guards Django and psycopg connections, and verifies SQL `current_database()` plus server address/port. This does not modify `.env` or stored credentials.
- PostgreSQL starts read-only, including application startup. Preflight checks migration dependency closure, absence of deferred 0027, model states, core columns, foreign keys and uniqueness. No migrations are applied.
- Writing modes require `--confirm-demo-writes`. They refuse other connected demo sessions and use an advisory transaction lock. The database must be dedicated to this run; stop any existing demo server before running them.
- All writing scenarios run inside a rollback-only repeatable-read transaction. An inventory is taken before any fixture insert. SQL guards reject DDL, deletion, commit SQL, multi-statement SQL, unknown tables, unbounded updates, and updates touching baseline rows. Writes outside the ownership/rollback wrapper are rejected. No existing edition/user/permission is modified. Only a synthetic staff user receives the existing explicit tutor permission.
- If no active edition exists, an owned synthetic 2026 edition can be created inside rollback only if the unique 2026 year is unused. Otherwise an existing active 2026 edition must already be suitable (registration open, complete pricing, tutor registration enabled). The runner fails rather than activating or changing pre-existing configuration. These checks are read-only in preflight.
- Paystack initialization/verification methods are mocked; production settlement logic, revisions, amount/currency checks and entitlement services still execute. All references and contacts are synthetic. Real HTTP, SMTP/SMS, external DNS, non-demo database connections and general subprocess execution are blocked. Only the packaged Playwright driver is allowed in browser mode. No provider credential installation/rotation or Google Cloud change occurs.
- OTPs are generated, encrypted, queued, worker-processed and verified through existing application paths. Only delivery is intercepted into private process memory. A test clock honors actual cooldown/hourly limits instead of changing them. Existing contact hashes/rate buckets are isolated with a process-only synthetic signing key. No code/password/token is printed or written to receipts.
- Browser mode first runs API scenarios with rollback, then launches a second rollback-only single-thread WSGI backend serving the existing frontend build. Requests run on the transaction-owning thread. Django connection-close request signals are temporarily disconnected and restored so requests cannot accidentally break transaction isolation.
- Chromium uses an ephemeral browser context/profile, blocked service workers, restricted local proxy/DNS and an origin-only request route. No existing browser/account profile is used. App/provider logs, request logs, tracebacks and Playwright debug traces are suppressed; screenshots, HAR, video and traces are not collected.

## Coverage

The integration scenario uses actual registration APIs for a two-minor guardian order, separate guardian/foreign orders, unverified/pending/failed/mismatched payments; genuine OTP proof and account activation; email/password login; explicit second-booking linking; foreign child denial; password reset; expired/revoked-by-reset sessions; refund eligibility loss; logout after loss of eligibility; and authorized complimentary tutor registration with housing and competition exclusion checks. Provider responses alone are mocked. Enrollment and account access always use application authorization services.

Browser mode additionally fills the public participant forms twice, enters an explicit guardian name/email at checkout, creates the order, settles using the guarded mocked provider boundary, then exercises actual email OTP, password confirmation/activation, logout, email/password login and camper switching. The public Google control must remain absent. API scenarios run first to cover negative cases without manipulating browser storage or bypassing OTP.

## Receipts and cleanup

Each invocation creates a new `output/acceptance/phase3-<uuid>.json`. It records target/schema metadata, baseline row counts and ID digests, all synthetic table/primary-key identities, check labels and per-batch cleanup status. It contains no contacts, passwords, OTPs, bearer credentials, provider secrets or raw responses.

Integration and browser fixtures are removed by transaction rollback, including audit/session/permission-grant rows created by the run. There is **no delete/reset cleanup path**. The runner compares all modeled-table primary-key sets with baseline after rollback before reporting cleanup verified. Browser startup/failure closes its transaction; a failed or interrupted run must not be treated as accepted. A receipt left at `rollback_pending` needs a read-only inventory investigation; never delete guessed rows from it.

PostgreSQL sequences can advance during rolled-back inserts. Sequence gaps are expected; the runner never resets them. Pre-existing records and receipts remain untouched. SQL ownership guards are defense in depth for trusted application code, not an OS sandbox for arbitrary malicious Python/native code.

## Validation status and prerequisites

- Python compilation, seven database-free guard unit tests, and the Python preflight were attempted but blocked before interpreter startup: base Python 3.13 executable reports **Access is denied**. These have **not passed** and must run before writing acceptance.
- Twelve source-level guard assertions passed using Node; these do not establish Python syntax or runtime correctness.
- Independent `psql` checks connected explicitly to `dic_2026_demo` at `127.0.0.1:5432` with `default_transaction_read_only=on`: required core tables and migrations 0028/0029/0030 are present, 0027 is absent, the explicit tutor permission exists, and no other demo session was observed. This is a catalog check, not the runner's full schema preflight.
- Python Playwright is absent in the inspected virtual environment; no Chromium cache was found. Browser prerequisites must be installed/approved before that mode can execute. The runner does not install them automatically. The existing `dawana-platform/dist/index.html` build is required; rebuild separately after source changes.
- Any browser-selector, SQL-guard or fixture incompatibility remains unverified until authorized execution. A failure must retain its receipt and trigger investigation; it must never weaken production authorization or application payment checks merely to make a test pass.

Stop here until static/Python preflight succeeds and writing acceptance is separately authorized.
