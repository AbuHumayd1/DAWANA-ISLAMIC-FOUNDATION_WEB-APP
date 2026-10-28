# Final release acceptance and controlled launch procedure

**BLOCKED — APPROVAL / ACCEPTANCE REQUIRED**

## Evidence and status register

| Requirement | Status | Evidence / remaining action |
|---|---|---|
| Phases 5–7 local consolidated validation | PASS (user-reported) | User confirmed successful local validation; not independently rerun here. |
| Last executed frontend regression | PASS | Retained Phase 7 run: 214 tests, lint and build; bundle-size advisory. No frontend changes in this final preparation. |
| Final release script syntax | PASS | PowerShell parser checked during preparation. |
| Final release Python suite and source-graph receipt | NOT RUN | Known Python interpreter access restriction. No repeated execution attempts. |
| Source migration dependency review | PASS | Inspected dependencies and run_before: 0026 → 0028 → 0029 → 0030 → 0027 → 0031. |
| Actual applied/pending migrations | NOT RUN / UNVERIFIED | No database connected. Do not infer pending state from filenames or source graph. |
| Production manifest approval/application | APPROVAL REQUIRED | Exact target identity, ordered plan, source hashes, backup/restore evidence. |
| Demo schema/application and acceptance writes | APPROVAL REQUIRED | Only dic_2026_demo; separate explicit schema/write authorization. |
| Current backend/DB/Paystack/email isolation | NOT RUN / UNVERIFIED | Must establish before any acceptance writes. Never rely on .env defaults. |
| Browser registration-to-portal acceptance | NOT RUN | Previous Phase 3 automated run failed at account_activation, with verified rollback. No successful replacement run claimed. |
| Actual staff assignments and inherited grants | NOT RUN | Source allowlists reviewed; no account/grant reads or changes. |
| Staff edition restrictions | FAIL | Existing staff grants are global, not edition assignments; request edition scoping is not staff-to-edition authorization. Approve global committee access explicitly or implement reviewed assignment policy before restricted use. |
| Controlled migration hook source | PASS | No unrestricted migrate/createcachetable in render-migrate.sh; pending plan stops deployment. Runtime checks NOT RUN. |
| Production build/start path | FAIL | Current Render scripts explicitly allow staging only; cannot be used unchanged for a production-settings launch. No hosting changes authorized here. |
| Actual HTTPS/proxy/hosts/origins/DB TLS/cache/static/email | NOT RUN | Source controls exist; deployed values and behavior not verified. |
| Live Paystack | APPROVAL REQUIRED | Intentionally unsupported/blocked; cannot launch paid registration merely by replacing a key. |
| Dedicated payment receipt and real refund-state acceptance | NOT RUN | Booking/payment confirmation exists; no bank receipt or real provider refund acceptance inferred. |
| Production deployment/public registration | APPROVAL REQUIRED | Neither authorized nor activated. |

## Completed implementation and final corrections

Reuse existing Finance, settlement, registration/accounts, ID/movement/housing,
Phase 5 feedback/welfare and Phase 6 reporting. No timetables implemented.

Final preparation adds `scripts/validate_dic_release.ps1` and
`scripts/validate_dic_release_policy.py`. The latter runs the existing safe suites
and generates a uniquely named complete **source-only** graph receipt; it never
connects, creates databases or applies migrations. `--manifest-file` now exports
an exact database-specific migration JSON without scraping mixed console output;
exclusive creation protects existing receipts. Manifest steps now include
`run_before`, and approval validation safely rejects non-object JSON. Tests added
to the existing release policy suite. No business behavior or secrets changed.

## Migration plan and compatibility

Verified source ordering, after prerequisites through dic.0026:

1. `0028_registration_privacy_measurements`: privacy/age declaration and optional
   measurement state/constraints. Existing-data compatibility must be reviewed.
2. `0029_authorized_tutor_registration`: tutor authorization/verification and
   registration-basis schema. Preserve complimentary authorization separately from payments.
3. `0030_portal_account_authentication`: account/booking/session/Google-link/OAuth
   attempt storage. Does not approve public activation or email ownership for users.
4. `0027_feedback_welfare`: six feedback/welfare models, explicit permissions and
   uniqueness/check constraints. Does not grant user permissions or seed responses.
5. `0031_phase5_feedback_welfare`: versions (existing responses become v1, new
   responses v2), nullable affected participant for legacy complaints, urgency,
   contact preference and constraints. Legacy affected-child identity is not guessed.

Finance and Movement app initial migrations depend on dic.0026; other project/app
migrations must be included in the actual database plan. No exact pending list is
available until read-only inspection runs. The source receipt includes the entire
graph, not just these DIC nodes, and **is not a migration approval artifact**.

Data risks: historical three-point reports must stay separate from v2; legacy
complaints without affected participants stay unavailable to camper history;
missing privacy key prevents feedback; new permissions do not confer staff access;
missing cache tables break throttles even when migration history is complete.
Rehearse constraints, locks/runtime, retained evidence and restore compatibility
against an approved restored copy before release. Never edit historical migrations.

### Read-only commands — no application

From the repository root:

```powershell
# One final database-free regression (normal next action).
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_release.ps1

# Approved isolated target only: identity/history/schema preflight, no writes.
.\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_demo.py preflight --database dic_2026_demo

# Preview staff allowlists only; does not query or change groups.
.\backend\.venv\Scripts\python.exe -B backend\manage.py setup_dic_staff_roles
```

Release database inspection is a separately configured environment: provision
secrets via the host/secret store, not edits to the shared backend/.env. With an
approved exact release database name in `$env:RELEASE_DATABASE_NAME` and the intended
settings already configured:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py release_migrations --database-name $env:RELEASE_DATABASE_NAME --manifest-file .\output\acceptance\release-pending-plan.json
```

Pending migrations intentionally return nonzero **after writing** the reviewed
manifest. Use a new filename on another inspection; never overwrite evidence.
The command refuses dawana_dev, dic_2026_demo and PostgreSQL system databases;
requested/configured/current_database identities must agree. No production
connection was attempted here. An operator must verify the approved host/service
identity as well as its database name; matching names alone do not prove isolation.

### Backup, approval and recovery — do not execute without authorization

Use secret-managed libpq service definitions. Confirm the named backup service
resolves to the exact approved host/database. Never print connection URLs/passwords.
An example exact operator command, once the service is approved:

```powershell
pg_dump --dbname="service=dic_release_backup" --format=custom --file .\output\acceptance\dic-release-before.dump --no-owner --no-acl
if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
pg_restore --list .\output\acceptance\dic-release-before.dump
Get-FileHash .\output\acceptance\dic-release-before.dump -Algorithm SHA256
```

Restrict/encrypt backups: they contain children’s personal and confidential data.
Listing an archive is not a restore test. With separately approved **new disposable
restore target** (never dawana_dev, demo or existing production) and no --clean:

```powershell
pg_restore --dbname="service=dic_release_restore_drill" --exit-on-error --no-owner --no-acl .\output\acceptance\dic-release-before.dump
```

Record restored schema/count/eligibility checks and the backup hash. Approver signs
off scope/time/backup/restore and traffic freeze. Construct approval JSON with the
exact exported object under `manifest` and nonempty `approved_by`, `approved_at`,
`backup_reference`, `restore_procedure`, `rollback_decision`. This is an
access-controlled operator artifact, not a cryptographic signature. No approval
file was generated or preapproved by this preparation.

Only after explicit approval:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py release_migrations --database-name $env:RELEASE_DATABASE_NAME --apply-approved-plan --approval-file .\output\acceptance\release-approval.json
```

Reinspect for an empty pending plan; verify 0030/0027/0031 columns, constraints,
content types/permissions, retained order/payment counts, v1/v2 reporting,
complaint privacy and eligibility before traffic. Cache-table creation is a
separate approved operation after exact identity verification; no startup
automation creates it. Test throttling and static manifests afterward.

Rollback: stop traffic and workers; preserve failed-plan evidence; assess writes
since backup; restore to a separately approved recovery database and verify before
switching traffic. Do not blindly reverse data migrations or run pg_restore --clean
against the live database. Application rollback alone requires schema compatibility.
Host/database switching and production restore each require explicit approval.

## Isolated acceptance controls and commands

No database-writing acceptance action is authorized by this document. Do not
silently change active servers or .env. Close unrelated processes, verify process
settings/host/port and all three database identities. Ensure test keys, localhost
callback, synthetic .test addresses, intercepted mail and mocked provider boundaries.
Refuse unknown external destinations or production callback/email delivery.

For **separately approved Phase 5 schema** on demo only:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_demo.py migrate --database dic_2026_demo --confirm-demo-writes --approve-phase5-schema
.\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_demo.py integration --database dic_2026_demo --confirm-demo-writes
```

The runner establishes explicit demo settings before Django imports, checks target
identity, requires existing 0030 and permits only 0027/0031 pending; it blocks
provider/network side effects. Integration runs synthetic TestCases inside rollback
transactions without DiscoverRunner database creation/flush/destruction and writes
an outcome receipt. Do not use it as a production migration mechanism.

The older Phase 3 runner intentionally rejects applied 0027. **Do not rerun it
after Phase 5 schema and do not bypass that guard.** Use the manual controlled
acceptance below on the current approved schema, with a reviewed synthetic fixture
list, test-mail interception and isolated mock payment adapter supplied by a
separately approved harness/session. There is no approved automatic combined
browser fixture harness for post-Phase-5 schema; this remains an acceptance gate.

### One manual browser checklist

1. Record approved demo identity, schema, frontend/backend origin, synthetic fixture
   IDs, payment mock/test mode and intercepted delivery configuration. If any
   isolation condition is unverified, stop before submission.
2. At `/dic/register`, register one synthetic camper with primary contact and strong
   password/confirmation. Verify backend price and total. Confirm registration alone
   and email verification alone cannot unlock protected portal requests.
3. Complete approved Paystack test checkout or isolated mocked verification. Confirm
   backend evidence, amount/currency/reference/domain and whole-order settlement;
   inspect `/dic/register/payment-return`. Never infer verification from the URL.
4. Use the captured synthetic email link, `/dic/participant#verify-email=...`; click
   Confirm email ownership, then email/password Sign In. Do not retain link tokens,
   passwords or OTPs in evidence. Record only sanitized endpoints/statuses/results.
5. Repeat a guardian multi-child order and separate eligible order; verify exact
   totals and legitimate linked-child selection. Attempt unrelated/unpaid child IDs
   directly: deny server-side. One paid order cannot authorize a separate unpaid one.
6. Verify pending, failed, unverified, refunded and cancelled synthetic bookings
   are denied. Change eligibility through the approved synthetic fixture harness;
   existing sessions must lose protected access. No production payment/refund calls.
7. Verify QR access only after authorized ID issuance; tutor exception remains valid
   without fake settlement, with no housing/competition privileges. No public tutor claim.
8. Logout and cross-tab expiry: protected APIs deny access, account recovery still
   requires ownership, and failed passwords do not link another booking.
9. Check Phase 5 duplicate/date/tutor applicability, complaint child isolation and
   hidden internal notes; report exports preserve version/privacy rules. Verify
   mobile focus, labels, loading/error states and normal scrolling.
10. Record PASS/FAIL per scenario. Roll back approved synthetic data where possible;
    otherwise retain exact fixture IDs and seek approved targeted cleanup. Never
    reset databases or delete pre-existing records/evidence.

## Staff permission review matrix

All require active staff + `dic.can_view_dic_operations`. No grants executed.

| Function | Additional rights | Boundary / decision |
|---|---|---|
| Administrator baseline | view edition/category | No finance, child identities or welfare by default. Existing inherited broad grants need review. |
| Registration | view registration order/item and participant | Contact viewing/export requires independent contact permissions. |
| Finance | `can_view_dic_finance`; dic_finance view_details/export/action permissions | Approval and confirm_payment distinct; creator cannot approve own entry. No welfare implication. |
| Accommodation | view house/allocation; explicit allocation/reassign/release rights as needed | Tutor exclusion and capacity constraints remain enforced. |
| QR/movement | view IDs, check-in; dic_movement view/record/authorize_departure as needed | QR tokens and release details never belong in general reports. |
| Welfare | view welfare; manage welfare separately | Notes/history identified/confidential; camper projection excludes internal notes. |
| Reporting | export reports + per-domain permissions | General summary permission does not authorize Finance/welfare/individual records. |

Actual account memberships, user permissions, superusers and inherited groups are
UNVERIFIED. Staff grants are global: edition filters scope queries but do not
restrict an officer to assigned editions. No assignment model exists. Do not
claim edition-specific staff authorization. This requires explicit scope approval
or implementation before any role that must be edition-restricted is enabled.

Only after grant approval, `setup_dic_staff_roles --apply-reviewed-grants` applies
the three existing additive allowlists; it does not revoke legacy broad grants or
create all specialist roles above. Review actual memberships and assign specialist
rights individually through an approved administrative session; never blanket grants.

## Hosting and secrets findings

Source: DEBUG false; HTTPS/secure cookies/HSTS; exact host/origin checks; TLS PostgreSQL;
shared cache requirement; redacted request logging; production strong hashers.
Actual environment values are UNVERIFIED; backend/.env was not printed/read here.
Required names are listed in PHASE7_RELEASE_HANDOVER.md (no secret values).

Frontend: `npm.cmd ci` then `npm.cmd run build`, output `dawana-platform/dist`.
Configure API proxy before SPA fallback; prefer same-origin `/api/v1`; no secrets
in VITE_* variables. Render staging scripts use constraints-staging.txt,
`manage.py check --deploy --fail-level WARNING`, collectstatic and Gunicorn. They
refuse production settings; approve/finalize production start/build and trusted
proxy handling before deployment. Source preparation did not alter hosting settings.

Health is `/api/v1/health/`, a read-only SELECT 1; it does not establish schema/cache/
static readiness. Retain controlled migration-plan inspection and cache/static checks.
Email SMTP transport, verification/recovery delivery, queue/worker health, webhook
HTTPS URL and callback routing need acceptance. The actual webhook route is
`/api/v1/dic/payments/paystack/webhook/`; frontend payment return is
`/dic/register/payment-return`, and its backend status API is
`/api/v1/dic/payments/return/`. Use the approved host and do not enable live keys.
Paystack client and settlement still reject live mode: live paid launch remains a
separate code/activation approval. Test keys alone are not a public payment launch.

No known exposure is established, so no credential rotation is asserted necessary.
Any exposed/reused Google app password, DB password, Django secret or Paystack key
requires explicit secret-manager rotation approval; never rotate the feedback
privacy key casually because it protects historical duplicate receipts.

## Single next action

### Step B preparation update

The DIC 2026 demo baseline now has a preserved read-only receipt with 44 applied
and 11 pending migrations, including `dic.0032_phase4_timetables`:
`output/acceptance/migration-verification-2c9499d80e584c1ca72fc04efe0d68b9.json`.
All implementation phases are complete; the user reports Phase 4 validation passed
(231 backend tests, 217 frontend tests, lint and build). These prior results are
not a new test run performed during backup readiness preparation.

Follow [Step B backup and restore readiness](../../scripts/DIC_2026_STEP_B_BACKUP_READINESS.md)
for the current safe commands, prerequisites, evidence and approval boundaries.
The new readiness workflow has no backup/restore execution mode. Its default is
offline preflight; a fixed read-only source check and offline archive reads are
explicit options. No schema/data/history or existing migration verifier was changed.
Step B is incomplete until authorized backup and disposable restore evidence exists.
The earlier next-action wording below remains historical release guidance, not
authorization to run migrations or database-writing acceptance.

Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_release.ps1`
locally to validate final artifact corrections and generate the source graph receipt.
Then approve **read-only demo preflight and reviewed post-Phase-5 synthetic
acceptance preparation**, followed separately by any schema/test writes. Production
plan, migration, grants, hosting changes, live activation and deployment each stay
behind their explicit gates. No launch command is authorized by this document.
