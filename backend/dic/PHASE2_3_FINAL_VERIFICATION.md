# DIC 2026 Phase 2.3 — final verification attempt, 25 October 2026

Frontend checks passed. Backend execution and browser visual acceptance remain blocked; Phase 2.3 is not declared fully verified.

## Narrow UI correction

The visible combined-leaderboard description was a caption inside the wide table. It is now a wrapping paragraph before the horizontal scroll region. The empty-state text is outside that region as well. The actual table retains its readable minimum widths and an accessible label. Scoring calculations, approved configuration, print endpoints, permissions and production backend logic were not changed.

## Python investigation

- The current process runs as `CodexSandboxOffline`.
- The existing `backend/.venv/pyvenv.cfg` references Python 3.13.7 under the hp user's local Programs/Python/Python313 directory.
- The virtual-environment launcher starts, but fails to launch that base interpreter with **Access is denied**, before Django imports or tests execute.
- Direct launch and attempts to read the base executable's metadata/ACL were denied. A false Test-Path result accompanying AccessDenied is not evidence that the file is missing.
- Windows `py -0p` successfully identified a separately registered Store Python 3.13 installation under Program Files/WindowsApps. Launching it through `py -3.13` was also denied before Python started.

This evidence points to access/execution restrictions for this Codex process. It does not establish a broken Django application or virtual environment. The exact ACL/sandbox-policy source could not be confirmed because access to the executable and ACL was denied. No Python reinstall, virtual-environment recreation, ACL change, execution-policy change or global Python configuration change was attempted.

## Backend validation prepared and attempted

The existing safe validation runner now accepts `--operations-scoring`, selecting:

- `dic.test_house_configuration` — the ten existing database-free approved configuration/capacity cases.
- `dic.test_allocation` — eligibility, capacity, permissions, allocation history and concurrency.
- `dic.test_housing_phase2` — guardian/housing policy and queue safeguards, including future-edition behaviour.
- `dic.test_scoring` — permission/CSRF, ranking, deductions, reversals, duplicate requests, audit and export cases, plus new database-backed checks.

The runner checks model/migration parity through the existing 0026 scoring graph, creates a new UUID-named local PostgreSQL database, runs all selected tests there, and retains it. It refuses an existing generated name, never migrates the application database or reuses/deletes an old test database, and does not change role permissions. The report records discovered/executed tests; missing or skipped tests prevent a complete pass. Existing test databases are only inspected read-only. Nonlocal network connections are blocked during tests.

Added tests, not executed:

- A 2026 TransactionTestCase fills a capacity-30 house to 29, then starts two competing allocation requests. It expects one success, one rejection and exactly 30 occupants.
- A real-database inventory test checks eight active 30-person houses, four per gender, total 240, without reserves.
- A real-database scoring test checks awards/deductions, repeat-request idempotency, reversal links, preserved originals and exactly one audit per actual write.
- A real-database edition-isolation test rejects foreign houses and cross-edition reversal attempts.

These fixtures are created only by Django's test runner in its isolated database. They were not inserted into development. Existing concurrency and eligibility tests remain intact.

Attempted command:

```powershell
& backend/.venv/Scripts/python.exe -B scripts/validate_dic_backend.py --operations-scoring
```

**Result: blocked at interpreter launch. Zero backend tests executed; no test database was created.** No result is claimed for the ten configuration tests, eight-house approval, eligibility/capacity limits, concurrency, or scoring/audit backend tests.

## Checks actually completed

| Check | Result |
|---|---|
| Frontend tests | PASS — 91 passed, zero failed; includes description/empty-state placement regression |
| Frontend lint | PASS — no warnings |
| Production build | PASS — existing >500 kB bundle warning remains, about 533 kB |
| Targeted git diff --check | PASS |
| Existing venv Python launch | BLOCKED — base interpreter access denied |
| Registered Store Python launch | BLOCKED — process creation access denied |
| Backend tests / actual concurrency | NOT EXECUTED |
| Browser visual verification | BLOCKED — CUA kernel-assets path error, OS error 3 |

There were no executed test assertion failures. The successful frontend checks do not imply backend or visual acceptance.

## Exact local command

From repository root in the user's existing activated PowerShell environment:

```powershell
python -B scripts\validate_dic_backend.py --operations-scoring
```

This command deliberately uses a new isolated database for the requested data-bearing tests. The local PostgreSQL role must already have CREATEDB; the runner refuses to change permissions. Read its actual execution counts and redacted report under `validation-results/`. Do not replace it with a command targeting `dawana_dev`, reuse an existing populated test database or bypass a failed safety check.

For a database-free preliminary run:

```powershell
python -B backend\manage.py test dic.test_house_configuration.FinalHouseConfigurationTests dic.test_scoring.HouseScoringTests --verbosity 2
```

For frontend reruns:

```powershell
Set-Location .\dawana-platform
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

Manual browser acceptance remains necessary: at 1440×900, 768×1024, 390×844 and 360×800, verify the description stays visible and wraps before the horizontal scroller, only the table scrolls sideways, all full names remain readable, and both existing print reports work with authorised access. No real points or development participants are needed for this viewing check.

## Files changed in this verification task

- `dawana-platform/src/pages/HouseScoring.jsx` — move descriptive/empty text outside table scroller.
- `dawana-platform/src/pages/Operations.css` — explicit wrapping for that description.
- `dawana-platform/src/services/houseScoring.test.js` — placement regression test.
- `backend/dic/test_allocation.py` — 2026 final-place concurrency test.
- `backend/dic/test_scoring.py` — three database-backed integration tests.
- `scripts/validate_dic_backend.py` — isolated Operations scoring suite and strict completion accounting.
- `backend/dic/PHASE2_3_FINAL_VERIFICATION.md` — this report.

No development/production records, migrations, approved houses, permissions or production backend business rules were modified. No subsequent phase was started.
