# Backend acceptance in ephemeral GitHub Actions

## Exact-artifact correction pass (run 42351498137)

The original PG14 and PG18 core ZIPs were read directly without extraction.
Both report 799 discovered/started, 772 passed, 21 failure entries, 9 error
entries and successful fresh migrations. Their failed_ids and error_ids match.
Subtest entries are not a count of distinct failed test methods. The artifacts
do not include exception tracebacks, so no particular exception text is assumed.

Source-confirmed corrections prepared from those identities:

- All 13 named recovery failures share create_order(), whose request omitted
  required primary_registrant and portal_account fields. Supply valid synthetic
  credentials/contact and mock only the independent account-verification mail.
  Recovery matching, delivery, expiry, revocation and concurrent verification
  remain real code under their existing dedicated tests.
- The ten-tester loop reused one primary contact eleven times including setup,
  exceeding its real ten-request limit. Each independent registrant now has a
  distinct synthetic contact. No production limit or cache allowance is changed.
- Finance-only fixtures no longer receive audit permission by default. The
  positive audit case grants it explicitly; the finance-only denial stays intact.
- Projection mocks now cover the real tutor lookup instead of reaching the ORM
  with an invalid synthetic identifier. Campsite mock orders include paid/tutor
  basis and assert the existing complimentary_tutors output field.
- Housing database-constraint coverage first verifies model ValidationError,
  then deliberately uses bulk_create to exercise the independent SQL constraint.
- Portal fixtures supply the existing synthetic housing reference date. Missing
  or revoked IDs retain 400; lost payment entitlement and revoked scopes retain
  403. Foreign bookings retain 404. No authorization implementation is changed.
- Linux font lookup prefers Liberation before the wider DejaVu/Vera fallbacks;
  the PostgreSQL CI jobs explicitly install fonts-liberation. Configured fonts
  and Windows font preferences remain first. Dimensions, complete-name checks,
  QR payloads and the 11 pt minimum remain unchanged. Liberation targets Arial/
  Times New Roman metric compatibility; production Linux must have compatible
  fonts installed or explicitly configure approved font files.
- New result artifacts retain failure/error tracebacks alongside IDs, without
  flooding count summaries. Missing, skipped and failed tests still fail CI.

Local Python execution remains unavailable (Access is denied), including the
registered Windows Store interpreter. Node-based supplementary font-table
measurements establish the fallback-width discrepancy, not PDF-rendering success.
All corrections, including exact long-name bounds and card status expectations,
require fresh policy and PG14/PG18 matrix execution before acceptance. No QR
failure identity appears in these artifacts; no QR code or payload was changed.

## Core remediation status (after bccb858)

The owner reports policy and all tutor/movement/assistance jobs passing on
PostgreSQL 14 and 18; both core jobs still fail. This is reported evidence, not
a locally reproduced result. Full test identities and tracebacks are required
before attributing every failure or the one-failure version difference.

Source-confirmed shared corrections in this pass:

- CI uses the application template override directory and CORS header additions.
  Origins remain restricted; production configuration is unchanged.
- Each PostgreSQL test starts and ends with empty CI caches. The cache location
  is unique to the disposable database. Real throttle rates and within-test
  histories remain active, including concurrent requests within a test.
- Authorized Operations fixtures explicitly request underlying record-view
  permissions; the fixture lookup supports permissions on their actual models.
  Finance/audit grants are explicit and contact access remains separate.
- Role provisioning fixtures opt into reviewed grants; preview-only behavior
  remains unchanged. With owner approval, the historical administrator assertion
  now verifies that registration-access management is withheld. A separate test
  confirms preview mode creates no groups; the role command is unchanged.
- Showcase fixtures explicitly activate the synthetic upcoming edition; public
  publication and inactive-edition restrictions remain unchanged.
- The production-middleware test imports actual declarations in a synthetic
  subprocess with dotenv loading and connection establishment blocked. Production
  secret requirements remain intact; settings imports cannot contaminate CI.
- Operations allocation fixtures now supply the same explicit synthetic housing
  reference date used by the existing allocation fixtures. No production edition
  date or housing policy is changed.
- The housing-worker test checks real CI refusal first, then simulates the
  supported development settings identity only against Django's test database.
  It also verifies wrong-name refusal in that supported context. The command's
  development-only and exact-name safeguards are unchanged.

Remaining investigation requires core tracebacks and a fresh matrix run: other
housing fixtures, portal UUID/card failures,
QR decoding, badge typography, downstream
payment/recovery/concurrency failures, and any independent report-contract errors.
Do not infer those causes from HTTP status or change security policy to satisfy
an outdated expectation. No PostgreSQL-version workaround is justified yet.

The CI-only cache regression exercises a real DRF throttle twice with the same
key: each test gets its full allowance, but excess requests within either test
are rejected. The existing strict counting and nonzero acceptance exit behavior
are retained. Local Python execution may still be blocked by executable access;
unexecuted checks must never be reported as passing.

## Historical preparation notes

The following describes the original preparation, not the current run status.

Prepared configuration, not evidence of a successful run. No workflow has been
committed, pushed or executed by this preparation. No existing local/demo or
production database, credential, account or infrastructure is involved.

## Existing conventions and version requirements

There was no `.github/workflows` configuration. Backend tests use Django
SimpleTestCase/TestCase/TransactionTestCase and DRF equivalents, with unittest
mocks for Paystack, messaging and storage. Existing validation scripts often read
local configuration or require protected local target identities; do not use
those scripts in CI. `scripts/test_production_policies.py` is already database-free
and configures synthetic settings without loading dotenv.

`backend/requirements.txt` pins Django 5.2.18, whose declared Python floor is 3.10
and PostgreSQL floor is 14. The complete acceptance tests have a Python 3.11 floor
because the payment regression fixtures use unittest.TestCase.enterContext.
There is no existing project-wide Python/PostgreSQL runtime pin. Some historical
local scripts demand PostgreSQL 18 for their own identity guard; that is not a
minimum for the application. The prepared workflow uses Python 3.13 and tests both
PostgreSQL 14 and 18. These selections are proposed CI coverage, not verified
production version acceptance. Existing bounded dependencies are not a fully
hashed dependency lock; their allowed resolutions can change between runs.

## Exact commands (repository root, GitHub-hosted job only)

Dependency installation uses existing requirement/constraint files:

```sh
python -m pip install -r backend/requirements-test-ids.txt -c backend/constraints-staging.txt
python -m pip check
```

The policy job runs:

```sh
python -I -B scripts/test_production_policies.py
```

It includes ProductionPaymentPolicyTests and all nine PaymentEntitlementModeTests.
With DAWANA_CI_ACCEPTANCE=1 it requires discovery of the nine regressions and emits
strict JSON counts; ordinary existing local invocation keeps its previous behavior.

Each PostgreSQL matrix job runs one of:

```sh
python -I -B scripts/run_backend_ci.py --partition core
python -I -B scripts/run_backend_ci.py --partition tutor
python -I -B scripts/run_backend_ci.py --partition movement
python -I -B scripts/run_backend_ci.py --partition assistance
```

Before the suites, both jobs parse Python source with no imports or bytecode writes:

```sh
python -I -B scripts/run_backend_ci.py --syntax-check
```

Every job also runs, even after test failure:

```sh
python -I -B scripts/run_backend_ci.py --summarize
```

Do not run PostgreSQL commands locally. They require both GitHub's GITHUB_ACTIONS
marker and DAWANA_CI_ACCEPTANCE=1, a job-local RUNNER_TEMP and the service's mapped
DAWANA_CI_PG_PORT. No developer or production DATABASE_URL is accepted.
DAWANA_CI_REPORT selects the exact expected report: policy or the partition name.
Reruns refuse existing report files instead of overwriting/reusing stale evidence.
The summary also requires DAWANA_CI_TEST_STEP=success, supplied from the actual
GitHub test step outcome; an earlier report cannot turn a failed/skipped step green.

## Coverage and database setup

All backend tests matching Django's `test*.py` convention are discovered across
accounts, config, health, dic, dic_scoring, dic_finance, dic_movement and
dic_assistance. Imported test cases retain normal unittest discovery semantics;
duplicate IDs are counted with multiplicity rather than silently deduplicated.

Database-free examples include production policies, payment-mode regressions,
provider-client/signature mocks, portrait design, release contracts, storage
mocks and CI harness accounting tests. Config subprocess tests import only
synthetic configuration; they neither provision nor connect to a staging service.
Some SimpleTestCase tests explicitly opt into database access, so base-class name
alone is not used to decide database requirements.

PostgreSQL is required for registration/payment settlement, accounts/booking
integration, tutor/privacy integration, allocation/check-in, concurrency,
finance/movement/assistance, and report workflows. The full graph is applied to a
uniquely named empty test database, using Django's normal test database setup:

- `core`: all tests except the three guarded groups below.
- `tutor`: dic.test_tutor_registration and dic.test_registration_privacy.
- `movement`: dic_movement.test_integration.
- `assistance`: dic_assistance.test_integration.

Names preserve existing guard patterns: `test_dic_<partition>_<UTC14>_<hex8>`.
Privacy permits the tutor pattern. No guard in the existing tests is weakened.
Jobs run serially within each partition to preserve threaded race tests; matrix
jobs use independent service containers, so their databases cannot overlap.

SQLite, disabled migrations, historical migration rewrites, faked migrations,
production settings and local/demo fixtures are not used. Django's migration
loader checks graph conflicts and model-state drift before any database setup,
including an explicit ordering assertion for the DIC chain through 0036.
The graph includes 0026 -> 0028 -> 0029 -> 0030 -> 0027 via run_before, then
0031 through 0036, plus accounts and the other installed application migrations.
PostgreSQL must support PL/pgSQL, CREATE FUNCTION/TRIGGER, partial unique/check
constraints and row locking/skip_locked. The ephemeral service role can create
and drop only this service's disposable test databases; it is not a production role.

After applying all migrations, CI validates the official 2026 edition, five fees,
draft/inactive state, absent registration dates/cutoff, four integrity triggers
and their functions from migrations 0014/0015, provider-transaction uniqueness and
the partial unresolved-attempt unique index. Only then it flushes the exact test database so existing
fixtures can create their own 2026 editions. Schema, triggers and migration
history remain; framework content types/permissions are recreated. This is
test-fixture preparation inside an ephemeral container, never a production seed
removal or production initialization procedure. A migration/seed failure stops
the job before fixture flushing or test execution. Ordinary Django teardown drops
the disposable test database; GitHub destroys the service when the job ends.
If database setup fails before Django returns its teardown configuration, the
service may retain partial test state until job completion; it has no persistent
volume and GitHub's service teardown removes that state. No local database cleanup
or production cleanup command is supplied.

## Safety and reporting

The workflow uses pull_request and workflow_dispatch, never pull_request_target,
has contents:read permission, disables persisted checkout credentials, requests no
secrets, no deployment environment and no OIDC write permission. There is no
Render/Cloudflare/Paystack deployment, login, provisioning or activation step.
Dependency downloads and service-image retrieval are the only preparation network
requirements; test code blocks Python outbound sockets and separately validates
libpq connections against the exact localhost port, synthetic role/password and
approved postgres/test database names. This is a trusted-test safety boundary,
not a security sandbox for deliberately malicious pull-request code.

CI settings never import base settings or read dotenv. The runner rejects a
checkout containing root/backend dotenv files without reading their contents.
All keys/passwords are openly synthetic job fixtures. Mail is in-memory; remote
storage and actual recovery delivery are disabled. Google and donations remain
disabled. Tests may override flags to exercise mocked policies, without real
credentials or outbound provider access. ffmpeg/ffprobe and PDF/QR dependencies
are installed on the disposable runner so missing tools are not treated as passes.

JSON artifacts contain discovered/started/passed/failure/error/skip/expected-failure
counts, test IDs and migration evidence. Only addSuccess contributes to passed.
Exact regression method names are read from the source AST and compared with
discovered IDs, so nine unrelated/substituted IDs cannot satisfy the requirement.
Any failure, error, skip, expected failure, unexpected success, unstarted case or
empty suite makes the job fail. Discovery/import/setup failures cannot be hidden
by selecting a partition. Missing reports make the summary/artifact step fail;
they never imply zero failures or a pass. Summary also checks that discovered,
started and successfully completed counts agree. Full failure tracebacks remain in the
job's unittest logs. Artifacts are uploaded with always(), even after failures.

No positive result is currently claimed. First CI execution may reveal model
drift, migration errors, outdated fixtures or runtime defects. Preserve and report
those failures; do not skip tests, loosen guards or disable constraints to get a
green job. Browser, real email, production TLS/IAM and live-provider acceptance
remain separate gates even after automated CI succeeds.

The complete candidate, including previously untracked migrations/helpers and the
nine regressions, must be present in the future approved Git revision. A workflow
cannot see uncommitted local changes. Publishing/triggering it requires a later
owner-authorized action; this preparation does not perform that action.

## Preparation review status

Local static workflow safety/reporting assertions and the count of nine unique
regression definitions passed. `git diff --check` and explicit whitespace checks
covering the untracked CI files are required before delivery. These checks do not
parse YAML or execute Python tests. No local YAML/schema validator was available.
A syntax-only AST check of the five CI Python files was attempted with the existing
project interpreter; it failed before startup with Access is denied. No environment
repair was attempted. Python syntax compilation is therefore also an explicit
workflow step and remains unverified until it runs on the GitHub-hosted Python.
The workflow itself has not been validated by a successful GitHub Actions run.

The seven prepared files are the workflow, this document, synthetic CI settings,
the guarded acceptance/result module, its database-free harness tests, the CI CLI,
and the existing production policy runner. No historical migration, production
setting or application entitlement implementation is changed by CI preparation.
