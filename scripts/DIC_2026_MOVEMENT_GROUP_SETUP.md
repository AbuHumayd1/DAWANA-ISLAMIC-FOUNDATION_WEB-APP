# DIC 2026 operational movement groups

26 October 2026. **Prepared only: no database access or group changes were executed by Codex.** The configured Python launcher still fails before Django starts with access denied to its Python313 base executable. The user's confirmed 21 backend passes, applied movement migration and successful camera checks remain prior evidence; they were not repeated.

## Approved exact groups

| Group | Exact permissions |
| --- | --- |
| DIC Movement Viewers | `dic.can_view_dic_operations`, `dic_movement.can_view_movements` |
| DIC Arrival Officers | `dic.can_view_dic_operations`, `dic.can_check_in_dic_participants`, `dic.can_view_dic_ids` |
| DIC Return Recorders | `dic.can_view_dic_operations`, `dic_movement.can_view_movements`, `dic_movement.can_record_movements`, `dic.can_view_dic_ids` |
| DIC Release Officers | All Return Recorder permissions plus `dic_movement.can_authorize_departure` |

No Finance, Django user/group administration, general model CRUD or unrelated DIC permissions are included. Release Officers do not automatically receive initial-arrival authority; that permission is intentionally absent from their requested role. Groups combine with a user's other existing grants; this setup does not remove rights granted elsewhere. Existing superusers retain Django's inherent permission bypass; no superuser flags or operational role memberships are changed.

## Architecture inspected

- `accounts.User` extends Django `AbstractUser`; existing UserAdmin supports group management.
- Installed `django.contrib.auth.admin` registers the standard GroupAdmin. No new Admin or parallel authentication/authorization system is needed. Operational groups do not receive `auth.change_group`/`auth.change_user`; existing authorized administrators manage groups through `/admin/`.
- The six required permission definitions are declared in source on `dic.CampEdition`, `dic.CampCheckIn`, `dic.CampEnrollment` and `dic_movement.Movement`. **Their live database existence remains unverified here.** The new command checks exact app/codename/model and refuses missing or ambiguous definitions without creating permissions or running migrations.
- Existing movement services independently require recording and viewing permission; every departure additionally requires `can_authorize_departure`, confirmation, checked external release authorization and its reference. These policies and the scanner workflow are unchanged.
- The older `setup_dic_staff_roles` command also configures unrelated roles and broad DIC administration. It is deliberately **not reused or invoked** for this task.

## Narrow command and safeguards

New command: `setup_dic_movement_groups`, under the existing DIC management-command package.

Default invocation is a **read-only dry run**. Before any group write it:

1. Requires development settings and configured PostgreSQL `dawana_dev` on localhost/127.0.0.1/::1. It has no alternate-database option.
2. Checks the actual connected database name, PostgreSQL server address and port against configuration; prints the verified identity without credentials.
3. Confirms movement 0001 is recorded as applied and dic 0027 is absent; never changes migration history or schema.
4. Requires all six existing permission definitions on their expected models and existing GroupAdmin registration.
5. Snapshots auth group names/IDs/grants, user memberships, direct user permissions, active/staff/superuser flags and permission definitions. These snapshots stay in process memory; sensitive user fields/grants are not printed.
6. Prints each group's existence, existing member IDs, exact target permissions, additions and removals. Changes to these groups can affect existing members' effective access, but their memberships/direct grants are not edited.
7. Emits a SHA-256 plan fingerprint binding the verified database identity, full auth snapshot and exact proposed changes.

`--apply --expected-plan <fingerprint>` repeats the checks/preview inside a serializable transaction and refuses a changed/stale plan. It uses an advisory lock for this setup command, existing target group row locks, unique Django group names and `get_or_create`. Only the four named groups' permission relations can be changed. Extra permissions are removed **only from those named groups**, as required by the exact requested assignments. Existing memberships remain intact, including members of those groups.

Before commit it checks all four groups' exact permission IDs, existing target group identities and equality of unrelated group/grant state, memberships, direct user permissions, flags and permission definitions. Unexpected changes raise an error and roll back this command. There is no user assignment, User.save, permission-definition creation, migration, camper query/write or movement record operation. A fresh dry run followed by apply is idempotent: already exact groups report unchanged and their permission relation is not rewritten.

## Exact normal VS Code PowerShell procedure

Use normal VS Code PowerShell at the repository root and the existing working backend interpreter. No installation/security change is required or proposed.

First run the ten new **database-free** checks only:

```powershell
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
$movementGroupPython = (Resolve-Path -LiteralPath '.\backend\.venv\Scripts\python.exe').Path
& $movementGroupPython -B .\scripts\validate_dic_movement_groups.py
if ($LASTEXITCODE -ne 0) { throw 'Focused group checks failed or Python is inaccessible. Stop.' }
```

The runner reuses existing synthetic configuration and blocks all Django database connections and external side effects. It does not create a test database or invoke the full test runner/migrations. Expected: **10 passed, no skips**; this result has not been observed in Codex.

Next inspect the actual development connection, definitions, memberships and proposed changes through the dry run:

```powershell
$movementGroupPreview = & $movementGroupPython -B .\backend\manage.py setup_dic_movement_groups --settings=config.settings.development
if ($LASTEXITCODE -ne 0) { throw 'Identity/permission/plan checks failed. Nothing may be applied.' }
$movementGroupPreview | Write-Output
$movementGroupHashLines = @($movementGroupPreview | Where-Object { $_ -match '^PLAN_SHA256: [a-f0-9]{64}$' })
if ($movementGroupHashLines.Count -ne 1) { throw 'Expected exactly one successful plan fingerprint.' }
$movementGroupPlanHash = ([regex]::Match($movementGroupHashLines[0], '^PLAN_SHA256: ([a-f0-9]{64})$')).Groups[1].Value
```

Review the printed local database/port, four groups, existing member IDs and add/remove lists. The user's authorization covers exactly these four groups. If anything differs or definitions are missing, stop; do not run migrations, the older broad role command or ad hoc permission grants to force this through.

Apply only that unchanged plan:

```powershell
& $movementGroupPython -B .\backend\manage.py setup_dic_movement_groups --settings=config.settings.development --apply --expected-plan $movementGroupPlanHash
if ($LASTEXITCODE -ne 0) { throw 'Setup failed or authorization state changed. Review a fresh dry run; do not force/retry an old plan.' }
```

Expected output: created/updated/unchanged for each named group, followed by verification that all four permission sets are exact and unrelated grants/user state/memberships are unchanged. No new memberships should appear. Group creation will not make the role effective for an unassigned user.

Finally rerun the read-only preview:

```powershell
& $movementGroupPython -B .\backend\manage.py setup_dic_movement_groups --settings=config.settings.development
if ($LASTEXITCODE -ne 0) { throw 'Post-setup verification failed.' }
```

Expected: all four existing, Add `(none)`, Remove `(none)`, same member IDs. Preserve this output and apply results. For another apply attempt, obtain its fresh fingerprint rather than reusing the pre-creation hash. Designated official assignments remain a separate manual Admin action and are not performed by this task.

## Verification evidence and limitations

- Both the new guarded test runner and actual dry-run management command were invoked in Codex. Both failed before Python started: `Python313\python.exe: Access is denied.` **Zero new tests executed; zero database reads/writes performed.**
- Source inspection confirms the role requirements match the six declared permissions, GroupAdmin exists, and recording alone is insufficient for departure. Whitespace/diff checks passed; this is not Python execution or database verification.
- Ten prepared tests cover exact role contracts, refusal of unapproved database/host before connecting, repeat planning/idempotence, scoped permission removals, preservation of member lists, stale-plan fingerprints, postcheck protection of unrelated state, non-superuser movement denial, separate release authority and existing Admin registration.
- Actual group existence, live definitions, memberships, idempotent SQL behavior and successful transaction verification are pending normal VS Code execution. No existing users/accounts, grants or unrelated groups have been modified by Codex.

## Files added

1. `backend/dic/management/commands/setup_dic_movement_groups.py` — guarded dry-run/apply command limited to the four exact roles.
2. `backend/dic_movement/test_groups.py` — ten database-free role/safety checks.
3. `scripts/validate_dic_movement_groups.py` — guarded runner for only those new tests.
4. `scripts/DIC_2026_MOVEMENT_GROUP_SETUP.md` — assignments, execution procedure and actual status.

No application workflow, movement authorization policy, historical migration, schema, credential or frontend file changed. No Phase 2 work was started. **Remaining blocker: run the focused tests and dry-run/apply/postcheck commands in the already working normal VS Code backend environment.**
