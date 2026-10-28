# Phase 2 housing — local operation

**DIC 2026 final configuration supersedes provisional inventory:** eight active
participant houses (four per sex), capacity 30 each, no reserves, total 240.
See `backend/dic/HOUSE_CONFIGURATION_PHASE2_3A.md` and the canonical
`backend/dic/config/dic_2026_houses.json`. Other editions retain the existing
25-person policy and reserve support. Do not apply the provisional 25-person /
two-reserve arrangement below to DIC 2026.

Update: the retained 24 October validation report discovered 42 tests but executed
only 10. That old PASS is incomplete. Use the corrected execution-accounted runner
and see [IDENTIFICATION_LOCAL.md](IDENTIFICATION_LOCAL.md) for the combined 60-test
Phase 2/3 validation and browser-preview command.

Work only in `C:\Users\hp\Desktop\DA'WANA WEB--APP`. No worker, migration,
role assignment, deployment or inventory seeding runs automatically.

## File inventory for this phase

Created:

- `backend/dic/housing_models.py`, `housing_policy.py`, `housing_service.py`,
  `housing_queue.py`, `housing_admin.py`
- `backend/dic/management/commands/process_housing_allocations.py`
- `backend/dic/migrations/0022_housing_guardians_queue.py`
- `backend/dic/templates/admin/dic/housing_review.html`
- `backend/dic/test_housing_phase2.py`
- `scripts/HOUSING_LOCAL.md` (this runbook)

Extended:

- `backend/dic/models.py`, `allocation.py`, `admin.py`, `test_allocation.py`
- `backend/dic/templates/admin/dic/allocation_console.html`, `allocation_confirm.html`
- `scripts/validate_dic_backend.py`, `validate-dic-backend.ps1`, `local_preview.py`
- `.gitignore` (private validation logs)

Pre-existing showcase, registration, Paystack, Media and local recovery changes are
not part of this phase and remain intact. No new dependencies are required.

## Validate first

From the repository root in your working PowerShell:

```powershell
.\scripts\validate-dic-backend.ps1 -HousingOnly
```

If necessary append `-PythonExe 'C:\path\to\working\python.exe'`.
This runs Django checks, migration-state parity and **only**
`dic.test_allocation` / `dic.test_housing_phase2`. It uses a new UUID-named local
PostgreSQL test database, refuses reuse, and retains it after completion. It never
migrates the application database or reuses/deletes `test_dawana_dev`. The local
role needs CREATEDB; the runner never changes role privileges. Tests may flush
records inside their newly created isolated test database, including concurrent
TransactionTestCase tests. External network connections are blocked in tests.
No ffprobe, frontend or payment test reruns are needed for this housing suite.
Redacted logs/JSON are written to ignored `validation-results/`; do not publish them.

Python is inaccessible in Codex's process, so runtime tests and migration parity
must be confirmed with this command before treating the implementation as verified.

## Apply locally and inspect Admin

After tests pass, use the existing backup-gated startup:

```powershell
.\scripts\start-local-preview.ps1 -PgDumpPath 'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe'
```

It requires the exact local DB confirmation, a nonempty custom archive and successful
pg_restore read checks before running migrations. Do not confirm an unintended target.
Migrations through `0022_housing_guardians_queue` must be applied to your verified,
backed-up local development database only. Stop any existing preview servers first;
the startup script refuses occupied ports and never kills them.

Open http://127.0.0.1:8000/admin/ using an authorized local staff account.

- **Camp editions:** housing reference date, balanced strategy and existing strategy
  approval action. DIC 2026 uses **2026-12-23**. Future editions require their own date.
- **Houses:** actual names, sex, purpose, capacity, status, occupancy and reserve
  authorization. Verify **four Active general houses and one Reserve per sex**, all
  capacity 25. This is 200 general / 250 potential occupants. Never create guessed
  official names or count dedicated accommodation as general inventory.
- **Guardian relationships:** create a pending child/female guardian link, save,
  then use its supervisor review link. Record a reason and explicit approval.
  Both need verified paid registration. Sharing an order never establishes guardianship.
- **Housing jobs:** inspect pending / processing / completed / held / failed states,
  reasons and attempts. An explicit supervisor retry with reason is needed after a hold
  or failure. Retry alone does not run a worker.
- **House allocations:** existing manual assignments and release/reassign links remain.
  Select the guardian to assign a new group; the service includes all linked dependents.
  Selecting an already allocated child/guardian for release or reassignment affects the
  **entire** group. A reason is required. Prior rows and history are retained.
- **DIC admin audit events:** immutable actor, timestamp, processing transitions,
  relationship decisions, before/after allocation IDs, houses and reasons.

No records are seeded by this feature. In `0022`, only the newly added reference date
for an existing 2026 edition is initialized and current Reserve houses receive a durable
reserve designation. House names, capacities, occupants and previous approval records
are retained. New configuration fingerprints invalidate old automation approvals
without erasing them. Downgrading this migration would remove its new tables/fields;
do not roll it back or delete its records without a separate data-preservation plan.

Before enabling automation, reconcile any pre-existing allocations that do not meet
the new policy. A blank capacity, unsupported JSON eligibility rules, wrong inventory,
missing reference date or stale approval blocks automatic allocation. Approval requires
the supervisor to verify real operational names and inventory and record the approval
reference. Reserve activation changes the fingerprint and requires strategy reapproval.
Reserve houses retain Reserve status; deactivating them does not remove their designation.
No names or operational inventory are inferred from the configured target counts.

## Supervisor permissions

Use an existing local superuser or explicitly assign granular permissions to approved
housing supervisors; this task does not grant anyone new privileges automatically:

- `can_allocate_participants`, `can_reassign_allocations`, `can_release_allocations`
- `can_activate_reserve_houses`, `can_approve_allocation_strategy`
- `can_approve_housing_guardians`, `can_process_housing_queue`
- Relevant view permissions for camp editions, houses, participants, guardian
  relationships, housing jobs, allocations and audit events; relevant existing
  house/edition change permissions for configuration.

All service mutations require active staff with the relevant permission. Existing
manual allocation can handle an incomplete general inventory, but cannot bypass age,
verified payment, guardian, reserve, dedicated-policy or capacity safety rules.
Dedicated fathers/authorized male administrator accommodation remains separate and
held pending committee policy; its participant flag alone does not authorize placement.

Guardian approval uses the authorized supervisor's assessment of the mother/female
guardian. The guardian must be independently accommodated (age 6+); no extra minimum
adult-age rule is invented. Record real safeguarding approval in the review reason.
Do not use the absence of a programmed adult-age threshold to approve an unsuitable guardian.

## Bounded worker

Run manually only after confirming inventory, approvals and local participants.
Replace the two IDs with actual local Admin record IDs; never put credentials in arguments:

```powershell
$editionId = [int](Read-Host 'Local camp edition ID')
$supervisorId = [int](Read-Host 'Authorized local housing staff user ID')
.\backend\.venv\Scripts\python.exe backend\manage.py process_housing_allocations --settings=config.settings.development --edition $editionId --actor $supervisorId --database-name dawana_dev --limit 50
```

The command requires development settings, a loopback PostgreSQL target, exact DB-name
confirmation and both processing/allocation permissions. `--discover-only` creates
bounded queue entries without allocating. `--limit` is 1–1000 and bounds discovery
and claimed jobs separately. One job can atomically allocate its entire guardian group.
There is no daemon, payment hook, Redis or Celery dependency. Discovery is idempotent,
using existing confirmed orders with successful verified payment attempts. Existing
jobs, including supervisor holds and released groups, are never silently reset.

Claims commit before allocation, use PostgreSQL `SKIP LOCKED`, a unique claim token
and a 15-minute recovery lease. Allocation locks the edition before jobs/houses;
concurrent group jobs cannot split the group. A stale token cannot process a recovered
job. Interrupted claims recover on a subsequent invocation; after three attempts an
expired claim fails for explicit supervisor retry. Held/failed policy cases never
loop automatically. Unexpected errors persist only the error class, not raw exceptions.
A database outage can leave a committed processing claim; it is recoverable after
the lease once connectivity returns. No existing database is dropped by the worker.

Each group is allocated or held intact. Children count as occupants, must be 0–5 on
the reference date, and always share a regular female house with the approved guardian.
Missing/unapproved/unpaid/ineligible guardians hold the whole group. Reserves are
excluded for dependent groups even if authorized. Ages 6+ allocate independently.
For independent participants the deterministic house order is: general before reserve,
fewest occupants in that participant's age band, lowest total occupancy, case-folded
house name, then house PK. For groups, minimize the sum of each existing occupant's
matching incoming age-band count (equivalently, existing count times incoming count
for each band). This considers both guardian and child bands; capacity and all
guardian rules take precedence. Age bands are exactly
0–5, 6–10, 11–13, 14–16, 17+. Each child's occupancy is included in later counts.

Releasing a group creates/holds its queue entries, preventing automatic rediscovery
from undoing a supervisor release. Relationship revocation requires release of the
allocated child/group first. Historical links cannot be reopened or silently edited.
Payment status changes do not automatically evict existing occupants: supervisors
must review/refund/withdrawal cases and release/reassign through the protected controls.

Future scheduling, after infrastructure approval, can periodically invoke this bounded
command (or a separately reviewed deployment-specific wrapper). Its current local-only
guard must not be removed casually. No scheduling or production worker is enabled here.

## Phase 3 compatibility

Participant IDs, edition IDs and existing HouseAllocation/history remain authoritative.
No second housing assignment table, portal, digital ID or examination flow is created.
Phase 3 should read current authorized allocations and account for holds/releases;
do not embed a permanent house assignment in a QR code. Runtime validation and local
Admin review must pass before treating Phase 2 as ready for Phase 3 integration.
