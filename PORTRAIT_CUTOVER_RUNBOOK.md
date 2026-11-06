# Portrait continuity and production acceptance — correction pass 3

## First production release — no data or portrait transfer

Production starts with a new, empty database. No local/demo database or participant
data is transferred, and no local/demo portraits are copied. Do not execute
`portrait_inventory`/`copy_portraits` as part of initial production setup. During
separately approved production acceptance, verify only the new production target's
own empty participant/portrait inventory, configure its independent private
storage, and record approval before enabling DIC_PORTRAIT_CUTOVER_VERIFIED.
An unknown legacy source bucket is not a blocker to this empty-data approach.
No copying, deletion, credential discovery or environment change is authorized.

Email/password remains the approved sign-in; Google remains unconfigured.
Live DIC payment readiness is independent of Foundation donations, which remain
disabled and deferred. The owner supplies registration dates and the Early Bird
cutoff; registration stays closed until production acceptance and owner approval.
Approved fees, the 17-year-old classification and tutor entitlement are unchanged.

## Historical/conditional maintenance reference — not initial setup

The copy procedure below is retained technical history for a possible separately
approved future production maintenance task. It is not authorization to import
local/demo/staging data, create environments or perform a first-release cutover.
Nothing in this runbook has been executed. Migration 0036 is a field-state
change, not a file migration or proof of media continuity. Historical migrations
0023 and 0036 are unchanged.

## Historical source identity — relevant only to a separately approved future task

0023 used `dic.memory_storage.private_memory_storage`. Before the production
split this resolved to `DIC_MEMORY_S3_BUCKET`, `DIC_MEMORY_S3_ENDPOINT`, and
`DIC_MEMORY_S3_REGION`, using boto3's existing AWS credential chain. Development
could instead use the local private-memory directory. That is the exact source
configuration path; it does **not** establish a deployed literal bucket name.

The deployed configuration and credentials were deliberately not read. The
existing plan mentions `dawana-staging-media`, but that is not evidence that any
particular production portrait came from that bucket. Do not infer source
identity from a filename prefix or reuse staging credentials in production.

Before scheduling anything, the owner must record for each database: a
non-secret database identity, the storage mode and exact source account/endpoint,
literal source bucket (or local root), and the independently approved destination
account/endpoint and bucket `dawana-production-private`. Verify these against
deployment records and a provider inventory through an authorized operator.
The earlier cross-dataset transfer proposal is superseded for initial production.
Local/demo/staging imports are not authorized. Production must never use staging
as a runtime fallback. The retained helper supports object-storage sources only;
any future production-only use needs a new reviewed scope and adapter.

**Conditional future-task decisions, not first-release blockers:** actual source bucket/account for each dataset, selected
databases, transfer authorization, least-privilege operator clients, maintenance
window, destination privacy and certificate/network verification. No copying is
safe until these are settled. This change supplies no operational CLI or SDK
client construction and performs no credential discovery.

## Historical exact-key copy procedure — excluded from first production setup

1. Approve a maintenance window and suspend every writer, including web workers,
   jobs, admin uploads and external integrations, across all databases sharing
   either storage account/bucket. Keep writers suspended throughout inventory,
   copying, final verification and cutover. Record the backup/restore decision.
2. An authorized operator uses a read-only database transaction on each approved
   database to enumerate only nonempty `CampEnrollment.portrait` names. For a
   later reviewed ORM adapter, the selection is
   `CampEnrollment.objects.exclude(portrait='').values_list('portrait', flat=True)`.
   Do not run manage.py or load application settings automatically from this
   runbook. Do not select participant names, IDs, email, telephone or QR tokens.
   Feed those strings into `portrait_inventory`; it preserves exact keys and
   counts shared references. Record the database identity separately. Keep the
   raw-key manifest in restricted operator storage; publish only counts and key
   digests. An empty inventory is an explicit result, not an assumption.
3. Write the approved literal source and destination bucket names and account
   identities into the restricted manifest. The source is **unresolved** until
   step 1's owner decisions are complete; the destination bucket is explicitly
   `dawana-production-private`. Validate scoped, independently supplied clients
   against those identities without logging credentials. Source permission is
   read-only. Destination permission permits reads and create-only writes.
4. The reviewed adapter may call `dic.portrait_cutover.copy_portraits` with the
   inventory, supplied source/destination clients, explicit bucket arguments,
   `maintenance_approved=True` and `writers_suspended=True`. These flags are
   operator assertions, not technical enforcement of a maintenance window.
   Review the adapter and SDK conditional-write compatibility before use. It
   must not call Storage.save, which would rename/re-encode files.
5. The helper reads each source at its observed ETag, preserves the exact key,
   and creates missing destination objects with `IfNoneMatch='*'`. It never
   overwrites or deletes a source/destination object. A matching existing
   destination is verified again without writing. A conflicting destination,
   absent source, failed read/write, size mismatch or SHA-256 mismatch stops the
   batch at once. No next key is attempted. Retain `CutoverStopped.report` on
   failure and mark remaining manifest entries **not attempted**.
6. Verification compares full downloaded source/destination SHA-256 values,
   downloaded sizes and destination HEAD size. A provider full-object SHA-256,
   when available, is also checked. Multipart ETags are never treated as checksums.
   Reads are bounded to the application's 12 MB portrait limit. Exceptional
   legacy formats/sizes require owner review; do not silently skip them.
7. Save each sanitized report (key digest, explicit buckets, status, byte count
   and verified SHA-256) against the restricted manifest. Failures expose only
   fixed reason codes. After fixing an approved issue, rerun the same inventory:
   identical destinations are `verified_existing`, not overwritten. Do not
   change database keys. Complete every database inventory, deduplicating keys
   only within the same source/destination identity.
8. Re-inventory while writers remain suspended; compare with the frozen manifest
   and reverify every referenced destination. Only after every object succeeds
   may the owner approve production routing and later set
   `DIC_PORTRAIT_CUTOVER_VERIFIED=True` through a separate operational change.
   For a new empty production dataset, record the verified empty manifest before
   approval. This source pass does not set any environment variable.
9. Keep source objects and backups. Verify authorized portrait/card/PDF retrieval
   and unauthorized rejection in the approved environment, then resume writers.
   If verification fails, keep cutover blocked and follow the reviewed rollback
   plan; no automatic fallback or bucket redirection is provided.

No source deletion is part of cutover. Before any future deletion proposal,
inventory **every database and external reference catalog** sharing the bucket,
suspend writers, and obtain separate approval. The current single-database
maintenance primitive cannot establish global non-reference. Storage deletion
cannot be undone by a database rollback.

## Runtime safeguards

Production participant storage keeps existing keys and reads only the independently
configured private bucket. Until cutover approval is recorded, referenced portraits
fail with a sanitized 503 before any object lookup. After approval, missing or
invalid referenced portraits also fail explicitly; HTML cards, portal downloads,
staff cards and PDF exports do not silently replace them with blank portraits.
Participants without a supplied portrait remain supported. Authorization checks
still precede rendering/storage. Staging's existing storage routing is retained.

## TLS, origins and acceptance

Both staging and production accept only `sslmode=verify-full`. Configure the
authenticated external Render PostgreSQL hostname and a trust store supported by
the deployed libpq (`DB_SSLROOTCERT` where needed). Certificate-chain validation,
hostname validation, connectivity and least-privilege network restrictions must
be tested separately before deployment. No hostname suffix, matching environment
string or provider name permits `require`/`verify-ca`. If those external endpoint
checks cannot be verified, deployment remains **blocked**. See
[Render connection documentation](https://render.com/docs/postgresql-creating-connecting)
and [libpq certificate verification](https://www.postgresql.org/docs/18/libpq-ssl.html).

Use separate HTTPS frontend/API origins under the same registrable site, for
example `https://www.example.org` and `https://api.example.org`. Keep cookies
`SameSite=Lax`. Unrelated frontend/API sites require a separately approved
authentication redesign; CORS alone cannot make those cookie flows work.
Credentialed CORS permits exact trusted frontend origins only, with matching CSRF
configuration; wildcard and regex origins are rejected. No R2 URLs are returned.

Published public image/video responses allow `CORP: cross-origin` through API
routes. Authorized previews and private participant responses retain private
policies and `private, no-store`. Public assets also retain no-store so content
withdrawal is not defeated by shared caches. Upcoming lecturers/activities need
active editions; historical lecturer appearances remain available exactly as in
the previous-edition listing. Authorized staff can preview inactive drafts.

Expected configuration, validation and provider errors return fixed sanitized
404/503 responses. After streaming headers have been sent, failures terminate
the stream and emit a fixed log message without exception details; HTTP status
cannot reliably change at that point. Browser acceptance across the actual
origins, including publication withdrawal, session cookies, CORS, previews,
portrait/PDF authorization and mid-stream failure behavior remains outstanding.

## Owner-terminal Python probes — no settings or environment changes

From the repository root in the owner's ordinary PowerShell terminal, first run:

```powershell
& .\backend\.venv\Scripts\python.exe -I -B --version
```

Only if it starts, verify dependency imports without loading project settings:

```powershell
& .\backend\.venv\Scripts\python.exe -I -B -c "import django, rest_framework, environ, corsheaders, psycopg, boto3, PIL, cryptography, qrcode, reportlab; print('Dependency imports OK')"
```

Do not reinstall, change PATH/permissions or replace the environment if either
probe fails. The sandbox reproduced Access is denied before Python startup.
Metadata presence proves no imports, Django checks or backend tests.

The later database/network-denying mocked runner is:
`backend/.venv/Scripts/python.exe -I -B scripts/test_production_policies.py`.
It configures synthetic settings without dotenv and rejects database test cases
and network/database connections. Do not substitute manage.py test, migrate,
makemigrations or a development/demo database. Its results remain unverified
until an authorized usable runtime actually executes it.

## Historical correction-pass-3 checks — not current release acceptance

From `dawana-platform`, with dotenv loading disabled:

```powershell
node --import ./scripts/source-only-vite.mjs --test --test-concurrency=2 src/services/*.test.js
npm.cmd run lint -- --ignore-pattern 'dist-correction-pass-3/**'
node --input-type=module -e "import { build } from 'vite'; await build({envDir:false,build:{outDir:'dist-correction-pass-3',emptyOutDir:false}})"
```

Final frontend result: **229 passed, 0 failed, 0 skipped**. The preload only adds
dotenv/optimizer guards to test-created Vite servers;
assertions are unchanged. The build output is a local review artifact, never
deployed. Existing `dist` and root caches are not cleaned. The build succeeds
with a large-chunk warning. Source lint is clean. An initial `npm run lint`
could not start because PowerShell blocks npm.ps1; npm.cmd requires no policy
change. Unfiltered lint also scanned generated bundles and warned; the reported
source-lint command excludes that artifact directory.

The exact attempted backend command from the repository root was:

```powershell
& backend/.venv/Scripts/python.exe -I -B scripts/test_production_policies.py dic.test_portrait_cutover.PortraitCutoverTests dic.test_media_corrections.MediaCorrectionTests dic.test_media_corrections.ShowcaseVisibilityTests dic.test_render_configuration.RenderConfigurationTests dic.test_storage_production.ProductionStorageTests dic.test_storage_production.MediaAuthorizationTests dic.test_release_readiness.ReleaseReadinessTests
```

It failed before Python startup with:
`did not find executable at 'C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe': Access is denied.`
Zero backend tests executed. No Django imports, checks, model-state verification,
migration-graph verification or backend runtime behavior are claimed as passed.
The Store interpreter discovered by `py -0p` also failed its version-only probe:
`py -3.13 -I -B --version` returned `Unable to create process ... Access is denied.`
