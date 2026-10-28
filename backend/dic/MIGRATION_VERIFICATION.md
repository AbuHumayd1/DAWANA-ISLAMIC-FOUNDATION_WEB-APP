# Database migration verification — 28 October 2026

## Result

- PASS: configured identity inspected without credentials: DB_* selects
  `dawana_dev`, `127.0.0.1:5432`. No settings-module override found; manage.py
  defaults to development. These are configuration values, not server identity.
- PASS: no database connection, record changes, grants or migration application.
- PASS: retained source graph and migration files agree on DIC ordering:
  `0026 -> 0028 -> 0029 -> 0030 -> 0027 -> 0031`.
- FAIL: Python could not start (base Python 3.13 access denied).
- UNVERIFIED: Django-resolved database, actual PostgreSQL identity, applied and
  pending migrations, all database-specific dependencies and resulting exact plan.
- UNVERIFIED: backup existence/completeness, restore drill, production schema/cache.
- FAIL (current shell): pg_dump and pg_restore are not available on PATH. They
  may be installed elsewhere; their location/version and successful backup/restore
  must be verified locally before migration approval.

The existing source-only graph receipt is not a pending database manifest. No
database-specific manifest was generated; do not approve migrations from assumptions.

## Safe local completion command

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\verify_dic_migrations.py --database dic_2026_demo
```

This new read-only verifier reuses `config.release_migrations.plan_manifest` from
Phase 7. It does not edit .env or silently connect to configured dawana_dev. It
explicitly establishes demo isolation before importing Django, restricts connections
to the configured loopback PostgreSQL port, disables external providers, verifies
requested/configured/current_database identity, and requires PostgreSQL transaction
read-only mode. It checks consistent migration history and graph conflicts, then
records ALL applied migrations and ALL pending leaf-target steps with source hashes,
dependencies and run_before. Only a uniquely named JSON receipt under
output/acceptance is written. There is no apply action or database creation/reset.
Runtime execution of this verifier remains untested here because Python cannot start.

Read-only connection overrides are process-local; no existing database configuration
is changed. Demo results do not establish production state or approve production work.

## Reviewed schema and compatibility

- 0028: optional DOB/measurements, age declaration/evidence fields and checks.
  If pending, inspect existing rows for constraint compatibility before application.
- 0029: tutor authorization/verification and registration basis. Complimentary
  registration remains separate from settlement; no real grants are implied.
- 0030: PortalAccount, booking links, sessions and Google/OAuth storage. Does not
  automatically authorize users or establish verified email ownership/payment.
- 0027: AnonymousCamperResponse, CamperFeedbackReceipt, IdentifiedFeedback,
  LecturerFeedbackAccess, WelfareReport and WelfareEvent; explicit permissions,
  foreign keys and duplicate/integrity constraints. No programme/response seeding.
- 0031: existing responses get questionnaire v1, future responses default v2;
  nullable affected participant preserves ambiguous legacy complaints without
  guessing a child; urgency/contact preference and checks are added.

0028/0029/0030 explicitly precede 0027 using run_before despite numbering. 0031
depends on 0027. Finance/Movement initial schemas separately depend on 0026.
Other apps' pending migrations cannot be determined without the actual history.
No existing registration/payment/finance/housing/portal records are intentionally
deleted or reset by these reviewed Phase 5 changes. Permissions/content types may
be initialized, but grants to users are not automatic. New tables/columns and checks
still require lock/runtime rehearsal; source compatibility is not data acceptance.

## Backup, recovery and production differences

The executable backup/restore procedure and approval fields are in
FINAL_RELEASE_ACCEPTANCE.md. Readiness is **not certified**: require a successful
custom-format pg_dump, checksum, encrypted/access-controlled storage and a verified
restore into a separately approved new disposable target. Archive listing alone
is not a restore test. Never use --clean or reset the existing databases.

Production may have a different migration history, app branches, data volume,
constraints and PostgreSQL role privileges. Its manifest must be independently
generated using production settings and explicit database identity. Shared cache
tables are not tracked by normal migrations and require separate readiness checks.
Production TLS/proxy/start settings and backup services remain separate launch gates.

After approved migration: recheck no pending steps; verify 0030/0027/0031 columns,
foreign keys/uniqueness/checks, versions and retained record counts; verify registration
and trusted-payment eligibility, tutor exclusions, reporting and complaint privacy.
If validation fails, hold traffic, preserve receipts, reconcile writes since backup
and use reviewed restore/forward repair. Do not automatically reverse data migrations.

## Approval-gated commands — prepared, NOT executed

For demo only, after the read-only receipt is reviewed and explicit schema approval:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\validate_dic_phase5_demo.py migrate --database dic_2026_demo --confirm-demo-writes --approve-phase5-schema
```

This refuses unexpected dependencies and permits only 0027/0031 after existing
0030. If the receipt shows anything else pending, stop rather than widen the gate.

For an independently approved production/staging target, with its actual environment
already supplied by the secret manager, export the exact plan first:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py release_migrations --database-name $env:RELEASE_DATABASE_NAME --manifest-file .\output\acceptance\reviewed-release-plan.json
```

Pending steps intentionally return a nonzero status after manifest export. Preserve
the file, attach backup/restore evidence and named approval, then ONLY after separate
explicit authorization:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py release_migrations --database-name $env:RELEASE_DATABASE_NAME --apply-approved-plan --approval-file .\output\acceptance\release-approval.json
```

Do not substitute dawana_dev or demo into this production mechanism; it refuses them.

## Exact approval request

No migration approval is ready to request until the database-specific receipt and
verified backup/restore evidence exist. Run the one read-only demo command above.
Then request: “Approve only the exact pending steps and source hashes in receipt
<actual receipt filename>, on dic_2026_demo, with backup <verified backup/hash> and
restore drill <evidence>. No other database, staff grants, live payments or deployment.”
Do not treat this template as issued approval or assume the pending set is 0027/0031.
