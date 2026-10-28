# DIC 2026 final database and publication sequence

Prepared 28 October 2026, Africa/Lagos. No database connection or write, migration, import, publication, grant, activation or deployment was performed. The operator's 180 backend / 225 frontend passing tests, lint/build and timetable preview are accepted as operator-reported results; the full test programme was not repeated. Games are excluded and are not launch blockers.

## 1. Migration review and actual checks

`dic.0033_launch_completion` contains **only five CreateModel operations**: AcademicClass, AcademicAssignment, CampAnnouncement, ContactEnquiry and FoundationDonation. There is no AlterField, RemoveField, DeleteModel, RunSQL or RunPython, no existing-row backfill and no transformation of registration, payment, guardian or portal records.

Fields match their source models on inspection. Existing Participant/CampEdition foreign keys use PROTECT; audit actor keys are nullable SET_NULL. New references do not rewrite referenced records. New class constraints enforce unique edition/name and edition/participant; announcement checks enforce valid publication state/window; donation constraints enforce positive NGN amounts and allowed states, with unique request ID and reference. Django supplies primary-key, unique and foreign-key indexes. Existing timetable composite index/source uniqueness remain unchanged. Current data volumes do not establish a need for additional speculative indexes.

Custom permissions are appropriate and do not automatically grant user/group membership. Applying the reviewed plan also initializes content types/permissions through post_migrate; that is expected metadata creation, not a staff-role grant. Existing eligibility/grant boundaries are unchanged. Academic projection is edition-scoped and schema-pending tolerant; announcements reuse the authorized participant/guardian item boundary. Source review is not a live access test.

Dependency chain: `0033 → 0032 → 0031 → 0027 → 0026`, with each existing graph dependency and swappable user dependency preserved. Earlier 0028/0029/0030 ordering remains as defined in the existing graph; no migration file was edited. **No actual migration defect was found, so no schema change was made.** The whole pending plan must still be reviewed; approving only 0033 does not authorize older pending migrations.

Executed: timetable source checks PASS (188 entries, ten consecutive dates, two types, 188 distinct source keys, approved opening/Basic Islam/Day 6/Final Night slots). The initial ad-hoc inline Unicode check was affected by PowerShell pipe encoding; it was corrected with Unicode escapes and passed without changing data. Django source graph/model-state consistency was attempted but **NOT RUN**: the agent cannot start its configured Python interpreter (access denied). No retry/install or full suite was run.

### Safe immediately: source-only consistency, no database connections

From repository root, in the operator's working local PowerShell:

```powershell
& .\backend\.venv\Scripts\python.exe -B .\scripts\review_dic_launch_migration.py
```

The new checker blocks network/database connection methods, loads `MigrationLoader(None)`, verifies five additive tables and unchanged previous model states, checks source/model parity and Django checks, and runs no unit/integration suite. Resolve any failure before proceeding.

## 2. Current configured target — not an approved release target

Selective configuration metadata inspection (no secrets printed) establishes:

| Item | Finding |
|---|---|
| Settings | `config.settings.development`, the manage.py default; no process override |
| Engine | `django.db.backends.postgresql` |
| Host / port | `127.0.0.1:5432` |
| Database | **`dawana_dev`** via DB_* configuration |
| Staging / production | Not selected by this workspace/default command context; deployed environments not inspected |
| Is 0033 applied? | **UNVERIFIED** — no database connection authorized/performed |

This describes workspace configuration, not a running service's identity. The historical demo receipt does not establish the current state of dawana_dev or any release database.

**Required operator confirmation:** intended environment/settings module, exact PostgreSQL host/port/database, whether read-only plan inspection is authorized, DIC edition primary key, approved importer and publisher usernames, and the separate migration/import/publication decisions. Confirm a release target explicitly rather than assuming dawana_dev is production.

The existing `release_migrations` mechanism intentionally accepts only explicit staging/production settings and rejects `dawana_dev`, `dic_2026_demo` and system databases. It must not be bypassed. If dawana_dev is deliberately selected, stop: a separately reviewed development migration execution procedure is needed; the staging/production command below is not applicable. No unrestricted `manage.py migrate` workaround is supplied.

## 3. Exact commands after context confirmation

The following are command templates using **operator-supplied variables**, not guessed target/account values. Run on the approved host/session whose secure configuration actually resolves to that exact database; never paste credentials or URLs into commands. All commands are from repository root.

```powershell
$Py = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
$Manage = (Resolve-Path .\backend\manage.py).Path
$ReleaseSettings = Read-Host 'Approved settings: config.settings.staging or config.settings.production'
$TargetDatabase = Read-Host 'Exact approved release database name'
$EditionId = [int](Read-Host 'Approved DIC 2026 edition primary key')
$Importer = Read-Host 'Approved timetable editor username'
$Publisher = Read-Host 'Approved timetable publisher username'
$SeedSha = '046fa64c9fd99de6c4e18e1c38ab8557d3879128cd131696e4ea94b553282bbf'
if ($ReleaseSettings -notin @('config.settings.staging','config.settings.production') -or
    [string]::IsNullOrWhiteSpace($TargetDatabase) -or
    $TargetDatabase -in @('dawana_dev','dic_2026_demo','postgres','template0','template1') -or $EditionId -lt 1) {
    throw 'Release context is unapproved or unsupported. Stop before connection.'
}
```

**Safe source previews after those non-secret values are supplied; no database queries or writes in the preview handlers:**

```powershell
& $Py $Manage import_dic2026_timetables --edition $EditionId --settings $ReleaseSettings --skip-checks
& $Py $Manage publish_dic2026_timetables --edition $EditionId --settings $ReleaseSettings --skip-checks
```

**Requires explicit read-only database-connection approval first:** generate the actual pending manifest. This connects to the approved database but does not apply schema. It normally exits nonzero when pending migrations require approval; preserve the new manifest rather than treating that message as an applied migration.

```powershell
$PlanFile = Join-Path (Resolve-Path .\output\acceptance).Path ('release-plan-' + [guid]::NewGuid().ToString('N') + '.json')
& $Py $Manage release_migrations --database-name $TargetDatabase --manifest-file $PlanFile --settings $ReleaseSettings
```

**Requires separate migration approval and verified backup/restore/rollback evidence:** approval JSON must contain the exact manifest plus `approved_by`, `approved_at`, `backup_reference`, `restore_procedure`, `rollback_decision`. Never reuse the older demo approval/receipt as this approval.

```powershell
$ApprovalFile = Read-Host 'Path to separately reviewed exact-plan migration approval JSON'
& $Py $Manage release_migrations --database-name $TargetDatabase --apply-approved-plan --approval-file $ApprovalFile --settings $ReleaseSettings
```

This applies the approved full pending plan, not just 0033. A changed source/target/plan invalidates approval. No startup hook supplies this application flag.

**Requires separate approval to import drafts into this exact database/edition:**

```powershell
& $Py $Manage import_dic2026_timetables --edition $EditionId --database-name $TargetDatabase --approved-by $Importer --approved-seed-sha256 $SeedSha --apply --settings $ReleaseSettings
```

**Requires a distinct publication approval after draft review:**

```powershell
& $Py $Manage publish_dic2026_timetables --edition $EditionId --database-name $TargetDatabase --approved-by $Publisher --approved-seed-sha256 $SeedSha --apply --settings $ReleaseSettings
```

Import is atomic and idempotent: stable source keys prevent duplicates and an audit receipt preserves later edits/deletions on reruns. It never publishes. Publication checks the matching import receipt and exact reviewed snapshot; already published rows are unchanged. Staff edits/extra entries cause the command to stop for deliberate Admin review instead of overwriting them. The approved edition must have the expected camp dates. No staff edits are silently reset.

## 4. Timetable content and staff setup

Source remains 188 entries: **158 activities and 30 food periods**, December 23, 2026–January 1, 2027 inclusive. Exactly Daily Activities and Food. December 24 opening 09:00–11:00 and Basic Islam 11:00–13:00; December 28 health forum 11:00–13:00 and sports 17:00–18:30. December 31 sisters' workshop / brothers' activity remains as approved; **Final Night** has the original 21:00 start and open-ended source labels, without invented details. Food is unchanged. Reconciled SHA-256 is `$SeedSha` above. No data was imported/published.

Assign only named, operator-approved active staff accounts via Django Admin; no blanket staff grants:

| Function | Exact permissions |
|---|---|
| Academic classes/assignments | `dic.manage_dic_classes` |
| Timetable view | `dic.view_timetableentry` (edit/publish holders also have Admin view through explicit checks) |
| Timetable draft editing | `dic.manage_dic_timetables` |
| Timetable publish/unpublish | `dic.publish_dic_timetables` |
| Announcement drafts | `dic.manage_dic_announcements` |
| Announcement publication | `dic.publish_dic_announcements` |
| Contact inbox read/update status | `dic.view_contactenquiry`, `dic.change_contactenquiry` |
| Donation audit read | `dic.view_foundation_donations` |

Operations entry additionally requires its existing Operations permission; these new permissions do not imply it. Approved academic names go in `/admin/dic/academicclass/`; assign registered campers at `/admin/dic/academicassignment/`, choosing the same edition. No class names/accounts are invented. Houses remain independent. Announcements use `/admin/dic/campannouncement/`; draft first, publish separately. Contact staff use `/admin/dic/contactenquiry/`; donation reviewers use `/admin/dic/foundationdonation/`. Grant changes and content creation/publication need their own operator-authorized administrative session.

## 5. Contact and test-donation activation

- Public verified source: `backend/dic/data/foundation_contact.json`, containing the operator-confirmed email and three phones. No extra credential/configuration is needed to display these via `/api/v1/foundation/options/`. Do not set `FOUNDATION_CONTACT_VERIFIED=True` unless supplying reviewed replacement `FOUNDATION_CONTACT_EMAIL/PHONE/WHATSAPP/ADDRESS`; otherwise retain the supplied source. No WhatsApp/address is invented.
- After schema and named staff inbox access are approved, `FOUNDATION_CONTACT_FORM_ENABLED=True` enables protected enquiry writes. Otherwise it remains off. CSRF, validation, IP throttling, honeypot and deduplication remain active. Agree inbox ownership/retention. No email/SMS send is needed to receive an enquiry in the staff inbox.
- After separate test-collection approval, `FOUNDATION_DONATIONS_ENABLED=True`, `FOUNDATION_DONATION_CURRENCY=NGN`, existing `PAYSTACK_MODE=test` and an existing securely supplied `sk_test_` key enable donation checkout. No actual key should be printed. Defaults permit NGN 0.01 through the signed 64-bit kobo ceiling; provider limits still apply. No business maximum was invented.
- Donation initialization: `POST /api/v1/foundation/donations/`; protected status and verification: `GET/POST /api/v1/foundation/donations/<reference>/` with private `X-Donation-Token`. Tokens do not belong in URLs/logs. Contact/donation writes require CSRF; API origins must allow the configured CORS/CSRF headers/origins.
- Donation webhook: `POST /api/v1/foundation/donations/webhook/`. Separately approve configuring the provider's test webhook to that exact HTTPS route. Raw-body HMAC validation and server-side verification remain mandatory; never redirect the DIC registration webhook to this route. Donation references/records are separate from DIC registrations. Review how the test integration is routed if the provider account permits only one webhook destination; do not replace an existing working DIC webhook automatically.
- Donors return to the original tab and use Verify payment status. Successful settlement is monotonic/idempotent; pending/failed/abandoned/mismatched/uncertain states are not successful revenue. Hosted checkout/provider replay testing needs the authorized target; no provider request was made here.
- Live collection is deliberately rejected. Do not switch to live keys/mode to deploy this test-only flow. Live donation/payment activation remains a separate reviewed decision.

## 6. Production prerequisites and approval decisions

Confirm the actual release host/settings/database before any connection. Preserve a verified backup and disposable restore/rollback evidence; approve the exact full pending manifest. Configure approved secrets privately, exact HTTPS hosts/origins, trusted proxy/TLS, shared cache and separately approved cache table if needed, static build/collectstatic and verified email delivery for existing portal activation/recovery. Follow existing Render release controls; health alone does not prove schema/cache readiness. Do not enable public registration, change working payment/webhook routing or deploy without the relevant approval.

Remaining decisions: intended target (current local dawana_dev is not implicitly approved), read-only inspection approval, full migration approval, importer/publisher identities and edition ID, separate import/publication approvals, staff grants/approved class names/announcement content, contact inbox activation, test-donation activation/webhook routing, and deployment approval. No full retest is requested; execute the source checker, inspect the approved live plan, then perform focused post-change smoke checks on that target.
