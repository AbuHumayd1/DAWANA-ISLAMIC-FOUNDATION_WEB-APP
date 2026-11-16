# DIC 0042 production recovery and deployment contract

## Status and diagnosis

This is a recovery-only change based on the locally available production merge `02a154e7ee10ec3d351d25a6a92e384b19471906` (PR #29). The owner's active checkout, existing integration release and unrelated work were preserved. GitHub fetch failed from this environment; verify fresh main before integrating this patch. No production connection, migration, Render setting change, merge, deployment, R2 activation or content initialization was performed.

Confirmed in source: normal Render build previously collected static files without migration planning/readiness checks. Migration 0042 has 23 operations: three CreateModel, sixteen AddField, one AlterField and three AddConstraint. New ORM queries use new columns on House/CampVideo/TimetableEntry and three new tables. The reported ProgrammingError/rollback recovery is consistent with unapplied 0042. This is a hypothesis about live schema until the read-only receipt is obtained. An applied-but-partial schema, permissions problem or unrelated SQL error is still possible. The current healthy backend `31c323f` must remain live throughout inspection/migration.

The recovery runner reproduces zero-row historical-model queries and reports sanitized SQLSTATE/object metadata without row data. A missing column produces 42703; missing table produces 42P01. Compare this receipt with the original Render error privately. Synthetic reproduction does not establish what happened on production.

## Scope and safety of 0042

New tables: dic_certificaterelease, dic_lecturerecording, dic_participationcertificate. New columns: House.canonical_key; CampVideo.description/lecturer/recording_file/session_id; TimetableEntry.audience/gender/lecturer/meal/title. Video URL blank handling changes model validation. Existing rows receive blank values or general audience/gender defaults; nullable new references do not invent associations. No participant/payment/ID/check-in/allocation row is deleted or reclassified. No reference content or houses are seeded by the migration.

Partial unique indexes enforce nonblank canonical house key per edition, and nonblank food meal per edition/date. The third unique constraint enforces certificate edition/participant; certificate reference and release edition are also unique. In the genuine pre-0042 schema the new house/meal columns do not exist, so all existing values will be blank and excluded from those partial indexes. If objects already exist, the runner reports inconsistency/conflict counts and refuses to repair, fake or delete anything.

The exact LF-normalized 0042 source SHA256 is `3d94da0a3c5e2213fd01362686c72498d88cfc362f27e74cdef47612868648d0`. Its reviewed dependencies must already be recorded, especially 0041. The runner pins this hash, operation classes/count, atomicity and dependency. It reports every outstanding graph leaf plan and refuses anything except one forward 0042 step. It never invokes unrestricted manage.py migrate, post_migrate, initialization commands, backward migrations or fake history. Existing 0041 tooling and the fresh-schema GitHub recovery workflow are unchanged.

Compatibility window: Django's non-null AddField defaults populate the new columns on existing rows but are not permanent database defaults. While `31c323f` remains live after migration, pause creation of houses, videos and timetable entries: old code does not supply those new fields. Existing registration/payment/check-in/ID/allocation columns remain unchanged. Old-code reads remain compatible, but rolling application code back does not guarantee old administrative CREATE operations on those three models. Do not reverse 0042 to solve that limitation; keep the window short and use the reviewed new backend after verification.

## Prerequisites and identity

Use the Render **external** PostgreSQL hostname already required by production settings, with verify-full and a readable trusted CA (`DB_SSLROOTCERT` when needed). Keep existing DATABASE_URL/DB variables secret and unchanged. Do not copy credentials into scripts, GitHub issues, receipts or logs. No TLS downgrade is supported.

The database owner/provider must privately supply these verified, non-password identity values (reuse the reviewed 0041 identity if still current):

| Render variable | Value |
|---|---|
| DAWANA_SCHEMA_DATABASE | exact production database name |
| DAWANA_SCHEMA_HOST | full external TLS hostname |
| DAWANA_SCHEMA_PORT | exact port, usually 5432 |
| DAWANA_SCHEMA_ROLE | exact production SQL role |
| DAWANA_SCHEMA_CLUSTER_ID | PostgreSQL system_identifier, nonzero decimal |

These are required permanently by the build guard and temporarily by recovery. Server identity is bound through verify-full hostname validation plus the connected database/current_user/system_identifier check. The SQL role needs permission to inspect pg_control_system() and schema catalogs as well as the already-approved migration privileges for apply. If the managed provider denies cluster identity inspection, STOP and have the provider/DBA verify and grant narrowly scoped inspection access. Do not substitute a guessed cluster ID, use a different service database, bypass identity checks or switch to fresh-schema INITIALIZE. No privileged grant is made automatically by this change.

## 1. Owner-operated READ-ONLY inspection, without Render Shell

After reviewing/merging the recovery PR through the normal owner workflow, select the exact recovery commit for a manual Render build. A candidate build failure leaves `31c323f` running. Do not promote PR #29 code first. Use the same pinned recovery revision for inspect/apply/verify; a changed revision requires a new receipt and approval.

The owner sets DAWANA_0042_MODE=inspect and the identity variables above. Temporarily set the build command to:

```bash
python -m pip install -r backend/requirements.txt && bash backend/integrated-schema-recovery-build.sh
```

Start command remains `bash backend/native-start.sh web`. Start a manual build. The wrapper intentionally exits 1 even when inspection succeeds, preventing application promotion. Settings/driver errors are suppressed into fixed codes. Inspect uses connection-level read-only plus a repeatable-read READ ONLY transaction, catalog queries, bounded zero-row probes and no permanent writes.

Privately save the one JSON line with status INSPECTED_READ_ONLY as inspection.json. Ignore surrounding build/pip text when saving JSON. Review:

* source revision/hash and identity match the intended database;
* recorded migration list, dependency hashes and complete pending plan;
* state is missing, applied or inconsistent;
* exact columns/tables/primary/foreign/unique constraints and partial-index predicates;
* aggregate unique-conflict counts and sanitized zero-row SQLSTATE probes.

Expected recovery case: state=missing, exactly dic.0042 pending, new schema objects absent, existing baseline columns intact and conflict counts zero. If state=applied with no pending migrations, use verify; do not reapply. If inconsistent, unexpected pending migrations, graph conflict, unknown recorded migrations or cluster/permission failure occurs, stop and review privately. This mechanism does not guess or repair an inconsistent schema. Do not use the fresh-database GitHub Schema Recovery workflow or the 0041-only runner for this incident.

## 2. Owner review and approval (not performed by Codex)

Confirm a recent production snapshot/backup and documented tested restoration procedure/RPO/RTO. Decide rollback strategy: retain additive 0042 schema and keep/return to `31c323f` if application verification fails. A destructive database restore is a separate owner decision and can lose legitimate writes made after the backup.

Copy the exact plan_sha256 from the receipt after reviewing the whole plan. Prepare approval privately in Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\New-Dic0042Approval.ps1 `
  -InspectionReceipt .\inspection.json -ApprovedBy 'OWNER NAME' `
  -BackupReference 'VERIFIED BACKUP REFERENCE' `
  -RestoreProcedure 'REVIEWED RESTORE PROCEDURE AND READINESS' `
  -RollbackDecision 'Retain additive schema; keep healthy backend on failure' `
  -ReviewedPlanSha256 'EXACT REVIEWED PLAN SHA256' `
  -OwnerAuthorized -BackupRestoreVerified -OutputDirectory .\private-0042-approval
```

This script connects to nothing and never executes a migration. Use a new private directory outside Git; restrict access according to the owner's normal procedure. Inspect approval.json. The two text files contain exact UTF-8 approval bytes encoded for Render and their SHA256. They contain non-password infrastructure/backup metadata and authorization evidence; do not commit them. The fingerprint is rechecked against current schema, complete migration history, dependency sources, exact release commit and database identity at apply time. A changed plan/identity/commit invalidates approval.

## 3. Owner-authorized apply (NOT authorized/executed in this task)

Only after explicit owner authorization, copy the private file values into DAWANA_0042_APPROVAL_B64 and DAWANA_0042_APPROVAL_SHA256. Set DAWANA_0042_MODE=apply. Re-run the same temporary failed-build command at the identical recovery commit. Do not change the startup command or healthy runtime.

Apply takes a transaction-scoped advisory lock, 5-second lock timeout, 120-second per-statement timeout, and SHARE ROW EXCLUSIVE locks on django_migrations/House/TimetableEntry/CampVideo before reinspection. PostgreSQL DDL and migration recorder update share one atomic transaction. This may briefly block operational writes; use an owner-approved quiet window. Lock timeout/busy locks cause a stop, not a retry loop. Concurrent schema work must be prohibited operationally; this lock also serializes this recovery runner. The older 0041 runner uses its own lock and must not be run concurrently.

Only exact reviewed 0042 executes via MigrationExecutor; no post_migrate signals run. Consequently new Django content types/permission rows are not initialized as a side effect. Staff role/content initialization remains a separate explicitly reviewed post-release activity from the integrated release; do not invoke unrestricted migrate merely to create them during recovery.

Check for missing new-model permission metadata before assigning the integrated release's new committee roles. Its role initializer expects those permissions to exist. A separately approved, narrowly scoped framework-metadata step may be necessary; it is not silently included in this schema-only recovery. Superuser schema/page verification and existing permissions do not depend on that initialization. Do not declare every new committee workflow accepted until this dependency is resolved.

COMMITTED_0042 is printed only after COMMIT succeeds. A failed build is still intentional: no application is promoted. If the connection/build is interrupted, or APPLY_OUTCOME_UNCONFIRMED_REINSPECT occurs, do not assume success or failure. Clear apply mode/approval and run inspect on the same revision. Applied+complete returns ALREADY_APPLIED_NO_WRITES on a valid retry; partial/uncertain representation stops. Never reverse, fake, delete tables or force a recorder entry to get past this barrier.

## 4. Independent verification

Set DAWANA_0042_MODE=verify. Remove the approval variables. Re-run the same failed-build command. Require VERIFIED_READ_ONLY, applied state, no pending migrations and complete schema/constraint/zero-row probes. Save the receipt privately. Compare legitimate registration/payment totals, IDs, check-ins and allocations against the pre-change baseline without reclassifying them. No disposable fixtures should be loaded in production.

## 5. Normal application deployment (separate owner authorization)

Remove DAWANA_0042_MODE and temporary approval variables. Retain DAWANA_SCHEMA_* identity variables. Restore the permanent commands:

```text
Build: python -m pip install -r backend/requirements.txt && bash backend/native-build.sh
Start: bash backend/native-start.sh web
```

Owner then explicitly deploys the reviewed main revision. The mandatory Render-only native build guard opens a verified read-only connection, checks migration graph/history, requires no pending migrations, validates 0042 representation and probes all managed model columns with WHERE FALSE. It fails safely if status is unknown or incompatible; there is no bypass flag or automatic migrate. A compatible schema allows ordinary builds. Non-Render static builds retain their existing behavior. Web startup is unchanged so database uncertainty does not turn a healthy process restart into this new guard's failure mode. The guard cannot detect a database changed after build time; prohibit concurrent schema reversal/change and never reverse populated 0042 tables.

Verify camper enrollments/authorization, Operations participants/check-in/IDs, Admin houses/allocations, videos/recordings, finance evidence, legitimate received money and public login/registration. Confirm R2/certificate flags retain their prior values; this patch does not activate either. Only then declare PR #29 functionality restored. If application acceptance fails, retain the additive schema and keep/redeploy the healthy backend under owner control; do not reverse 0042 after new records exist.

## Routine future schema releases

Keep the build guard permanently. Each schema release gets a reviewed exact plan and backup/recovery window before the ordinary code deployment. Inspection is separate from application and promotion. A new migration requires its own reviewed source/operation policy based on this runner; merely changing TARGET/hash is not sufficient. Existing generic release_migrations apply covers all outstanding leaves and emits post_migrate, so it remains excluded from this live-database emergency procedure. Capture read-only inspection, approval and post-commit verification receipts for every release. The fail-closed build barrier prevents the missing-migration promotion that source review identified here.
