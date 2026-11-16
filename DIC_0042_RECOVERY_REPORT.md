# DIC 0042 recovery implementation report

## A. Confirmed findings and hypotheses

Confirmed source defect: the normal Render build lacked a migration-compatibility barrier. PR #29 code queries new 0042 columns/tables, so it could be promoted before its schema was present. The locally available main is the confirmed PR #29 merge `02a154e7ee10ec3d351d25a6a92e384b19471906`. A fresh GitHub fetch was attempted and failed (network unavailable). No production database connectivity or Render connector is available in this environment.

The owner's ProgrammingError and successful rollback to `31c323f` strongly support missing/incompatible 0042 schema. **The live root cause is not yet confirmed.** Production django_migrations, physical schema and original SQL error still require the read-only procedure. Synthetic PostgreSQL reproduced 42703 for missing columns and 42P01 for missing tables; those are not claims about live results.

## B. Files changed

* backend/config/integrated_schema_recovery.py — read-only inspection, pinned 0042 policy, exact approval, transactional executor and sanitized receipts.
* backend/config/deployment_schema_guard.py — read-only deployment readiness, complete pending-plan rejection and model-column probes.
* backend/native-build.sh — mandatory Render-only compatibility check; no migration application.
* backend/integrated-schema-recovery-build.sh — one-time runner with unconditional failed-build promotion barrier.
* backend/config/test_integrated_schema_recovery.py — ten guard contracts and eight real PostgreSQL scenarios.
* scripts/New-Dic0042Approval.ps1 — explicit owner/backup approval preparation, exact UTF-8/base64/SHA256; no database execution.
* scripts/test_integrated_schema_recovery.sh — five synthetic shell entrypoint/barrier checks.
* .github/workflows/integrated-schema-recovery-tests.yml — shell regression CI; PostgreSQL tests are discovered by existing core acceptance CI.
* DIC_0042_PRODUCTION_RECOVERY.md — exact operational runbook and rollback limits.
* DIC_0042_RECOVERY_REPORT.md — this report.

0042 itself, the existing 0041 runner/wrapper/tests, fresh-database GitHub recovery workflow, application models, frontend, startup command and production settings were not modified. Owner checkout retains its original 91 tracked changes. Existing integration worktree/branches and previous candidate files were preserved. Recovery work uses a separate local clone/branch because the owner's .git metadata is read-only in this environment.

## C. Schema/data safety

0042 contains 23 operations: three CreateModel, sixteen AddField, one AlterField and three AddConstraint. It adds certificates/recordings, timetable audience/meal metadata, private video metadata and a canonical house key. It contains no RunPython/RunSQL/content initialization. The runner verifies the exact normalized source hash and permitted operation shape, complete dependency history and physical baseline. It rejects partial representation, unknown recorded migrations, graph conflicts and unrelated pending migrations.

The new partial uniqueness rules exclude blank house/meal keys. Genuine pre-0042 rows receive blank keys, so they do not conflict. Existing-schema conflicts are counted without exposing records and cause a stop. New primary/foreign/unique constraints, column types/nullability and partial-index predicates are inspected. No live compatibility conclusion is asserted until inspection succeeds.

Atomic DDL and recorder writes share a PostgreSQL transaction. Apply takes bounded table/advisory locks and timeouts. Verification failure rolls everything back; a lost connection/COMMIT outcome requires reinspection. Already-applied schema is not reapplied. No fake, reverse, blanket migrate, post_migrate, storage activation or reference seeding occurs.

Backward compatibility is limited for old-code CREATE operations on House/CampVideo/TimetableEntry after non-null columns are added without permanent database defaults. Pause those administrative creations during the migration/deployment window. Existing participant/payment/check-in/ID/allocation records and columns are preserved. Do not reverse populated 0042 tables as a rollback shortcut.

## D. Read-only production inspection

Use the runbook's temporary owner-operated Render build with DAWANA_0042_MODE=inspect, exact DAWANA_SCHEMA_* identity, existing external verify-full connection/CA, and the pinned recovery revision. The wrapper intentionally fails the build so `31c323f` remains live. Inspection emits recorder/dependency hashes, complete pending plan, actual schema, sanitized zero-row SQLSTATE probes and a plan fingerprint. It does not modify permanent data. Cluster identity inspection permission must be verified with the provider; no bypass is included.

## E. Explicitly authorized apply and verification

Owner first reviews the receipt and verified backup/restore readiness. The PowerShell approval builder requires explicit OwnerAuthorized/BackupRestoreVerified switches, named approver, backup/restore/rollback evidence and reviewed fingerprint. Apply independently re-derives and matches the exact source revision, identity, history, schema and pending plan under locks. It permits only 0042 with its dependencies already applied. COMMITTED_0042 is reported after COMMIT, and the build still fails intentionally. Clear approval, run verify independently, then request the separate normal deployment. None of these production actions was executed here.

## F. Permanent Render configuration

Build: `python -m pip install -r backend/requirements.txt && bash backend/native-build.sh`

Start: `bash backend/native-start.sh web`

Retain DAWANA_SCHEMA_DATABASE/HOST/PORT/ROLE/CLUSTER_ID. Existing database secrets, verify-full/CA, public hosts, payment flags and R2 settings remain unchanged. Render builds now fail on unknown/incompatible/pending migration state. Compatible schemas pass; no automatic application occurs. Startup is unchanged and does not add this database guard, so the current healthy deployment is not disabled. Do not run concurrent schema changes between readiness check and promotion.

## G. Test evidence

Local environment: Python 3.12, Django 5.2.18 and PostgreSQL 17.11 on disposable loopback test databases, with real migrations. Production TLS/identity checks are tested with synthetic connection objects; local PostgreSQL transport is isolated/non-production and does not establish live TLS/provider acceptance.

* 59 backend regression tests passed, zero failures/skips: recovery contracts/scenarios, Operations lifecycle, participant authentication/authorization/ID concurrency and integrated-release behavior.
* Final focused recovery plus native/Render deployment validation: 42 passed, zero failures/skips, recorded in evidence/recovery-deployment-final.log. This overlaps the preceding run; do not add counts as unique coverage.
* Existing 0041 runner: 16 tests passed unchanged.
* Shell: five barriers plus syntax passed. Successful or failed recovery always prevents promotion; unknown schema blocks Render build; compatible Render/non-Render builds pass the entrypoint contract.
* PowerShell: parser and synthetic approval UTF-8/base64/digest roundtrip passed; no database connection.
* Python syntax parsed across 378 backend files; git diff whitespace check passed.

An earlier raw-runtime deployment run reported seven subprocess failures because its isolated child interpreter could not import django-environ. A dependency-complete local virtual environment resolved that environment issue; all 42 final tests, including real WSGI startup/TLS configuration regressions, passed. No application code was weakened to accommodate the test environment.

The populated fixture includes verified payment, issued ID, historical check-in and allocation. It snapshots every original column/row in existing dic/accounts tables across migration, then exercises real camper and Operations endpoints. Other cases cover duplicate keys, missing/faked/partial schema, unknown plan, wrong approval/source/identity/TLS, read-only enforcement, lock contention and DDL/recorder rollback.

No frontend code changed, so frontend build/browser suites were not rerun for this recovery. Existing real-endpoint backend regressions were run. GitHub CI and its PostgreSQL 14/18 matrix have not been executed from this restricted environment; the focused tests are wired into them. Live endpoint and R2 checks remain owner-operated after approved restoration.

## H. Delivery

One local branch: fix/dic2026-schema-recovery. The consolidated `dic0042-recovery-delivery.zip` contains the complete source patch, every changed/new file, manifest/hashes, commit bundle, evidence and Windows PowerShell integration instructions. The manifest identifies the exact local commit and base. No push or PR was possible because GitHub network access failed. Integrate onto freshly fetched main, verify PR #29 ancestry and review any upstream overlap; do not replace main with an archived tree. Create/reuse one focused PR only. No merge/deployment was attempted.

## I. Outstanding approvals/dependencies

Fresh-main reconciliation and GitHub CI; actual read-only production inspection and original SQL-error comparison; provider-verified identity/cluster-function access and trusted CA; verified backup/recovery readiness; explicit production apply approval; independent verification; separate normal deployment approval and live acceptance. No R2 activation is included.

Because post_migrate is deliberately excluded, new-model content types/permissions may remain absent. The integrated committee-role initializer requires those permissions. Assess and separately approve narrowly scoped framework metadata initialization before declaring new committee/media/certificate roles accepted; do not run unrestricted migrate during this emergency to create them silently.

## J. Exact restoration sequence

Keep `31c323f` live → review/integrate this recovery PR onto current main → owner runs failed-build read-only inspection → classify actual state and review exact plan → owner confirms backup/restore and approves fingerprint → owner runs guarded apply if genuinely missing → owner runs independent read-only verify → restore permanent guarded build command → owner explicitly deploys reviewed code → verify camper enrollments, participant/house/allocation Admin pages, videos/recordings, login/registration, permissions, finance/IDs/check-ins and preserved operational records. Only live acceptance establishes recovery. If inspection instead shows inconsistent or unrelated schema/errors, stop; this tool intentionally does not guess a repair.
