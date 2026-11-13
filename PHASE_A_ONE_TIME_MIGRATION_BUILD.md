# Phase A RC3: one-time Render migration build

Prepared only. No production SQL, push, merge, deployment or Render settings change has been performed by this task. Execute the following procedure only after owner approval.

## Files and scope

New files only:

- `backend/phase-a-migration-build.sh`
- `backend/config/phase_a_migration_build.py`
- `scripts/test_phase_a_migration_build.py`
- `.github/workflows/phase-a-migration-build-tests.yml`
- `PHASE_A_ONE_TIME_MIGRATION_BUILD.md`

The existing native scripts, `release_migrations` command, validator, migration, payment configuration, expiry policy and owner edits are unchanged. The one-time runner reuses `config.release_migrations.plan_manifest`, `validate_target` and `validate_approval`. It deliberately does not call the broader management command: that command permits arbitrary approved pending plans and emits `post_migrate` signals, which can write permissions/seed data beyond 0041. This runner permits only the three additive `CreateModel` operations in 0041, migration recorder writes and no post-migration hooks. It does not create lifecycle permissions or grant staff access; handle any missing permission as a separate reviewed operation, never silently as part of this migration.

Release-review base: this isolated checkout uses the recorded RC3 release commit `5b946f255e1aafaa1127e29dc28bdde06f3cf430`, not local `main` or the mixed development working tree. Its 0041 migration matches the reviewed RC3 ZIP byte-for-byte; the shared approval validator and Render production settings match the ZIP after CRLF/LF normalization. Local `main` (`074c49b4f8ab01914b992f59ca4125f696eb8669`) and cached `origin/main` (`f970461e7b3537eb4437cdd28ccd55aa5ec040fc`) are stale. The existing `origin/release/phase-a-rc3-20261113` tracking ref records the RC3 commit, but that is not fresh proof of its merge into current main.

**Provisional commit, not deployment-ready:** GitHub connections are blocked in this execution environment; `gh auth status` also reports invalid authentication here. Current main ancestry/content and GitHub check results could not be verified. Chrome/dashboard access was refused, so actual Render settings, build-time CA availability and database-role privileges are unverified. After restoring access, fetch main in this isolated checkout, verify the RC3 ancestry and review any intervening differences, then base the five-file change on that verified main and run CI before release. Do not publish the mixed owner workspace wholesale. No permission to push, merge or deploy is implied by this local commit.

## Promotion barrier and permanent commands

Temporary Build Command (for BOTH planning and application):

```sh
python -m pip install -r backend/requirements.txt && bash backend/phase-a-migration-build.sh
```

The wrapper exits **1 even after successful migration commit**. Render must mark this deployment/build failed; it must never start its new backend. The previous successful deployment continues serving. The temporary build does not run collectstatic, start Gunicorn, or produce a deployable successful release. Do not append `|| true`, force success, or invoke the Python module directly as the Build Command. Do not enable automatic deployment of the new runtime during this procedure. Serialize migration operations; the advisory lock coordinates this runner, not unrelated tools that ignore it. Old runtime/new additive-schema compatibility must be retained while the old deployment serves.

Permanent command values remain exactly:

```sh
# Build
python -m pip install -r backend/requirements.txt && bash backend/native-build.sh
# Start
bash backend/native-start.sh web
```

Only temporarily substitute the Build Command after approval. Never change Start. Restore Build after the schema receipt is confirmed; deploy runtime only through a subsequent separately authorized normal build. This implementation does not alter any Render setting automatically.

## Identity and read-only planning

1. Record the current successful Render deployment ID and full commit, plus an available complete database backup/recovery reference and tested restore procedure. Do not infer the live revision from a local branch. Preserve payment continuity; a code rollback cannot reverse payments.
2. Independently obtain the exact intended external PostgreSQL host, port, database, role, and cluster system identifier from trusted existing database/provider evidence. `SELECT current_database(), current_user, system_identifier::text FROM pg_control_system();` is the identity query. The runtime role must already be authorized to inspect it. If Render denies it, **STOP**; do not weaken or bypass cluster binding or grant broad privileges just to run this build. Do not substitute a Render service ID for PostgreSQL's system identifier.
3. Retain all existing production environment variables, including DATABASE_URL, Paystack LIVE configuration and trusted CA configuration. Do not paste credentials into a command, approval, repository or log. The runner selects the same `config.settings.render` settings as production. It rejects anything except PostgreSQL `sslmode=verify-full`, a readable CA bundle, and an exact external hostname. It also checks `pg_stat_ssl` for the connected session. No TLS fallback is implemented.
4. After approval to change Render settings, set these temporary environment variables using the dashboard's protected environment controls. Use **Save only**, not Save and deploy, when editing variables. Prevent command changes/auto-deploys from launching an unintended normal deployment while configuring them:

```text
DAWANA_PHASE_A_MODE=plan
DAWANA_PHASE_A_DATABASE=<independently verified exact database>
DAWANA_PHASE_A_HOST=<full external TLS hostname>
DAWANA_PHASE_A_PORT=5432
DAWANA_PHASE_A_ROLE=<exact existing database role>
DAWANA_PHASE_A_CLUSTER_ID=<exact PostgreSQL system_identifier decimal string>
```

`RENDER=true` and `RENDER_GIT_COMMIT=<full 40-character commit>` must be supplied by Render. Do not spoof these to bypass a missing release identity. The five expected identity values must be entered independently; they are not inferred from DATABASE_URL.

Compatibility is verified at the source/synthetic level only. The existing Render settings consume DATABASE_URL and production variables without replacing existing Paystack LIVE values, require an external matching hostname, and resolve DB_SSLROOTCERT or the OS trusted CA bundle. A custom CA path must actually be readable **during the build**, not only by the running service. Existing secret-file paths, network allowlists and the role's permission for pg_control_system() must be checked on the actual service. If any prerequisite is missing, stop instead of changing DB_SSLMODE, using an internal hostname, granting new privileges, or weakening certificate verification.

Render documents environment-variable **Save only** behavior at https://render.com/docs/configure-environment-variables and build/deploy sequencing at https://render.com/docs/deploys. These describe platform behavior, not this account's current settings. If a commit is eventually published after approval, retain `[skip render]` in its message and ensure the final merge commit also skips auto-deployment or auto-deploy is explicitly disabled before publication. A skip phrase in a child commit does not guarantee the merge commit will skip deployment.

5. Use the temporary Build Command on the exact approved release commit. The plan runs in a read-only transaction and prints a JSON object containing `release_commit` and `manifest`; it never applies migrations. The JSON has no passwords or connection URL. It includes operational database/role/cluster identifiers, so keep approval evidence private. Save that JSON verbatim for review. Planning refuses an empty plan, any other pending migration, backwards steps, missing target, conflicts, inconsistent history, unexpected target operations, busy lock, identity mismatch or missing TLS.

## Separately approved manifest

Review the generated manifest before authorizing application. It must contain exactly one step:

```text
app: dic
name: 0041_phase_a_order_lifecycle
```

Verify its source SHA-256 against the exact deployed release's migration bytes, dependencies (0040 plus swappable user dependency), full target identity and `plan_sha256`. Do not fabricate a manifest from assumptions about the production migration state. Add the approval evidence fields to the saved JSON object, retaining `release_commit` and `manifest` unchanged:

```json
{
  "release_commit": "<exact planned Render commit>",
  "manifest": {"<entire actual manifest>": "copied unchanged, not this placeholder"},
  "approved_by": "<named approving owner>",
  "approved_at": "<approval timestamp with timezone>",
  "backup_reference": "<verified backup/PITR reference; no credentials>",
  "restore_procedure": "<verified private recovery procedure reference>",
  "rollback_decision": "<retain additive 0041 schema; roll back code if needed>"
}
```

This is a template, not an approval. The validator requires exact manifest equality and non-empty evidence; it does not authenticate a human signature or independently verify backup quality. The owner must approve the actual file through the established review channel. Access to Render environment settings is an authorization boundary.

With a trusted local Python installation, encode the exact approved UTF-8 file bytes (without modifying them afterward):

```sh
python -c "import base64,hashlib,pathlib; b=pathlib.Path('phase-a-approval.json').read_bytes(); print('DAWANA_PHASE_A_APPROVAL_B64='+base64.b64encode(b).decode()); print('DAWANA_PHASE_A_APPROVAL_SHA256='+hashlib.sha256(b).hexdigest())"
```

Keep that output private. Base64 is not encryption. Put the two values into protected Render environment variables, and change only `DAWANA_PHASE_A_MODE=apply`. Keep identity variables, code commit, all payment settings and TLS settings unchanged. Any change to the release commit or pending plan requires a new read-only plan and approval; do not edit an approval to force it through.

Run the temporary build once after approval. The application path acquires a non-blocking transaction-scoped advisory lock, verifies connected identity/TLS, recomputes the complete pending graph, compares the approved manifest and applies only 0041. DDL, migration recorder entry and final no-pending check are in the same PostgreSQL transaction. Lock timeout is 5 seconds and per-statement timeout is 120 seconds. No provider/payment call, expiry activation, permission signal, refund or registration rewrite is performed.

## Log interpretation

Read-only success:

```text
[phase-a-migration] PLAN: read-only; no migrations applied.
{"manifest": ..., "release_commit": ...}
[phase-a-migration] COMPLETE: database step finished; deliberately failing build to prevent backend promotion.
```

SQL success (emitted only after transaction commit returns):

```text
[phase-a-migration] APPLIED: dic.0041_phase_a_order_lifecycle committed; no pending migrations.
[phase-a-migration] COMPLETE: database step finished; deliberately failing build to prevent backend promotion.
```

Both are followed by a **failed Render build** because exit 1 is the promotion barrier. A failed Render status alone does not prove SQL failure.

Guard failure:

```text
[phase-a-migration] STOP: <fixed guard code>
[phase-a-migration] STOP: migration build blocked; no backend promotion.
```

Examples: `EXPLICIT_IDENTITY_REQUIRED`, `VERIFY_FULL_REQUIRED`, `ENDPOINT_MISMATCH`, `CONNECTED_IDENTITY_MISMATCH`, `UNEXPECTED_PENDING_PLAN`, `APPROVAL_RELEASE_MISMATCH`, `APPROVAL_DIGEST_MISMATCH`, `APPROVAL_PLAN_MISMATCH`, `MIGRATION_LOCK_BUSY`, `SCHEMA_STILL_PENDING`. Unexpected settings/SQL/TLS/privilege errors use `INTERNAL_FAILURE_REVIEW_PRIVATELY`; exception text, SQL diagnostics and credentials are deliberately suppressed. Inspect failures using authorized private database/provider diagnostics, without printing the production environment.

`NO_PENDING_MIGRATIONS_VERIFY_PRIOR_ATTEMPT` means stop and inspect the migration recorder/schema before doing anything else. It may mean a previous attempt committed. Never delete the recorder entry or fake/unapply a migration to get past this guard. An interrupted connection at COMMIT can leave the result uncertain even without an APPLIED marker. Obtain read-only applied-migration/schema evidence; do not blindly retry or treat this as confirmed rollback.

## Completion and rollback

- On guard failure before DDL: old production deployment stays active. Correct only the specific cause after review. Never bulk-apply other pending migrations.
- On SQL/postcheck failure before commit: PostgreSQL rolls back this atomic migration. Confirm actual recorder/schema state if the connection was interrupted. Never drop tables or edit records speculatively.
- After confirmed APPLIED: retain the three additive tables and recorder entry. Do not reverse 0041, delete rows, restore an older database or activate expiry. Record the release commit, APPLIED marker and backup reference privately. Remove temporary approval/identity/mode variables through protected settings controls, restore the permanent Build Command, and retain the unchanged Start Command. These settings changes/deployment still require owner approval.
- Deploy the compatible backend normally only after schema confirmation and approval. If runtime fails, redeploy the previously recorded successful Render artifact/commit while retaining additive schema; verify old runtime compatibility before that rollback. Do not change Paystack LIVE settings. Verify health and existing paid-registration access without creating live charges. Frontend deployment is outside this migration-build change.
- Database disaster recovery is a separate controlled operation: preserve/reconcile payments received after the backup and obtain explicit approval before restoring. A schema rollback is not a payment rollback.

## Validation

Local isolated validation: **16 focused tests passed**. The suite covers exact-plan enforcement, wrong identity, busy locks, approval/source/commit binding, TLS downgrade refusal, transaction failure/postcheck refusal and secret-safe error logs. Behavioral tests run the actual Bash wrapper with synthetic Python success and failure; both return exit 1. A fresh-process synthetic Render settings check blocks dotenv, sockets and database connections, verifies existing LIVE payment values survive unchanged, and rejects weaker TLS, missing CA and internal hostnames. No real payment credential is used. Actual RC3 graph inspection uses MigrationLoader(None), without a database connection, checking conflicts, 0041 as the dic leaf, and dependency on 0040. Python syntax, Bash syntax and staged diff whitespace checks passed. Transaction/DDL failure tests use synthetic doubles; no real PostgreSQL migration or live TLS handshake was exercised.

Git Bash was found at `C:/Program Files/Git/bin/bash.exe`; the earlier note that Bash was unavailable applied only to PATH discovery. Source syntax and shell checks are now executable locally. The new CI-safe workflow repeats guards, shell syntax, both intentional-failure paths and graph inspection. **GitHub-hosted CI has not run for this unpublished commit**; querying existing checks failed because GitHub access is blocked. Local execution is not reported as a GitHub CI pass. Tests do not establish actual Render connectivity, CA contents, role permissions or production schema state; those remain fail-closed release prerequisites.
