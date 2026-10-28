# Controlled legacy preview recovery — prepared, not executed

## Why a different recovery path is needed

The old `.local-preview/servers.json` records backend launcher 22928 and frontend
launcher 1152 but no exact creation times. Its referenced backend/frontend logs
both have the `20261024-115322` launch timestamp and were created at 11:53:22.
Those corroborate the session; they cannot prove exact historical process identity.
Do not add current creation times to that manifest as though captured at launch.

The user-confirmed read-only audit has established the current project process
tree, port owners and database:

`dawana_ids_demo_c936c26ba558429eb4b4fda3b5c62668`.

All 36 identification tests are reported passed. None of that permits arbitrary
Python/Node termination or proves historical metadata that was never recorded.

The supported recovery is a **new, explicit authorization to shut down the currently
verified demo processes and launch a fresh normal preview**, rather than silently
upgrading the historical manifest. It preserves the original manifest and records
a separately labelled recovery-time observation. The resulting fresh launch saves
its own actual process creation times for future normal restoration.

## Prepared implementation

`restore-normal-preview.ps1` adds `-AuthorizeLegacyShutdown`. This is accepted only
with both `-Restore` and `-DemoFormatsReviewed`, and only for a legacy manifest.
Normal `-Restore` still refuses a legacy manifest. No old timestamp check or
process ownership rule is disabled by this recovery option.

The following checks remain mandatory:

- Confirm exact project interpreter/helper/serve and Vite launch arguments.
- Recursively verify all Python descendants, allow only validated Windows console
  hosts, and refuse unknown processes or inaccessible metadata.
- Correlate launcher times with the old timestamped logs. Refuse disagreement.
- Verify loopback port 8000 belongs to the backend tree and port 5173 to Vite.
- Query the actual running database through Django and the Vite proxy.
- Pin this one-time recovery to the confirmed demo DB named above; a different
  session needs separate review rather than inheriting this authorization.
- Run the complete isolated identification validation, requiring success.
- Perform `local_preview.py prepare --no-migrations`, verifying **dawana_dev**,
  Django checks, actual database identity and no pending migrations. This does not
  migrate, seed, update, restore or delete application records. If migrations are
  pending, leave the demo running and obtain separate authorization for the existing
  verified-backup migration procedure. Do not drop the no-migrations flag casually.
- Display the currently verified process list and require a typed confirmation.
- Rebuild and compare the full current process tree, exact observed creation times,
  parent IDs, executable paths, command lines, port ownership and running DB identity.
- Refuse if the original manifest hash changed during review.

Before any shutdown, the original manifest is copied using exclusive creation to
`.local-preview/legacy-manifest-<uuid>.json` and SHA-256 checked. A separate
`legacy-recovery-observation-<uuid>.json` records the observation timestamp, observed
process creation times/commands, current DB, intended target and authorization user.
It explicitly says these are **not reconstructed historical launch timestamps**.
No existing manifest, log, backup or observation is deleted.

Only verified Python/Vite processes are stopped, deepest first, with identity
checked again immediately before each termination. Console hosts are never explicitly
terminated; Windows manages their lifetime. No PostgreSQL/browser/unknown process is
targeted. The normal launcher then starts Django/React with `-NoMigrations` and
verifies health, direct/proxied `dawana_dev` identity and the configured DIC response.

`start-local-preview.ps1` now also archives and hash-verifies any previous manifest
before writing its new session manifest. The old manifest is never blindly lost.
Fresh manifest creation times describe the fresh processes, not the old demo.

## Exact procedure after the user authorizes execution

Do **not** execute the shutdown/restart command during this preparation task.
Do not use old PIDs as direct Stop-Process targets.

From the original Desktop project, a read-only audit remains safe:

```powershell
.\scripts\restore-normal-preview.ps1
```

Review its current process list, port ownership and matching demo database. Stop
if ownership has changed or the command cannot inspect metadata. Do not bypass
execution policy or run broad kill commands to work around a failed audit.

After independently reviewing both ID formats and receiving explicit authorization
to shut down this demo session and launch normal development, run:

```powershell
.\scripts\restore-normal-preview.ps1 -Restore -DemoFormatsReviewed -AuthorizeLegacyShutdown
```

The script reruns the gates above before asking you to type:

```text
STOP VERIFIED DEMO AND RESTORE dawana_dev
```

Only type that exact phrase after verifying the displayed current process evidence.
Any different response aborts with nothing stopped. Supplying switches alone is
not enough. There is no noninteractive confirmation bypass.

Safe automation after confirmation is limited to the verified process shutdown,
fresh no-migrations startup, archive creation and post-start identity/health checks.
Uncertain process ownership, an unexpected DB, failed tests or pending migrations
requires human review; the script does not repair those automatically.

## Preservation and failure handling

- Both the synthetic DB and dawana_dev remain in PostgreSQL. No DB is dropped,
  recreated, restored, seeded or migrated by recovery.
- Existing files, test DBs/results, synthetic records, media, logs, stash and recovery
  backups remain. Only new audit files/new normal-session manifest are written.
- The script cannot guarantee restart will succeed. If startup fails after shutdown,
  keep the archived manifest/recovery snapshot and inspect the retained logs. Do not
  rerun legacy recovery against newly reused PIDs or overwrite fresh metadata.
- After fixing the prerequisite, start the normal preview only when ports are free:
  `.\scripts\start-local-preview.ps1 -NoMigrations`.
- The demo can later be served from its retained manifest with
  `.\backend\.venv\Scripts\python.exe -B scripts\id_demo.py serve`, only after
  ownership review and without duplicating a backend on port 8000. This does not reseed it.
- A current manifest/archive hash is evidence of preserved bytes, not an independent
  proof of old process ownership. Typed authorization is specifically for the verified
  **current** tree, and the original limitations remain documented.

## Verification status of this preparation

Scripts were inspected and edited only. PowerShell syntax and whitespace are checked
without invoking the scripts. No restoration/audit command, test run, process stop,
server restart or database query was executed as part of this task. User-reported
36/36 and the passing live audit remain external evidence, not newly rerun results.

After authorized recovery, inspect http://127.0.0.1:5173/dic and the printed
direct/proxy database checks. Values must come from dawana_dev; any incorrect data
there must be reported rather than replaced or hardcoded.
