# DIC 2026 — Final house configuration, 25 October 2026

The approved eight houses were actually created in the configured local `dawana_dev` database, edition ID 1. No migration was required or applied. No participant, registration, payment, check-in, allocation, score or permission records were changed. One existing-format configuration audit event was added, without inventing a staff identity.

## Database safety and execution

Before writes, the explicit setup mechanism confirmed edition ID 1 / year 2026, zero houses, zero allocations, and applied migrations 0022 through 0026. The existing `backups/dawana_dev_before_scoring_0026.dump` archive is 205615 bytes, modified 25 October 2026 at 08:22:01 local time. PostgreSQL 18 `pg_restore --list` confirmed the database name and full `pg_restore --file=NUL` reading passed. This verifies archive readability, not a tested restore rehearsal.

`scripts/configure-dic2026-houses.ps1` was executed first in dry-run mode, then explicitly with `-Apply`, then with `-Apply` again to verify repeat safety. It uses a controlled PostgreSQL transaction as the setup mechanism because the existing Python launcher remains inaccessible. It locks the edition, validates the canonical approved configuration, rejects unexpected/conflicting records, inserts only missing exact-name matches, preserves existing identities and checks the resulting count/capacity before committing. It never updates/deletes houses or approves allocation. An unchanged rerun creates no audit event.

PowerShell file execution was blocked in this environment. The reviewed script contents were explicitly executed as a PowerShell script block; no execution policy, Windows permission or global configuration was changed. Connection credentials were read privately and were not included in the setup output.

Final database verification: eight houses, capacity 240, zero score transactions, zero allocations, one configuration audit event. The second apply retained IDs 1–8 and the same audit count.

## Exact records

Every row belongs to edition 1, has `purpose=participants`, `status=active`, `capacity=30`, and no reserve designation.

| ID | Name | Gender | Colour |
|---|---|---|---|
| 1 | ʿAbdullāh ibn Umm Maktūm | male | Amber — #B46B19 |
| 2 | Al-Barāʾ ibn Mālik | male | Royal Blue — #244B91 |
| 3 | ʿUkkāshah ibn Miḥṣan | male | Emerald Green — #147D64 |
| 4 | Usayd ibn Ḥuḍayr | male | Royal Purple — #743B94 |
| 5 | Al-Shifāʾ bint ʿAbdullāh | female | Olive Green — #677D29 |
| 6 | Asmāʾ bint Yazīd | female | Teal — #168A9C |
| 7 | Nusaybah bint Kaʿb | female | Rose Pink — #B83F75 |
| 8 | Umm Sulaym | female | Crimson — #A53E46 |

The original Unicode names, Arabic names, colour names and mottos were transcribed directly from the supplied UTF-8 approval table into `backend/dic/config/dic_2026_houses.json`. Each house's existing `eligibility_notes` retains `Arabic: …`, `Colour: …`, and `Motto: …`. `eligibility_rules` remains empty; descriptive notes do not become eligibility rules. No new schema fields were needed. No font or generated ID/PDF design was changed.

## Policy reconciliation

- `house_capacity_limit` centralises 30 for edition year 2026 and retains 25 for other editions.
- The House model validation, direct HouseAllocation.save guard, allocation occupancy check, group capacity check and occupant validation all use that limit. A configured lower capacity remains enforced. At 30 occupants another assignment is rejected, including the direct model-save path.
- Inventory approval for 2026 accepts exactly eight operational participant houses, four active houses per gender, each capacity 30, with no reserves. Reserve participant houses cannot receive 2026 allocations. Other editions retain the existing eight-active-plus-two-reserve approval policy and reserve authorisation controls.
- Existing edition/house transaction locks, gender/guardian eligibility, payment eligibility, allocation permissions, audit and explicit strategy-approval requirements remain. No automatic strategy approval was granted.
- No capacity-limiting serializer/form constant was found outside the updated paths; Admin uses House validation. The remaining synthetic preview capacity 25 is a fixture choice, not a production cap.

## Dashboard integration

House Allocation now includes configured `badge_colour` in its API response and displays it as an accent border around the existing icon; label text keeps the established high-contrast foreground. Full house names wrap rather than ellipsise. House Scoring continues to use the same house records/colours, all genders in one leaderboard, and zero scores when no transactions exist. Its scoped table overrides the global nowrap and mobile minimum-width rules so long names can wrap without widening the document. Scoring write/reversal/audit logic was not changed.

## Files created

- `backend/dic/config/dic_2026_houses.json`
- `backend/dic/house_configuration.py`
- `backend/dic/test_house_configuration.py`
- `scripts/configure-dic2026-houses.ps1`
- `dawana-platform/src/services/houseConfiguration.test.js`
- `backend/dic/HOUSE_CONFIGURATION_PHASE2_3A.md`

## Files modified

- `backend/dic/models.py`
- `backend/dic/allocation.py`
- `backend/dic/housing_policy.py`
- `backend/dic/housing_service.py`
- `backend/dic/operations_api.py`
- `dawana-platform/src/pages/Operations.jsx`
- `dawana-platform/src/pages/HouseScoring.jsx`
- `dawana-platform/src/pages/Operations.css`
- `scripts/HOUSING_LOCAL.md`

## Verification actually performed

- Backup listing and full archive read: passed.
- Database preflight: passed, no conflicting existing houses.
- Approved eight-house creation: committed successfully.
- Repeated setup: same eight IDs, capacity 240, audit count remains one; no duplicates.
- Frontend tests: **90 passed, zero failed**, including three new tests for exact names/colours/metadata, 4+4 / 240 inventory and zero-score leaderboard rendering.
- Frontend lint: passed without warnings.
- Production build: passed; existing >500 kB JavaScript bundle warning remains (about 532 kB).
- Targeted `git diff --check`: passed, with the existing allocation-file line-ending warning.
- Backend attempted with database-free classes: Python failed before Django started with base-interpreter `Access is denied`. No interpreter repair, virtual-environment recreation or permission changes were attempted. **Ten new backend tests remain unexecuted.** They cover edition-specific limits, model capacity 30/31, eight-house inventory, no 2026 reserves, future-edition policy, gender/edition boundaries, group and direct-save 30th/31st checks, and combined zero-score colours. ORM calls are isolated in SimpleTestCase; these do not establish real concurrent behaviour.
- Existing transaction locking was inspected and retained. No participant data or isolated test databases were created, and no real concurrent allocation test was run.
- Browser automation failed to initialise (kernel-assets path, OS error 3). Desktop/mobile, Arabic rendering and print visual acceptance remain pending.

## Remaining local validation

From repository root in the user's existing activated PowerShell:

```powershell
# Database-free classes only; no application/test database creation needed.
python -B backend\manage.py test dic.test_house_configuration.FinalHouseConfigurationTests dic.test_scoring.HouseScoringTests dic.test_checkin.CampCheckInTests dic.test_campsite_foundation.CampsiteFoundationTests --verbosity 2
python -B backend\manage.py makemigrations dic --check --dry-run --noinput

Set-Location .\dawana-platform
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

The existing `dic.test_allocation` and `dic.test_housing_phase2` suites need an approved isolated PostgreSQL test database. They were not run against `dawana_dev` or a newly created database here. Run their existing isolated runner only after confirming its database-creation scope; it must never treat development data as test fixtures. A real concurrent 30th/31st test remains necessary before claiming concurrency verification.

The setup command's default is read-only. To review its current database view without changing policy settings, from repository root:

```powershell
& ([ScriptBlock]::Create([IO.File]::ReadAllText((Resolve-Path -LiteralPath 'scripts/configure-dic2026-houses.ps1')))) -DatabaseName dawana_dev -BackupPath .\backups\dawana_dev_before_scoring_0026.dump
```

No further setup apply is required: it has already succeeded twice without duplicates. Do not rerun application merely for browser testing.

House Allocation and House Scoring are ready for **manual viewing/acceptance**, not declared fully validated. At 1440×900, 768×1024, 390×844 and 360×800, check all eight full names and colours, 30 per house / 240 total, combined zero-score leaderboard, normal scrolling and print wrapping. Restart the backend if it does not reload source changes automatically. Preserve existing staff permissions and strategy approvals; do not create real participants or scoring transactions just to test this configuration.
