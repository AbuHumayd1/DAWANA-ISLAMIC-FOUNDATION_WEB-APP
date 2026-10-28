# DIC 2026 Camper Portal CP-3 implementation

Prepared 25 October 2026 against the user-supplied approved CP-3C.1 catalogue.
Code is implemented; schema is not applied and launch acceptance is incomplete.
No application records, accounts, permissions or existing migration files were changed.

## Implemented

- Fixed catalogue: 38 individual and 17 collective activities, exact approved points,
  thresholds, prayer/Rawātib periods and recurrence. HSP07 is Class and Camp Lectures
  Attendance; Islamic Reading Challenge is not a collective activity.
- One supporting ActivityAward table, linked one-to-one to the existing original
  HouseScoreTransaction. House totals still read only that ledger.
- Existing Staff Operations scoring page: activity selection, eligible camper/house,
  date/period/approved reference, verification evidence, participation/exemptions,
  official inspection/competition marks and fixed points. Direct house adjustments remain.
- Trusted verified-paid eligibility, physical check-in and current valid house assignment
  rechecked at submission. Scoring does not issue IDs or create enrollments/check-ins.
- Atomic ledger/award/audit writes; edition lock serializes caps, duplicate claims,
  corrections and house transfers. Relevant source orders are locked in PK order before
  participants/enrollment source-review rows. No external calls occur inside posting.
- Per-edition request UUID and actor/payload fingerprint; unique business claims also
  prevent replay with another UUID. Shared task/incident references prevent cross-code
  duplication. Officers must consistently reuse agreed identifiers for the same event.
- Separate 10-point ordinary service/character caps, punctuality exclusions and
  once-per-edition milestones verified from underlying unreversed achievements.
- Collective exact-fraction thresholds, frozen eligibility/exemption/attendee evidence,
  four-of-five prayer target, winning/tied inspection and competition results.
- Existing supervised audited reversal offsets personal and original-house totals.
  Reverse dependent milestones/prayer bonuses first to avoid invalid evidence.
- Booking-scoped portal personal total/history, current-house individual ranking and
  overall standings. Individual ranking uses first name/last initial without contact,
  booking, payment evidence, staff notes or other-house individual records.
- Camper switches unmount/cancel scoring requests. New panels use normal document
  flow and wrapping grids/lists, with no fixed-height or nested scoring scroll area.

## Operational details

Award date is the Africa/Lagos camp-local activity date; future/out-of-camp dates and
activity dates before physical check-in are rejected. Credited house is determined at
posting time, including backdated achievements. Transfers never move earlier ledger rows.
Nightly activities use their recorded camp-local activity date.

Approved task, incident, memorisation, lesson and competition identifiers use lowercase
letters/digits/hyphens/underscores, maximum 80 characters. Identifiers for targets and
sessions are unique throughout an edition. No new scheduling or target-management UI exists.
MIL05 references the verified QUR05 completion of the approved reading target.

Only staff with existing record permission can post. Existing correction permission is
also required to document/approve participation exemptions. Inspections require marks
for every active participant house; competitions require the verified official results
for participating houses. Each tied winner is recorded separately using identical results.

Reversed claims remain reserved, including their original cap usage: reversing does not
automatically permit re-earning the same milestone/task/prayer. Original rows are retained.
No replacement/reopening workflow has been invented. Direct house adjustments remain
available for other agreed reasons, without creating personal points; reserved catalogue
codes/names must use the verified activity endpoint.

Current-house rankings show current members' contributions credited to that house.
Personal totals can include contributions previously credited to another house.
Before schema application the portal displays setup-pending, not invented zero personal
points, and can still show existing overall standings if the ledger table exists.

## Files

Created:

- backend/dic_scoring/__init__.py, apps.py, models.py, tests.py
- backend/dic_scoring/migrations/__init__.py, 0001_activity_award.py
- backend/dic/scoring_catalogue.py, activity_scoring.py, activity_scoring_api.py
- backend/dic/test_activity_scoring.py
- dawana-platform/src/components/operations/ActivityAwardForm.jsx
- dawana-platform/src/components/dic/CamperScores.jsx
- dawana-platform/src/services/activityScoring.js, activityScoring.test.js
- This implementation handover

Modified in this task (other pre-existing workspace changes were preserved):

- backend/config/settings/base.py
- backend/dic/scoring_services.py, urls.py
- dawana-platform/src/pages/HouseScoring.jsx, Operations.css, ParticipantPortal.css
- dawana-platform/src/components/dic/CamperDashboard.jsx
- dawana-platform/src/services/camperDashboard.test.js

Registration, payment, OTP, check-in, allocation and Digital ID services were not modified.

## Endpoints

- GET/POST /api/v1/dic/operations/scoring/activities/?edition=<id>
  Existing Operations session, CSRF and record/view permissions. GET supplies the fixed
  catalogue and eligible directory. POST accepts activity/date/slot, camper OR house,
  verification, note, UUID, and relevant attendees/exemptions/results/reading target.
  Client point values and undocumented fields are rejected.
- GET /api/v1/dic/participant/scoring/?item=<authorised-registration-item>&page=1
  Existing booking grant; edition and permitted house are derived on the server.
- Existing scoring, direct house-award, history/print and reversal URLs remain.

## Migration safety

Prepared only: dic_scoring.0001_activity_award depends on
dic.0026_house_score_transaction. It does not depend on dic.0027_feedback_welfare.
No migrations were applied, faked, renamed, rewritten or removed. Actual applied state
was not queried. Review the entire prerequisite chain before deployment.

Never use unrestricted migrate while 0027 remains unapproved. Ordinary database-backed
Django tests and the existing validation runner can migrate all pending apps; do not
assume that a focused test label or its graph-inspection target prevents 0027 application.
Integration validation needs separately approved fresh isolated PostgreSQL setup with an
explicit migration target that excludes 0027, and no reuse of application databases.

## Verification and launch steps

Frontend final rerun passed 114 tests (zero failed/skipped), lint and production build,
with the existing >500 kB bundle warning (about 562 kB).
Targeted tracked-file diff whitespace checks passed (line-ending warning only).

Backend database-free test execution was attempted but Python failed before Django:
`did not find executable at 'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.`
No test DB was created. No backend pass or migration/model parity result is claimed.
Prepared: 15 database-free policy/API/service tests and 8 isolated database integration/
concurrency tests. Real locking, constraints, rollback and end-to-end access remain pending.

The computer-use skill initialized, but automatic approval review rejected Chrome access:
`Computer Use was not approved to use Google Chrome`. No desktop/mobile visual acceptance
pass is claimed. A temporary synthetic preview was stopped and removed; it made no API writes.

From a working existing Python environment, safe database-free checks:

```powershell
python -B backend/manage.py test dic.test_activity_scoring.ActivityPolicyTests dic.test_scoring.HouseScoringTests --verbosity 2
python -B backend/manage.py check
python -B backend/manage.py makemigrations --check --dry-run --noinput
python -B backend/manage.py showmigrations dic dic_scoring
python -B backend/manage.py migrate dic_scoring 0001 --plan
```

The last two commands inspect existing migration state/plan only. Confirm that the plan
excludes 0027 and that earlier pending dependencies have separate approval. Obtain a fresh
backup and explicit migration execution approval before applying the targeted schema.
Do not run the integration test module until its isolated schema setup is explicitly approved.

After approved schema validation/application and existing scoring permission assignments,
deploy backend/frontend together. Check real booking scope and existing ID access, two
campers in one booking, expiry/logout, individual/collective posting and reversal, historical
transfer attribution, and standings. Verify desktop/tablet/390px/360px layouts, document
scrolling, hamburger open/close/navigation, keyboard use and pending/denied/error states.
No new login, portal, staff dashboard or house-leader permissions are needed.
