# Step B isolated demo backup and restore readiness

This prepares recovery evidence for **dic_2026_demo on 127.0.0.1:5432 only**. It does not authorize a backup, restore, database creation, migration, permission grant, timetable import/publication, production access, deployment or live Paystack. No existing feature or operational permission is changed.

## Preserved baseline

Step A receipt: `output/acceptance/migration-verification-2c9499d80e584c1ca72fc04efe0d68b9.json`.

- SHA-256: `c70fa32d1de80e6e426a2f90d8a030548cdf5bdd96c8063a822a076b05e27d9f`.
- Recorded identity: `dic_2026_demo`, `127.0.0.1:5432`, read-only transaction.
- Recorded history: 44 applied, 11 pending, including `dic.0032_phase4_timetables`.
- Manifest plan hash: `e5d5092b7e55f39fcc8d42da529b261b1980cd1d9694c1518d88240e412ad9e3`.

The workflow checks this receipt byte-for-byte and compares repository-owned pending migration source hashes. Django package migrations are retained in the receipt but are not rehashed by this standard-library preflight. This is historical evidence, not a fresh assertion of server state. `scripts/verify_dic_migrations.py` and the controlled migration mechanism are unchanged. Do not edit a receipt to make it pass; changed source/state needs a newly reviewed receipt and explicit baseline update.

## Files and conventions

- `scripts/dic_backup_readiness.py`: standard-library workflow. Default is offline preflight: guards, receipt, path/space and tool versions. It cannot create a backup or run a restore. The subprocess boundary allowlists version checks, one fixed read-only SQL query, and offline archive listing/full read. There is no arbitrary SQL or write mode.
- `scripts/test_dic_backup_readiness.py`: 19 database-free unit tests using fake subprocesses and temporary files. Covers target/role guards, dry-run behavior, tool discovery/failure, protected restore names, overwrite prevention, credential isolation/redaction, read-only identity, versions/space/privileges and corrupt/unreadable archives.
- `scripts/validate_dic_backup_readiness.ps1`: consolidated safe checks. Preserves existing PowerShell summary conventions; never requests a database connection. It checks the pinned receipt/source hashes and Windows tools independently of Python.

Custom-format `PGDMP` header, TOC and full archive read to the null device follow `scripts/local_preview.py` conventions. **Do not invoke `start-local-preview.ps1`, `complete-local-identification.ps1` or `configure-dic2026-houses.ps1` for Step B**: those have other database-changing responsibilities.

## Prerequisites and tooling

Supply a trusted complete PostgreSQL toolset. Python workflow configuration priority:

1. Explicit `--pg-dump-path`, `--pg-restore-path`, `--psql-path`, or environment equivalents `DIC_PG_DUMP_PATH`, `DIC_PG_RESTORE_PATH`, `DIC_PSQL_PATH`. Missing sibling tools are sought beside an explicitly supplied executable; invalid explicit configuration never falls back silently.
2. `--pg-bin` / `DIC_PG_BIN`, an absolute directory.
3. Complete installations under `%ProgramFiles%\PostgreSQL\<numeric-major>\bin`, newest first, then the directory containing `psql` on PATH. No recursive drive scan, registry/system edits or software installation.

All three tools must exist at absolute paths and report matching major/minor versions. Automatic detection can choose a newer installed server distribution; it does **not** prove compatibility with the running server. The optional connected preflight requires the client major to match the server major, consistent with the existing project backup gate. Choose a matching `PgBin` explicitly after reviewing server identity. No tool is installed or upgraded automatically.

Destination must be a **new** `.dump` file beneath the existing ignored `.local-preview` directory; the parent must already exist. Symlink/junction redirection outside the private root is rejected, including redirection of the private root itself. Existing files are never overwritten. Preflight uses filesystem metadata only, with no directory creation or probe writes. `os.access` does not establish Windows ACL confidentiality: an operator must separately inspect/restrict ACLs, encryption, available capacity and retention before approving a backup. Git ignore is not access control. Do not upload archives, TOCs or raw SQL/data to source control or chat.

The source account must already be approved for demo reads/backup; do not grant rights automatically. The connected check rejects missing table/view/foreign-table SELECT, sequence SELECT, large-object SELECT, or any row-security tables pending separate review. This conservative check is not proof that all dump operations will succeed (extensions, schemas, locks and other permissions still need review and a successful authorized dump).

## Credentials and connection isolation

Configure an explicit simple role name with `--username` or `DIC_DEMO_PG_USER`; the workflow never loads `backend/.env` or inherits application database targets. Host and port are pinned to numeric loopback and the receipt port; arbitrary hosts, URLs, DSNs and service names are rejected.

For the optional connected read, use **one** credential source:

- `--password-env DIC_DEMO_PG_PASSWORD`: operator supplies that environment variable outside logs/command history. Its value is passed only in the child environment, never argv or output. Do not set it with a literal in a recorded command.
- `--passfile <absolute-private-file>`: existing restricted libpq passfile. Prefer an exact `127.0.0.1:5432:dic_2026_demo:<approved-role>:<password>` entry without wildcards. Verify ACLs manually. No credential file is created by preflight.

All inherited `PG*` settings and common password/secret/token/URL environment variables are removed from subprocess environments. The chosen credential is supplied explicitly; default `.pgpass` discovery is disabled. Children receive read-only transaction defaults and short timeouts. `psql` disables startup files and interactive password prompting. Its only connection query checks actual database, server IP/port, current role, read-only state, version, database size and backup privilege/RLS prerequisites. Raw process stdout/stderr and exception details are not printed on failure. Do not enable shell tracing or log child environments. Loopback uses explicit `sslmode=disable`, matching this local-only target; this workflow cannot be repurposed for remote/production access.

## Safe commands

From the repository root, the consolidated validation command is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_backup_readiness.ps1 -Username $env:DIC_DEMO_PG_USER -PgBin 'C:\Program Files\PostgreSQL\17\bin'
```

The version directory above is an example; choose the actual approved distribution. This runs no database connections or writes. If the role is not configured, configured-target preflight is NOT RUN and the overall result is INCOMPLETE. If Python is known unavailable, `-SkipPython` runs only PowerShell receipt/tool checks and reports Python tests/preflight NOT RUN, with a nonzero incomplete exit. No fallback runtime installation is attempted.

Direct offline preflight (no database connection, backup or restore):

```powershell
& .\backend\.venv\Scripts\python.exe -B .\scripts\dic_backup_readiness.py --username $env:DIC_DEMO_PG_USER --pg-bin $env:DIC_PG_BIN
```

Explicit read-only connected check, once the approved demo role and credentials are available (not a backup authorization):

```powershell
& .\backend\.venv\Scripts\python.exe -B .\scripts\dic_backup_readiness.py --username $env:DIC_DEMO_PG_USER --pg-bin $env:DIC_PG_BIN --password-env DIC_DEMO_PG_PASSWORD --check-connection
```

The connected check requires free space of at least twice the reported database size, with a minimum 1 GiB. This is a readiness estimate, not a reservation or guarantee of final dump size. The default destination is `.local-preview/dic_2026_demo_step_b.dump`; supply a unique absolute `--destination` if that path already exists. Do not delete or reuse a previous archive.

## Separately authorized backup procedure — not executed

Obtain explicit approval naming the source database/endpoint, operator/time, private destination, toolset, credential source, access restrictions and retention. Confirm no production/application database target is inherited and retain a fresh read-only identity/history receipt. Quiesce demo application writes if the intended rollback point requires a stable release boundary; stopping services is a separate operational decision. A PostgreSQL dump is transaction-consistent but external media/configuration/secrets and subsequent writes are outside that snapshot.

In a separately approved isolated operator session, use `child_environment()` from the workflow for the same explicit credentials/read-only settings and the validated tools/target. The dump invocation to review is:

```text
<validated pg_dump.exe> --format=custom --no-password --host 127.0.0.1 --port 5432 --username <approved-demo-role> --dbname dic_2026_demo --file <new-private-unique-archive.dump>
```

This is a review template, not an action supported by the readiness script. The operator must exclusively reserve the new file (`open(path, 'xb')` or .NET `FileMode.CreateNew`) immediately before the approved dump to prevent overwriting earlier evidence. `pg_dump` can then write that operator-owned reserved empty file. Preserve failed/partial files under their unique names, clearly marked failed; never accept them as backups. Do not add `--create`, shell-expanded connection URLs, broad-role grants or migration commands. Capture exit status and sanitized metadata only. The workflow's `run_read()` intentionally rejects dump execution even after someone supplies an approval-like argument.

After a successful authorized dump, independently record its byte length and SHA-256, then run offline archive verification:

```powershell
& .\backend\.venv\Scripts\python.exe -B .\scripts\dic_backup_readiness.py --username $env:DIC_DEMO_PG_USER --pg-bin $env:DIC_PG_BIN --archive $approvedArchivePath --expected-sha256 $recordedArchiveSha256
```

This checks `PGDMP`, the separately recorded checksum, nonempty TOC with exact source `dbname: dic_2026_demo`, and a complete `pg_restore --file NUL` read, without supplying `--dbname` or connecting `pg_restore` to any database. The checksum detects changes relative to the recorded evidence; it is not authentication if archive and hash can both be replaced. Preserve provenance and restrict both. Archive readability **does not** prove successful restoration.

## Restore prerequisites and approval boundary — not executed

1. Name a separately approved disposable target matching `dic_2026_restore_<12-32 lowercase hex>`. Offline `--restore-database <name>` validates the name only. No database is connected to, created, dropped, renamed or restored by that option.
2. Obtain distinct approvals for disposable database provisioning and the real restore, specifying endpoint, unique target, owner, operator/time, exact archive hash, tool/server versions, extensions, roles/ownership policy, encoding/locale, tablespaces, disk capacity and isolation. Check that the disposable target does not already exist before creation; otherwise stop and seek a new approved name. Use no template containing live application data.
3. The approved restore session must independently verify `current_database()`, server address/port and disposable owner before any restore. Use a role with CONNECT/CREATE/object privileges **only** on the approved disposable, with no CREATE DATABASE, superuser or source-database write rights. Do not alter source grants to facilitate rehearsal. No application traffic, delivery worker, Paystack, webhooks or email should point at the restored database.
4. Review `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges --dbname <exact-approved-disposable> <verified-archive>` in that separately authorized session. Do not use `--clean`, `--create`, `--if-exists`, a default database, or `psql` against the demo/dev/production databases. Tool execution needs its own restricted environment; the readiness script's read-only environment must not be broadly changed to enable restoration.
5. Independently verify schema/object availability, constraints, selected table counts, expected 44 applied/11 pending migration inventory and protected data behavior against the disposable only. Compare with a contemporaneous approved source inventory, accounting for writes after the dump snapshot. Record failures honestly. Do not execute pending migrations as part of restore acceptance.
6. Retain the disposable until evidence review. Cleanup/drop is another explicit authorization; no automatic cleanup or source replacement is included.

Never restore over `dic_2026_demo`, `dawana_dev`, any production database or an existing target. The name guard is only one layer; actual role/endpoint verification and restricted privileges are mandatory before a separately approved restore.

## Acceptance evidence and rollback

Record a new sanitized Step B evidence artifact without editing Step A: approvals/UTC and Lagos times, source identity/read-only checks, preserved migration receipt/hash, tool paths/versions and server major, source inventory reference, destination ACL/retention review, disk headroom, dump exit status/size/hash, archive header/TOC/full-read results, disposable approvals/identity, restore exit status and comparisons, and the rollback owner/decision. Omit passwords, URLs, raw TOCs, SQL data and delivery/authentication tokens.

Backup acceptance requires successful authorized dump plus all archive checks. Restore acceptance additionally requires a successful approved disposable rehearsal and matching inventory. Step B cannot be marked complete from preflight or `pg_restore --list` alone. A future controlled migration approval must reference the reviewed manifest, verified backup, completed restore evidence, operator approval and agreed rollback decision. Demo readiness is not production approval; the existing release command deliberately refuses demo/development targets, so no existing guard may be bypassed to apply a demo plan. Any demo migration execution mechanism still needs separate review and authorization.

If later migrations fail, stop new writes/traffic under the approved operational plan and assess a reviewed forward repair or isolated recovery. Do not automatically reverse migrations, overwrite source data or switch applications to the disposable. A rollback decision must account for all post-backup writes, financial/movement/audit records, restored credentials/tokens, media and external effects. Application rollback alone is safe only when schema compatibility has been established. Actual source recovery is a separate explicit action, outside this preparation workflow.

## Actual preparation results

Sanitized executed-check log: `output/acceptance/step-b-readiness-preparation.log`.
It records the intentionally incomplete `-SkipPython` cycle; it is not backup or
restore evidence. PowerShell syntax was also checked with its native parser.

- **PASS:** preserved Step A receipt SHA-256, identity/counts and repository-owned migration source hashes.
- **PASS:** safe Windows detection found `C:\Program Files\PostgreSQL\18\bin`; `pg_dump`, `pg_restore` and `psql` all report **18.6**. This proves tool availability only, not running-server compatibility.
- **NOT RUN:** 19 focused Python tests and full offline Python preflight. The existing virtual environment cannot start its configured Python 3.13 interpreter: access denied. One attempt was made; no runtime was installed or system setting altered.
- **NOT RUN:** live read-only source identity/version/size/privilege check, backup creation, archive integrity and disposable restore. No credentials were requested/read and no database connection was opened by this preparation.
- No executed readiness assertion failed, but validation is **INCOMPLETE** and returns nonzero while required Python/preflight checks remain NOT RUN. No backup/restore PASS is asserted.

Remaining blockers: working local Python and passing focused tests; approved demo role/credential source and connected preflight; server-compatible tool selection; private-destination ACL/retention review; separate backup approval and verified archive; disposable provisioning/restore approval and completed rehearsal; refreshed migration review plus a separately approved migration execution plan. No migration approval is issued here.
