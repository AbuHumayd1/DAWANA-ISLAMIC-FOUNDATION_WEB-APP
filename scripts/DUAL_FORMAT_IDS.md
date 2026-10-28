# Phase 3 dual-format identification and safe preview restoration

For a legacy manifest with no exact launch timestamps, see
[LEGACY_PREVIEW_RECOVERY.md](LEGACY_PREVIEW_RECOVERY.md). Normal restoration still
refuses it; a separate typed authorization can approve shutdown of the currently
verified demo tree without fabricating historical metadata. That recovery has been
prepared only, not executed.

## Process-validation follow-up

The confirmed demo can contain several nested Python processes plus Windows console
hosts, rather than a single reloader child. Restoration now traverses the full
backend/frontend descendant trees. Each backend Python must use the project's venv
or the interpreter recorded in its pyvenv.cfg, with the exact demo-helper path and
serve arguments. Vite must match its exact executable/helper/launch arguments.
System32 conhost.exe is recognized only beneath a verified parent, with restricted
console-host arguments and no descendants; arbitrary non-Python processes fail.
Children must not predate their current parent. Port 8000 must belong to the verified
backend Python tree; 5173 must belong to the recorded Vite root. Both must be loopback.

Future startup manifests save launcher creation times in UTC. The validator compares
those times (1 ms tolerance for CIM/.NET timestamp precision), and later rechecks
the full tree, parent IDs, creation times, executable paths, command lines and port
owners before any termination. Python/Vite nodes are stopped deepest first; console
hosts are never explicitly terminated.

The current legacy manifest has no exact creation-time fields. The timestamp in its
log filenames supports only a narrow launch-time audit (within 30 seconds), not a
complete PID-reuse guarantee. Non-restoring audit can proceed with a warning if all
other evidence matches; restoration refuses the legacy manifest. Do not manufacture
historical start times or bypass the guard to make restoration proceed.

Codex attempted `.\scripts\restore-normal-preview.ps1` without restoration switches,
but its PowerShell host rejected script execution under the existing execution
policy. No policy bypass/change was attempted; no process or database was touched.
Both modified scripts passed syntax checks. Run that same read-only command in your
existing authorized PowerShell environment to establish the current audit result.

## Implemented without a migration

- Existing no-parameter card URLs still render landscape **85.6 × 54 mm PVC**.
- `?format=a6` renders a distinct **105 × 148 mm portrait camp badge**, with a
  larger portrait, name, ID and QR, and a 6%-width top safe area for the header.
- Both read the same enrollment, participant number and currently active QR issue.
  Viewing/downloading/printing does not issue, replace or revoke credentials.
- Card GETs and batch print rendering no longer insert print-view audit records.
  Issuance/revocation and QR verification retain their existing audit behavior.
- Repeated enrollment inputs are deduplicated before rendering. No new registration,
  participant, guardian, housing or payment records are created by printing.
- Unsupported `format` or `printer` values return HTTP 400 after staff authorization.
- Both formats embed the existing cached official logo, private portrait and QR.
  No CDN/image fetch is needed to render downloaded HTML; online verification still
  requires the backend. The QR URL/token mechanism is unchanged.
- Literal question marks from earlier template writing were found in labels. Those
  damaged punctuation labels now use `&times;`, `&mdash;` and `&middot;` entities.
  UTF-8 source/HTML/HTTP charset and user-supplied Unicode are preserved; Arabic or
  participant names are not globally rewritten. Old synthetic DB names are not edited.

The official logo is now present locally at
`backend/dic/static/dic/dawana-official-logo.img`, with source/hash provenance beside
it. This task does not substitute a favicon or invent a new logo.

## Physical printing limits — no silent shrinking

**PVC single:** centred on A4 portrait, actual 85.6 × 54 mm.

**PVC batch:** eight per portrait A4, 2 columns × 4 rows, 6 mm gaps. Cards occupy
177.2 × 234 mm within the 186 × 273 mm content area (12 mm paper margins).

**A6 single:** centred on A4 portrait with normal margins, actual 105 × 148 mm.

**A6 four-up:** 2 × 2 on portrait A4, zero page margins/gaps. Actual badges occupy
210 × 296 mm, compared with paper 210 × 297 mm. There is NO horizontal margin and
only 1 mm spare vertical space. **A4 borderless printing is required** for reliable
outer edges. Ordinary printers can clip the sheet; choosing Fit to printable area
would shrink the badges and is not an acceptable substitute. Edge-to-edge trimming
has no bleed allowance, so use a careful straight cut or suitable print service.

**A6 ordinary-printer alternative:** select **two-up landscape A4**, with 12 mm paper
margins and 6 mm cutting gap. Two actual-size badges occupy 216 × 148 mm inside a
273 × 186 mm printable content area. No dimensions are reduced.

Choose A4, the instructed orientation, **100% / actual size**, headers/footers OFF
and background graphics ON. The app cannot enforce browser-controlled options.
Downloaded HTML has the same print CSS and embedded assets. Measure a saved PDF
and physical proof; browser/automated CSS checks alone do not establish scan reliability.

## Current environment evidence and limits

At investigation time:

- Branch: `staging/dawana-e2e`; original uncommitted changes preserved.
- Latest saved demo manifest: `dawana_ids_demo_c936c26ba558429eb4b4fda3b5c62668`.
- Saved normal preparation target: `dawana_dev` on 127.0.0.1:5432.
- Saved launchers: backend 22928, frontend 1152. **These are historical, not approved
  current process identities. Do not stop those PIDs from this document.**
- Vite proxies `/api`, `/admin`, `/static` to `DJANGO_API_PROXY_TARGET`, default
  http://127.0.0.1:8000. The documented launcher uses that target and `/api/v1`.
- `id_demo.py serve` explicitly selects its saved isolated database. Its seed creates
  `SYNTHETIC DEMO — DIC 2026` and fee 100 only in a new `dawana_ids_demo_*` database.
  Thus the observed title/fee are the expected **backend demo data**, not a new
  production fee or a frontend replacement constant. No records were changed to hide it.
- The saved backend log contains successful requests for registration options and
  showcase from that preview. However current process metadata is denied in Codex,
  and a live `SELECT current_database()` has **not** been executed here. Therefore
  the saved manifest cannot be claimed as proof of the current live DB.

No processes were stopped by Codex and the normal preview has **not** been restored
or verified from this tool session. Python also remains inaccessible. Every demo DB,
validation report, backup and fixture remains preserved; dawana_dev records are unchanged.

## Local execution in the required order

### 1. Run focused tests, leave demo running

```powershell
.\scripts\validate-dic-backend.ps1 -IdsOnly
```

Expected identification count is now **28**, not 18 or 22. The combined housing/ID
suite is **70**. The runner requires all selected tests to execute with no skip,
missing tests, error or failure. It uses a new isolated PostgreSQL test database;
the actual name/counts appear in `validation-results/*.json`. No existing test DB is
reused or deleted. Prior retained **60/60** success predates these dual-format changes;
it must not be reported as a current 70-test result.

Tests cover shared QR across formats, no SQL writes during rendering/download,
unsupported parameters, PVC eight-up, A6 four/two-up, partial pages, deduplication,
UTF-8/Arabic, permission enforcement, revoked/replaced credentials and local diagnostic
access. Existing eligibility/payment/guardian rules are used unchanged.

### 2. Review the actual synthetic demo in your browser

Directory: http://127.0.0.1:8000/admin/dic/campenrollment/

Use **PVC view / print**, **A6 view / print**, **PVC HTML**, **A6 HTML** on a record.
The same card URL accepts:

```text
/api/v1/dic/ids/cards/ENROLLMENT_UUID/
/api/v1/dic/ids/cards/ENROLLMENT_UUID/?format=a6
/api/v1/dic/ids/cards/ENROLLMENT_UUID/?format=a6&download=1
/api/v1/dic/ids/cards/ENROLLMENT_UUID/?format=a6&layout=batch
/api/v1/dic/ids/cards/ENROLLMENT_UUID/?format=a6&layout=batch&printer=standard
```

Replace ENROLLMENT_UUID with an actual directory record, not a participant number.
Existing links without parameters remain PVC. Admin actions distinguish PVC eight-up,
A6 four-up borderless and A6 two-up standard-printer layouts. These print actions use
existing active IDs only. The separate existing issuance action remains explicit.

Review portrait/missing portrait, full long name, assigned/pending house, child ID,
synthetic labels, UTF-8 labels and mobile layout. Save both HTML formats, disconnect
network or stop the servers later, then reopen: CSS/logo/portrait/QR must still render.
Live QR verification cannot work offline. In local loopback mode a separate phone
cannot reach this computer's 127.0.0.1; do not expose the development server publicly.
Use **Verify this ID** for a local credential check and retain camera/physical-scan
sign-off for a reachable approved verification environment.

Verification: http://127.0.0.1:8000/api/v1/dic/ids/verify/

For partial/multiple-page geometry tests, synthetic files appear under the runner's
reported `.local-preview/id-print-qa/<isolated-test-db>/` path. Fixtures using repeated
mock card content are explicitly geometry fixtures; they do not establish distinct
credential correctness. Actual batch rendering deduplicates enrollment IDs.

### 3. Read-only running-environment investigation

```powershell
.\scripts\restore-normal-preview.ps1
```

This inspects current port owners plus executable, command line, creation time and
parent links. It accepts only this repository's recorded `id_demo.py serve` and Vite
processes and their verified reloader child. Any unknown ownership stops the script.

A new development-only diagnostic performs `SELECT current_database()` inside the
running app and then through the Vite proxy, without reading participant records.
It is loopback-only, requires development settings + DEBUG, and a local random token
from ignored `.local-preview/diagnostic-token` sent only as an HTTP header. No token,
password, DB user or connection URL is printed. It is unavailable publicly and when
DEBUG is false. This proves actual running DB identity rather than relying on .env.

Existing Django's reloader normally loads this new route/configure code. If no token
file/route is available yet, restart only the demo you own from its original console:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\id_demo.py serve
```

That reuses the saved demonstration DB and does not reseed it. Do not run duplicate
backends. If process discovery is denied in your PowerShell too, stop and inspect
manually; do not bypass ownership checks or kill all Python/Node processes.

### 4. Restore only after both demo formats pass review

```powershell
.\scripts\restore-normal-preview.ps1 -Restore -DemoFormatsReviewed
```

This is an explicit statement that you reviewed both formats. It reruns the 28 ID
tests, then performs normal development preparation with **--no-migrations**.
That requires the real configured target to be exactly `dawana_dev`, Django checks,
no pending migrations and an actual DB-name SELECT. It never seeds, updates, migrates
or restores the real database. Pending migrations stop restoration before processes
are terminated; report them and obtain separate authorization for backup-gated handling.

Only after those gates does it reverify each current PID/executable/command/creation
time immediately before termination, stop known demo children/launchers, and launch
the normal backend/frontend. All synthetic DBs remain. A JSON restoration report is
retained under `.local-preview/` with the before/after DB identity and stopped PIDs.
It verifies direct backend and Vite-proxied DB identity are `dawana_dev`, health/routes
respond, and reads the actual configured edition. It reports any synthetic label in
dawana_dev without editing it. Review fee, venue, deadline and registration status
in the DIC page; no replacement values are supplied by the script.

Final intended URLs:

- Frontend: http://127.0.0.1:5173/
- DIC: http://127.0.0.1:5173/dic
- Backend: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

Normal foreground alternatives after successful read-only preparation:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts\local_preview.py prepare --no-migrations
.\backend\.venv\Scripts\python.exe -B scripts\local_preview.py serve
```

Second terminal:

```powershell
$env:DJANGO_API_PROXY_TARGET = 'http://127.0.0.1:8000'
$env:VITE_API_BASE_URL = '/api/v1'
npm.cmd --prefix .\dawana-platform run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

These commands do not migrate the real database. Existing backup-gated migration
support is preserved but is deliberately not invoked by this restoration flow.

## Changed files in this continuation

- `backend/dic/identity_views.py`, `identity_admin.py`, `templates/dic/identity_cards.html`
- `backend/dic/test_identity_cards.py`, `local_diagnostics.py`, `urls.py`
- `scripts/local_preview.py`, `start-local-preview.ps1`, `restore-normal-preview.ps1`
- This runbook and links from older printing instructions.

No new migrations, dependencies, participant identities or checkpoint functionality.
No edits to registration, pricing, Paystack, housing or guardianship rules.

## Honest validation status

Current automated tests executed by Codex: **0** (Python access denied).
No current pass/fail/skip claim; run the commands above for actual counts.
Browser JavaScript syntax, PowerShell syntax and whitespace checks passed.
Physical dimensions, borderless capability, PDF pagination, offline rendered
appearance, camera scan reliability and final live DIC restoration remain manual
checks. Prior browser attempts in this tool environment failed during initialization.
