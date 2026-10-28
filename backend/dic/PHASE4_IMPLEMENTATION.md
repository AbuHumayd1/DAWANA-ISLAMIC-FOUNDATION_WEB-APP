# Phase 4 timetable implementation

Launch reconciliation update: see `FINAL_LAUNCH_COMPLETION.md`. The operator reconfirmed the source documents and December 31 workshop/activity, and approved the final evening label **Final Night**. The dataset remains 188 entries. Import now requires exact reviewed seed SHA-256; publication has a separate preview/write command. No import/publication was executed. Historical validation below describes the original Phase 4 run.

Implemented exactly two edition-wide timetables: Daily Activities and Food Timetable. A single additive `TimetableEntry` model stores both types, dates, source labels, optional time bounds, day numbers, descriptions, certainty, location/instructions, ordering, draft/publication state and responsible staff timestamps. No class, house or personal timetable model was added.

## Source data

The authoritative files were located at `C:\Users\hp\Downloads\Telegram Desktop\DIC_2026__Timetable.pdf` and `C:\Users\hp\Downloads\Telegram Desktop\Uodated food time table for 2026.docx`. Their SHA-256 hashes are recorded in `data/dic2026_timetables.json`. PDF text was decoded using its embedded Unicode font maps and cell coordinates; DOCX table text was read directly from OOXML. Intermediate source extraction evidence is under `output/phase4/` at the repository root.

The seed has **188 draft entries: 158 activities and 30 meal periods**, covering 23 December 2026 through 1 January 2027. Adjacent equal activity cells were merged. Arrival retains the stated 4:30 PM start and its source slot label. Unbounded periods retain source labels; no overnight end, prayer times or meal-serving times were invented. “No scheduled activities” remains a source period, rather than a new event. Food spelling, whitespace, blank descriptions and meal headings are preserved; the source's “Last day” maps to 1 January, the tenth camp date. Blank food descriptions remain blank in storage and are explained in the interface.

Day 6 has Health Forum / Health Symposium at 11:00–13:00 and Sports Activities at 17:00–18:30, both marked confirmed. Superseded entries are absent. Other source entries retain unspecified certainty unless the source explicitly identifies otherwise; document approval is separately represented by draft status. Final Night Programme has no invented details or ending time.

`import_dic2026_timetables --edition <id>` previews the source without querying the database. Import requires a separately approved operator to supply `--apply --database-name <exact-name> --approved-by <username>`. The operator must have `dic.manage_dic_timetables`; the edition year and exact dates are checked. The command locks the edition and uses one atomic transaction. Stable source keys preserve existing rows; a durable audit receipt makes subsequent runs no-ops, including after staff delete entries. It never updates existing entries or publishes them. This command has **not been executed against any database**.

## Administration and security

Grant permissions deliberately to named users/groups; no existing staff group is automatically changed:

- `dic.view_timetableentry`: view timetable entries and full-day staff previews.
- `dic.manage_dic_timetables`: create, edit, reorder through `display_order`, and delete drafts.
- `dic.publish_dic_timetables`: deliberate publish/unpublish actions; does not grant draft editing.

In Django Admin, filter by edition, type, date and status. Preview links show the complete day, including draft labels. Select entries and use the publish/unpublish day action: all entries on those days are included. To publish a complete timetable, filter to one edition and type, select all matching entries, then publish. Mixed editions/types are rejected. Unpublish a day before editing it. Edition/date/type cannot be changed on an existing row. Bounded overlaps, reversed ranges, out-of-edition dates and incorrect day numbering are rejected. Publication and draft deletion lock the edition. Changes, deletion, imports and publication create audit records; Django Admin additionally records its normal change history.

`GET /api/v1/dic/participant/timetables/?item_id=<booking-item>&type=activities|food&date=YYYY-MM-DD` reuses existing participant/guardian grant and eligibility rules. Edition identity comes from the authorized booking item, never a client edition parameter. Queries select published entries only; unpublished and absent dates share one generic state. Missing schema returns a controlled setup-pending response. Existing portal CSRF, throttling and no-store headers remain in force.

The portal Timetables destination offers both types, a complete camp date selector, previous/next navigation, Africa/Lagos today/current/upcoming information, refresh, mobile layout and day printing. Known bounded activities can be current; exact starts permit upcoming labels. Unknown meal times and open-ended activity ends are not guessed. Information refreshes every minute. Before camp the next published date is selected; after camp the last published date remains browsable, subject to existing eligibility.

Operations navigation links to a permission-protected, read-only status screen and Django Admin. `GET /api/v1/dic/operations/timetables/` returns edition choices and per-day publication counts to authorized staff. It does not create a second editor.

## Migration and release

Additive migration: `dic.0032_phase4_timetables`, depending on `dic.0031_phase5_feedback_welfare` and the swappable user model. Existing ordering, including the postponed welfare dependency controls, is unchanged. The existing `release_migrations` command calculates all leaf nodes and hashes every migration source, so the new migration is automatically included in a freshly generated exact release manifest. Previous approval manifests must not be reused. No unrestricted migration command or startup migration hook was introduced.

**No migrations, database seeds, permission grants, deployment, registration enablement or live payment activation were performed.** Demo, development and production data were not modified.

## Files

New backend files: `timetable_models.py`, `timetable_services.py`, `timetable_api.py`, `timetable_admin.py`, `test_timetables.py`, `migrations/0032_phase4_timetables.py`, `management/commands/import_dic2026_timetables.py`, `data/dic2026_timetables.json`, and this handover. Existing `models.py`, `admin.py`, `urls.py` and `operations_api.py` receive model/admin registration, routes and the explicit navigation permission flag.

New frontend files: `src/components/dic/CamperTimetables.jsx`, `Timetables.css`, `src/pages/TimetableOperations.jsx`, `src/services/timetables.js` and `timetables.test.js`. Existing `CamperExperience.jsx`, `PortalPhase3.jsx`, `Operations.jsx`, `operationsNavigation.js` and `operationsRefinement.test.js` integrate the views and permission checks. The repository already contained extensive uncommitted changes; this list describes Phase 4 additions only.

Validation files: `scripts/validate_dic_phase4.ps1` and `scripts/validate_dic_phase4_policy.py`.

## Validation and blockers

- **PASS:** frontend suite, 217 tests; frontend lint; production build. Final consolidated frontend log: `output/phase4/validation.log`.
- **NOT RUN:** Django system checks, the new database-free timetable policy tests, model/migration parity, migration graph and relevant Phase 3/5/6/7 backend regressions. The configured Python virtual environment could not start: access to its Python 3.13 interpreter was denied. No retry or alternate Python execution was attempted.
- **NOT RUN:** database-writing acceptance tests, migration application and seed execution; separate authorization is required.
- **FAIL:** none in the final executed frontend cycle. Vite retains a non-fatal bundle-size warning.

The backend policy runner reuses existing isolation guards to prohibit database connections, enables fast test-only password hashing, checks Django and the migration graph/model parity, and runs timetable plus Phase 3/5/6/7 policy regressions in one process. Timetable tests cover source integrity/amendments, draft import and receipt idempotency, permissions, publication scope, validation, guardian scope, published-only reads, escaped staff previews and Lagos date selection. These are policy tests with mocked storage, not evidence that live database transactions have been exercised.

Release blockers: restore local Python execution and pass the backend validation; separately review and authorize the exact migration manifest; authorize an import into the intended edition; explicitly grant staff permissions; review draft schedules and publish deliberately. Database-backed acceptance and browser/mobile/print visual review remain unperformed.

Next command, from the repository root (safe checks only):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_phase4.ps1
```
