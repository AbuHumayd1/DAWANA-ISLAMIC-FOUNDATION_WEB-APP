# Manual production schema recovery

Preparation only. No production access has been attempted.

## Configure before the first run

1. Review and publish the workflow, recovery/preflight/native Python helpers,
   synthetic/integration tests and this runbook from the exact
   approved source revision. The workflow must exist on the default branch for
   workflow_dispatch. Use a reviewed publication process that avoids unintended
   Render auto-deployment (Render supports a [skip render] commit message).
   Keep the selected recovery branch/tag at that exact revision through both phases.
   The existing Render Build/Start Commands and startup scripts are unchanged.
2. In GitHub Settings > Environments, create production-preflight and
   production-initialize. Restrict both to the reviewed recovery ref. Require
   owner review for production-initialize, disable approval bypass where available,
   and confirm these controls are supported for the repository's visibility/plan.
   Do not rely on GitHub silently creating an unprotected environment.
3. Verify production is PostgreSQL 18 and set repository variable
   RECOVERY_POSTGRES_MAJOR to 18. This workflow installs PostgreSQL 18 client and
   server packages explicitly on ubuntu-24.04 using the signed official PGDG Apt
   repository. It calls /usr/lib/postgresql/18/bin executables, verifies client
   versions and checks the connected production server major. A mismatch stops
   recovery; a variable/default is not independent proof of the server version.
4. Add these secrets to BOTH environments with identical values:
   * RECOVERY_DJANGO_ENV: a JSON object of the approved Render Django environment,
     including DATABASE_URL with the external endpoint, DJANGO_SECRET_KEY,
     PUBLIC_HOST, FRONTEND_ORIGIN and required production settings. Values are
     strings. Use the existing pre-live Paystack configuration; this workflow
     refuses live mode. Do not include GitHub/runner controls or PG* variables.
   * RECOVERY_EXPECTED_HOST: independently verified full external hostname.
   * RECOVERY_EXPECTED_SCHEMA: independently verified effective target schema.
   * RECOVERY_EXPECTED_CLUSTER_ID: independently verified PostgreSQL system ID.
   * RECOVERY_BACKUP_KEY: one securely generated base64-encoded 32-byte random key.
     Retain it securely for the backup's lifetime, including after workflow removal.
5. Verify GitHub-hosted runner egress is permitted by the database access policy.
   A GitHub runner does not inherit Render private networking. Do not broaden the
   database allowlist to all addresses. If current policy excludes hosted runners,
   stop and arrange approved runner egress access before running this workflow.
6. Confirm the role can read pg_control_system(), dump all database objects/data,
   and create the reviewed schema objects. No privilege changes are performed.
   Extensions in a dump must be available in the native PostgreSQL 18 installation;
   missing extensions or ownership/ACL problems stop the restore test.

## Native isolated restoration and tests

The separate recovery-native-validation.yml workflow runs on pull requests to
main scoped to recovery files and their requirements. It has contents:read only,
no production environment, no secret references and no recovery dispatch. It runs
both suites against synthetic data only, with the same native package/account
setup as the manual workflow. A passing PR check is not production authorization.

Docker is not used by this recovery workflow. No hosting configuration changes.
Before any production-secret-bearing step, the job runs the stdlib-only synthetic
subprocess regressions and a real production-free PG18 integration test. The latter
creates two fresh private clusters, backs up synthetic rows/ownership/ACLs, encrypts
and decrypts the archive, refuses tampered ciphertext, a wrong cluster identity
and an invalid archive,
restores the real archive twice and checks rows, ownership and privileges. Both
test clusters are stopped and removed, including on failure. A failed test stops
the job before it receives production database credentials.

The job creates a dedicated unprivileged, non-login OS account, dawana_restore,
with no home or sudo privileges. Root-owned helper copies in
/opt/dawana-schema-recovery cannot be edited by that account. Each cluster uses a
new /tmp/dawana-schema-restore-<random> directory (0700), a private Unix socket
(0700), peer authentication, rejected host authentication and NO TCP listener.
There is no connection to a package-managed/default local cluster.

The runner and sudo/helper subprocess environments are separated. The restore
server receives no production environment, URLs, tokens, passwords or encryption
key. Only the dump and source role names (recreated as NOLOGIN) are streamed to the
helper. Before any restore/role write the helper verifies the private directory,
receipt, actual cluster system ID, data directory, socket, database, role and PG18
version. Restores preserve ownership and ACLs and use --clean --if-exists
--exit-on-error --single-transaction only against that verified disposable target.

Production pg_dump runs directly as the runner, with explicit connection settings,
verify-full, the readable runner CA bundle and default_transaction_read_only=on.
An exported read-only snapshot remains open for the dump. The dump is private;
only the encrypted archive is uploaded. Raw subprocess stderr and server logs
are never printed or uploaded; failures report allowlisted tool/category/status.
The always-run cleanup stops/removes the receipt-bound cluster and deletes the
runner plaintext archive. Cleanup failure fails the job. Runner destruction is
the final containment boundary for an interrupted/killed job.

Local/CI test commands (integration requires the ephemeral Linux Actions runner,
dedicated account and installed root-owned helpers; no production credentials):

```sh
python -I -B scripts/test_schema_recovery_tools.py
python -I -B scripts/test_schema_recovery_native.py
```

## Phase 1 - PREFLIGHT

1. GitHub > Actions > Production schema recovery > Run workflow.
2. Select the reviewed recovery ref and PREFLIGHT. Leave all other inputs empty.
3. Approve environment access if configured. The job verifies TLS and identity,
   runs the all-schema fresh gate, generates the existing source-hashed migration
   manifest and Django cache DDL, creates a full custom-format backup and actually
   restores it into a disposable loopback PostgreSQL service. Production sessions
   default to read-only and the dump uses an exported read-only snapshot.
4. Wait for SUCCESS, including artifact upload. Download
   production-schema-preflight and retain it in approved secure storage.
   It contains backup.enc (AES-256-GCM encrypted), evidence.json (authenticated),
   manifest.json and cache.sql. Only encrypted backup content is uploaded.
   Artifacts expire after seven days. Retain the archive and key beyond that
   period if required for the production rollback plan.
5. Review every migration and cache SQL against the backup and identity record.
   Record the run ID and both hashes shown in the job summary. No raw backup,
   password, URL or participant rows are printed or uploaded.

The existing cross-schema gate deliberately refuses any existing Django relation,
sequence, relevant function or trigger, including objects hidden by search_path.
If it stops, investigate the schema mismatch or partial initialization instead
of bypassing it. The exact identity is dawana_db / dawana_db_user / port 5432,
plus the independently supplied host, schema and cluster.

## Phase 2 - INITIALIZE

1. Obtain explicit owner approval of the successful preflight's exact manifest,
   cache SQL, encrypted backup hash, identity and rollback decision. Keep
   production writes quiescent from the backup through initialization. Do not
   change source revision or either environment's settings.
2. Run the SAME workflow/ref again, selecting INITIALIZE. Enter:
   * preflight_run: successful Phase 1 run ID.
   * approved_plan_sha256: exact plan hash from the summary.
   * approved_backup_sha256: exact encrypted backup hash from the summary.
   * approval: INITIALIZE dawana_db
3. The owner reviews these inputs and approves production-initialize.
4. The job checks the successful run's provenance, same source/settings/identity,
   authenticated evidence, approved hashes and exact current manifest/cache DDL.
   It decrypts and restores the backup again into the disposable service before
   allowing any production write.
5. Under a workflow concurrency guard and database session advisory lock, it
   repeats the cross-schema gate, runs existing release_migrations with the
   exact approval, creates only the configured dawana_release_cache table, and
   checks migration completion, required model columns and cache privileges.
   It verifies that no edition is active and registration remains closed.

Use a fresh manual dispatch only after reviewing failures. The workflow refuses
GitHub Re-run jobs (run_attempt > 1). A partial application leaves Django objects
and is refused by the fresh gate, requiring a separate reviewed recovery plan.
A completed run also cannot initialize again. There is no automatic database retry.

## Consequences and verification

Migration 0034 seeds approved Early Bird/regular fees and an INACTIVE draft
2026 edition. Migration 0035 supplies the official corrected venue/theme.
This does not recreate missing historical production overrides, accounts or tutor
invitations. No demo fixture loader or edition-activation command is invoked.
Initialization does not open registration or enable live Paystack.

After success, use the existing application logs/API checks. Editorial and showcase
should return 200 with empty published collections when no approved media exists.
Registration options initially returns its deliberate no-active-edition 404.
Publishing the DIC 2026 listing while keeping registration closed is a separate
owner-approved configuration step.

Migrations commit individually, so earlier steps can persist after a later failure.
A code rollback does not reverse them. Stop on failure; do not fake history,
drop/reset tables or automatically reverse migrations. The archive preserves
database ownership/grants, but restore roles are recreated as NOLOGIN for the
isolated test. Actual disaster recovery must separately provision required
login credentials and role memberships, then reconcile any post-backup writes.

No Render settings, application startup mechanism or durable permit system is used.
