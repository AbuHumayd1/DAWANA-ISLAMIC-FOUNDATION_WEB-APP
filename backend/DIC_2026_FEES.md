# Approved DIC 2026 fees

## First production release — current policy

Production starts with a new, empty database. No local/demo database, participant
data or portraits are transferred. Do not run the historical local PostgreSQL
procedures below or the portrait cutover helpers during initial production setup.
Only the fresh production target and its approved schema/reference data belong to
the initialization plan. No demo or staging environment is required or authorized.

The owner must supply registration opening/closing dates and the timezone-aware
Early Bird cutoff. No deadline is invented. Registration remains draft/closed
until production acceptance and explicit owner approval. Live DIC payments require
their own verification and activation approval; Foundation donations remain disabled
and deferred. Email verification/password sign-in is approved; Google is not enabled.
Ordinary participants require independently verified live payment in production;
explicitly authorized complimentary tutors retain the no-payment exemption.

Implemented on the approved `staging/dawana-e2e` branch. No database was connected,
no deployment was performed, and `.env` was not read or changed for this work.

`dic.0034_approved_2026_fees` adds an explicit payment classification to
`RegistrationCategory` and seeds these NGN Early Bird / regular amounts:
Pre-Primary 4,000 / 5,000; Primary 10,000 / 12,000; Secondary 12,000 / 15,000;
Undergraduates 15,000 / 17,000; Graduates & Adults 18,000 / 18,500.

The one-time migration creates missing categories and fills null fee fields on
categories with the exact approved names. Existing non-null fees (including
zero), active flags, edition configuration and deadlines are preserved. Only
payment age bounds/classification on these five named categories are standardised.
Other categories are untouched. Existing order items, price revisions, camper
records and payment attempts are never updated by this migration. Reverse data
migration is a no-op to avoid deleting administrator edits or referenced records.
There is no startup price reset or fee import step.

If no 2026 edition exists, 0034 creates a draft, inactive edition. Its historical
name/venue defaults are corrected forward by 0035 to Darul Islam Camp 2026,
Fazil Umar Secondary School, Lagos, with theme The Outliers. Dates remain
23 December 2026–1 January 2027. Neither migration opens registration, sets
registration dates or chooses an Early Bird deadline. Do not rewrite 0034.

Payment eligibility uses age on the registration date, as before. Undergraduates
requires tertiary-student status and age 17–24; its public card omits the age
ceiling. Graduates of any age, non-undergraduates aged 17–24, and everyone
aged 25+ qualify for Graduates & Adults. An adult withholding DOB can use that
category if not a tertiary student; a tertiary student must disclose DOB to
establish the applicable age band. Younger graduates retain the graduate fee.
These rules do not modify housing, guardian, safeguarding, class or house policy.
A 17-year-old qualifying for the adult payment category remains a minor under
the existing age-declaration and safeguarding rules.
Legacy categories without a payment classification retain their existing rules.

## Production configuration

- Include 0034 and all pending dependencies in the existing controlled production
  migration manifest/backup process. Do not run it against protected demo databases.
- In Django Admin, review the 2026 edition and its Registration categories.
  Configure the approved timezone-aware `early_bird_cutoff_at` if absent. Existing
  validation keeps pricing unavailable while discounted fees lack a cutoff.
- Review any additional active categories or differently named legacy categories;
  this migration deliberately does not merge, delete or deactivate them. Review
  preserved fee overrides, especially zero fees or a regular override below the
  seeded discount, which existing validation will reject.
- Confirm existing registration dates, active edition and registration status
  before opening. Fees and cutoff remain editable through existing Admin permissions.
- Payment verification, amount/currency/reference checks, webhook signatures,
  idempotency and grouped checkout remain required. Live DIC capability is present
  behind explicit configuration and acceptance gates; no payments are activated by
  this fee work. Entitlement also requires stored mode to match runtime mode, and
  production paid access requires live evidence. A test payment cannot become live
  entitlement by switching configuration. Donation functionality remains deferred.

## Historical validation tooling — excluded from first production initialization

The following local/disposable-database procedures are retained historical
technical information only. Do not execute them for this release. They do not
authorize local database troubleshooting, creation, migration, cleanup, demo-data
transfer or a staging environment. Their old results are not current production
acceptance. Only database-free checks are authorized in correction pass 4.

SQLite cannot run the existing PL/pgSQL `CREATE FUNCTION` statements in
`dic.0014_participant_portal_and_ids` (first at line 108) or the triggers in
`dic.0015_guard_registered_category_edition`. The earlier SQLite runner was an
infrastructure defect. No historical migration or pricing changes are needed.

The runner now delegates to `scripts/dic_fee_postgres.py`. Its `plan` action
connects only to the local `postgres` maintenance database, read-only, and records
the server system identifier, address/port/version, role, maintenance OID and
baseline database OIDs. It requires the operator's explicit port and role; it
never reads `.env` or application credentials. Passwords are prompted and never
stored. Permission to read `pg_control_system()` and CREATEDB are prerequisites;
the tool stops if unavailable and never grants privileges or changes the server.

`run --approve-create` revalidates this identity, rejects an existing generated
name, creates a new database from template0, and records its new OID, owner and
unique comment marker in an exclusive creation receipt. OID 25041 and every OID
present at preflight are forbidden test targets. Every Django connection must
match the disposable name/OID/owner/marker/cluster identity. The runner refuses
non-empty databases, checks migration parity and applies unmodified migrations
only to this new database. It validates the migrated fee seed, then clears only
the disposable fixture for the existing registration/payment tests. Django's
own database creation, cloning and automatic deletion paths are disabled.

The test suite blocks Python socket connections; libpq connections are restricted
to this exact disposable target. It uses synthetic service settings and mocked
payment evidence, never production credentials. No protected DB is connected or
copied. Failed runs retain the test database for inspection. A receipt-verified
`rerun` can use the same database if its migration set is exact and it has no
retained records other than framework permissions/content types. The suite includes approved fees, existing registration,
payment validation/webhook replay and privacy policy checks; it does not claim
production acceptance or concurrency stress coverage.

Commands from the repository root (same PowerShell session):

```powershell
$dicFeePort = [int](Read-Host 'Confirmed local PostgreSQL TCP port')
$dicFeeRole = Read-Host 'Approved local PostgreSQL role with CREATEDB and pg_control_system read access'
$dicFeePlan = Join-Path (Get-Location).Path ('output\dic-fee-plan-' + [guid]::NewGuid().ToString('N') + '.json')
$dicFeeReceipt = [IO.Path]::ChangeExtension($dicFeePlan, 'receipt.json')
& '.\backend\.venv\Scripts\python.exe' -I -u '.\scripts\test_dic_2026_fees.py' plan --port $dicFeePort --user $dicFeeRole --plan $dicFeePlan
if ($LASTEXITCODE -ne 0) { throw 'Fee-test preflight failed; stop.' }
Get-Content -LiteralPath $dicFeePlan
```

After reviewing the exact server identity and generated database name, explicitly
approve creation/testing by executing:

```powershell
& '.\backend\.venv\Scripts\python.exe' -I -u -X faulthandler '.\scripts\test_dic_2026_fees.py' run --plan $dicFeePlan --receipt $dicFeeReceipt --approve-create
if ($LASTEXITCODE -ne 0) { Write-Warning 'Tests did not pass. Preserve the receipt; no automatic cleanup was performed.' }
```

Separately approve cleanup only after the test process exits:

```powershell
& '.\backend\.venv\Scripts\python.exe' -I -u '.\scripts\test_dic_2026_fees.py' cleanup --receipt $dicFeeReceipt --approve-drop
if ($LASTEXITCODE -ne 0) { throw 'Cleanup refused or failed; do not use a manual broad DROP command.' }
```

To rerun all tests in the existing receipt-matched database without creating a
second database, migrating, flushing or resetting retained fixtures:

```powershell
& '.\backend\.venv\Scripts\python.exe' -I -u -X faulthandler '.\scripts\test_dic_2026_fees.py' rerun --receipt $dicFeeReceipt --approve-test-writes
```

Rerun revalidates cluster/name/OID/owner/marker, excludes protected and baseline
OIDs, refuses active connections, and checks exact migration history plus model
parity and clean application tables before tests start. If those checks fail it
stops rather than repairing, migrating or deleting records. Tests perform their
usual transactional synthetic writes; no cleanup command is invoked.

The mixed-category payment fixture was corrected to include the required
`primary_registrant` and `portal_account` from its existing valid registration
payload. Omitting them caused serializer HTTP 400 before eligibility or pricing.
The test retains the exact 2,080,035-kobo expectation and now asserts both
individual order-item and price-revision fee snapshots. Approved fees and
eligibility logic were not changed for this fixture correction.

Cleanup rechecks cluster identity and exact name/OID/owner/marker, rejects OID
25041 and all baseline OIDs, and refuses active connections. It drops only the
new receipt-matched database, never uses FORCE, terminates no sessions, leaves
roles untouched, and retains the JSON evidence files. A partial creation receipt
is intentionally insufficient for automated cleanup and requires separate review.

These PostgreSQL commands were prepared only, not executed. No database connection,
creation, migration or cleanup was performed during this correction. Backend
results remain unverified. Database-free infrastructure guard tests are provided
in `scripts/test_dic_fee_postgres_safety.py`; they were not executed here.

Frontend command (from `dawana-platform`):
`node --test src/services/categorySelection.test.js src/services/registrationPricing.test.js`
Result: 9 passed, 0 failed. `git diff --check` passed.
