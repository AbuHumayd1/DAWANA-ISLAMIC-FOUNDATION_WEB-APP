# Validation follow-up — DIC refinements

Starting revision: 268ef27197a4acb21b629151d9165b14029a55f5
Branch: staging/dic-page-refinements, existing integration checkout.
Overall: NOT READY for staging deployment; runtime validation remains blocked.

PASS — static checks
- 0021 depends on existing 0020 and the swappable user model. The local DIC
  dependency chain was checked for existing files/cycles back to 0001; the accounts
  user migration exists. Migration definitions and model fields were reviewed.
- No new model/schema change was needed for these follow-up fixes. 0021 and its
  models are unchanged from 268ef27. Django autodetector/SQL validation has NOT run.
- Media.jsx, hosted YouTube video code, registration serializers, pricing,
  payment initialization/verification/webhook and payment-return modules are
  byte-identical to the approved 3520770 integration base.
- Production release ref is unchanged at 424ccf7. Original Desktop files untouched.
- git diff --check passed.

Frontend integration run (Node 22.19.0)
- Complete npm test executed: 51 passed, 3 failed to load due to missing Vite:
  categorySelection.test.js, registrationControls.test.js, showcase.test.js.
  These are dependency/load failures, not observed assertion failures.
- npm run build attempted: blocked because vite executable is unavailable.
- npm ci retried using a writable TEMP cache to avoid the old cache permission
  issue; it failed with npm's "Exit handler never called" error. No package
  manifest/lock changes or dependency-version workarounds were introduced.
- Browser/mobile rendering and actual MP4 seek/proxy behavior remain unverified.
  The full suite was run once; already passing tests were not separately rerun.

Backend/runtime blockers
- py lists a Windows Store Python 3.13 interpreter, but execution returns Access
  denied. Other known interpreter locations are absent/inaccessible. No interpreter
  or system install was changed. Django tests cannot start in this environment.
- ffprobe is not on PATH and DIC_FFPROBE_BINARY is not injected locally. Genuine
  MP4 validation requires a working local ffprobe binary on the backend host.
- No isolated PostgreSQL test target was verified (DB_TEST_NAME is not injected).
  No production/staging DB was opened or modified. Do not use a live DB to work
  around this blocker. A dedicated local PostgreSQL test target is needed for
  migrations, permissions, row-lock and unique-constraint tests.
- Local R2 configuration/credentials are not injected. Mocked storage tests need
  no real R2 credentials; actual staging connectivity is a separate deployment
  check, not something to solve by exposing secrets to this session.

Code fixes from review
- PrivatePromoStorage.open no longer inherits the photo storage 12 MiB read cap.
  It enforces the 100 MiB video limit and spools large reads to a temporary file,
  with bounded chunks and provider/tempfile cleanup. The HTTP streaming route
  remains bounded and does not buffer the full video.
- HEAD ignores Range headers; invalid/empty asset ranges fail safely and range
  numeric syntax is restricted to ASCII bytes syntax.
- Admin flyer publication locks the edition before uniqueness validation so
  simultaneous publication through Admin can report validation errors instead
  of racing directly into a database integrity error.
- New DIC surfaces use the established theme heading variable for readable text
  on existing dark/light panel backgrounds.
- Regression coverage added for >12 MiB reads, oversized-read cleanup, HEAD+Range,
  publication-action permissions, published-flyer withdrawal and DB uniqueness.
  The new backend regression tests remain UNEXECUTED because Python is blocked.

Remaining commands in a working trusted LOCAL development environment
1. Configure a dedicated PostgreSQL test target, synthetic test settings and an
   accessible Python interpreter; install backend requirements. Do not source
   live staging/production credentials. Then:
     python manage.py makemigrations --check --dry-run --settings=config.settings.development
     python manage.py test dic.test_promotions dic.test_memories dic.test_videos dic.test_showcase dic.tests.RegistrationApiTests dic.tests.PaymentApiTests --settings=config.settings.development
   Tests may create/drop only the isolated test database, never a live application
   database. Review the target first. Use no live R2 calls; tests mock the SDK.
2. Install ffprobe and validate one synthetic MP4 locally with no external network.
3. Restore a successful npm ci, then rerun only the three previously blocked test
   files (or full suite if dependency/runtime changes justify integration rerun),
   npm run lint, npm run build, and the staging build with synthetic/site-approved
   build variables. Do not deploy those artifacts automatically.
4. Browser-check 320/375/768px and desktop, flyer focus/Escape/scroll restoration,
   video click/play/seek/HEAD/206/416, no overflow and theme/reduced-motion behavior.

No push, deployment, real R2 operation, migration application or database change
was performed during this validation follow-up. Do not deploy until blocked checks
and the new regression tests pass.
