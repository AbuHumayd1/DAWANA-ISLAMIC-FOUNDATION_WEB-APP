# Phase 2 completion and Phase 3 identification — LOCAL-FIRST

For the current dual-format Phase 3 implementation and restoring the normal
development preview without database writes, follow [DUAL_FORMAT_IDS.md](DUAL_FORMAT_IDS.md).
Current suite: 28 identification tests, 70 combined. Earlier counts below are historical.

Latest printing refinements: see [ID_PRINTING.md](ID_PRINTING.md). The retained
085711 report confirms the earlier 60/60 pass. Four new presentation tests bring
the current suite to 64 (22 identification tests); those additions await execution.
Use `complete-local-identification.ps1 -IdsOnly -IdDemo` for focused ID validation
and the isolated print preview, including caching the exact existing website logo.

Workspace: `C:\Users\hp\Desktop\DA'WANA WEB--APP`, branch `staging/dawana-e2e`.
No push, deployment, live payment call, real allocation worker, portal or check-in
activation is included. Existing work, stash and recovery backups remain intact.

## What the previous test report actually proves

`validation-results/20261024T073256Z-f416d2.txt` says **Found 42**, but **Ran 10**.
Only nine `AllocationAdminPermissionTests` and one `HouseAllocationTests` ran.
None of `dic.test_housing_phase2` ran. The prior overall PASS was incorrect.
The original runner only checked Django's failure count. Django's default
`suite_result()` counts failures/errors and does not reject an early-stopped
suite. Its installed interrupt handler can stop a run cleanly while unittest
still prints OK for the completed subset. The historical reason for stopping
was not captured; interruption is a possibility, not an established fact.

The corrected runner records discovered IDs, attempted tests, **executed
non-skipped tests**, skipped and missing IDs, stop status and counts per module.
It rejects incomplete runs, missing selected modules, and skipped required tests.
Safe RUN/PASS/FAIL progress prints live; raw failure details remain in the redacted
log. Do not interrupt a running test just because it is taking several seconds.

The original combined suite contained **60 tests** (now 64 with print refinements):

- `dic.test_allocation`: 23.
- `dic.test_housing_phase2`: 19.
- `dic.test_identity_cards`: originally 18; now 22.

Repair following `20261024T081546Z-7541f2`: all 60 actually ran; housing passed
42/42, identification passed 1/18 with 15 errors and 2 failures. The Phase 3 test
class reused an operations fixture whose users intentionally had `is_staff=False`.
That correctly triggered ID/guardian service denial and Admin login redirects.
Only the Phase 3 fixture now marks its two Admin actors as staff; the operator
still lacks ID permissions and must receive 403. A separate assertion preserves
the correct 302/service-denial behavior for a non-staff ID-permitted account.
Guardian approval receives only its explicit approval permission, followed by a
fresh User instance to avoid stale permission caches. No production authorization
or shared operations fixture is weakened. This repair still needs a fresh run;
the old report is not evidence that repaired identification tests pass.

Those are expected counts, **not a claim of execution**. Python remains inaccessible
to the Codex tool process. A fresh local report must show actual execution before
either phase is signed off. No unrelated frontend/media tests run in this mode.

## One command: validate, then activate the real local development preview

From the repository root in your working PowerShell:

```powershell
.\scripts\complete-local-identification.ps1
```

Optional: append `-PythonExe 'C:\path\to\your\existing\venv\Scripts\python.exe'`.
This installs only a missing `qrcode>=8.0,<9` dependency into the selected existing
virtual environment, then runs the complete focused suite in a new uniquely named
local test database. It refuses a system-wide package installation. Test databases
are retained and existing `test_dawana_dev` is not changed. New isolated test data
may be flushed by Django's test framework. Reports are in ignored `validation-results/`.

If tests are incomplete or fail, startup/migrations do **not** proceed.
After successful validation, the normal startup requires database **dawana_dev**,
loopback host and your exact name confirmation. It creates and verifies a custom
PostgreSQL 17 archive before applying any pending local migrations. Archives are
nonempty and checked by header, TOC and full pg_restore read; no restore rehearsal
is claimed. Any failure blocks migration. It never drops/recreates the application DB.
It then checks Admin registrations and starts Django and Vite on loopback.

Migrations added for these phases:

- `0022_housing_guardians_queue`: housing relationships, queue and policy fields.
- `0023_digital_id_cards`: optional private portrait and encrypted/digested QR fields
  on existing enrollment/ID issue records. Existing rows/IDs are retained; no legacy
  credentials are silently generated. Legacy QR activation requires an explicit staff
  Issue operation and current eligibility.

These have **not** been applied to dawana_dev by Codex. The previous log only proves
0022 applied successfully to its isolated test database. 0023 runtime migration parity
and local Admin access remain to be established by the command above.

Do not activate automatic housing until actual house inventory and supervisor approval
are confirmed. See [HOUSING_LOCAL.md](HOUSING_LOCAL.md). The identification setup does
not run the housing worker or create real houses.

## One command: exercise real functionality with isolated synthetic data instead

If real eligible records are not available, use this alternative (not concurrently
with the normal preview):

```powershell
.\scripts\complete-local-identification.ps1 -IdDemo
```

It performs the same focused validation, then creates a **new**, random
`dawana_ids_demo_<uuid>` PostgreSQL database. Only that new database is migrated and
seeded. It cannot seed dawana_dev, a nonempty database, a remote database or production
settings. No real registration/payment records are changed. No database is deleted.

Choose a demo Admin password in the hidden console prompt (minimum 12 characters).
Sign in locally with username **local-id-demo** and that password. Passwords are
hashed in the isolated database, never printed or written to manifest/log files.
The demo Admin header and every card explicitly say SYNTHETIC DEMO.

The demo creates:

- A synthetic female guardian and male child with separately generated participant
  numbers/cards and an explicitly approved synthetic relationship.
- One clearly named synthetic female demonstration house and a safe manual group
  assignment, demonstrating actual house display without inventing operational inventory.
- A synthetic male participant whose active card shows **Housing assignment pending**.
- Verified-looking **synthetic** settlement evidence only inside this isolated demo DB,
  processed through the normal eligibility and ID services. No Paystack request occurs.
- No fabricated participant photographs. You can inspect missing-photo behavior or
  upload an approved local demonstration portrait through Admin.

The normal business services, views, templates and QR verification are used, not mock
screens. Automatic housing stays disabled; this single demonstration house does not
meet the real inventory gate. Its generated manifest and exact card URLs are retained
under ignored `.local-preview/`. Portrait files are isolated there too. Prior demo
databases/manifests and all recovery backups are preserved.

Only one backend may use port 8000 at a time. The startup refuses occupied ports and
never kills servers. Switching between normal and demo previews requires stopping
the processes you started first; `.local-preview/servers.json` records their launcher
PIDs/log paths. Account for Django's reloader child; do not terminate unrelated processes.

## Browser URLs and actual workflow

| Feature | URL |
|---|---|
| Frontend | http://127.0.0.1:5173/ |
| Existing DIC showcase | http://127.0.0.1:5173/dic |
| Django Admin | http://127.0.0.1:8000/admin/ |
| Participant directory | http://127.0.0.1:8000/admin/dic/campenrollment/ |
| ID issue/revocation history | http://127.0.0.1:8000/admin/dic/digitalidissue/ |
| Guardian controls | http://127.0.0.1:8000/admin/dic/guardianrelationship/ |
| Queue controls | http://127.0.0.1:8000/admin/dic/housingjob/ |
| QR verification page | http://127.0.0.1:8000/api/v1/dic/ids/verify/ |
| Individual card | http://127.0.0.1:8000/api/v1/dic/ids/cards/ENROLLMENT_UUID/ |

The demo startup prints exact individual card URLs, with real generated enrollment
UUIDs. In either preview, the directory's **View / print** link opens the actual card.
**Download HTML** provides a self-contained card with embedded portrait/QR images.
**Print / save PDF** uses the browser dialog; choose A4 and 100% scale. The print sheet
uses two 86mm-wide cards per row with automatic page flow. Screens use responsive
grids and natural document scrolling; no fixed-height shell or scroll lock is added.

For real existing registrations, open **Registration order items** at
http://127.0.0.1:8000/admin/dic/registrationorderitem/ and select up to 25 items, then
**Prepare participant identification records**. This reuses `ensure_enrollment`;
it does not issue cards, mutate payments or infer guardianship. Ineligible records
remain visible for authorized review and cannot receive active cards.

In the participant directory:

1. Review participant number, name, edition, age band, verified-payment eligibility,
   housing/pending status, approved guardian, ID/QR status and verification history.
2. Use **Issue / replace / revoke**; reasons are required for replacement/revocation.
3. Open **View / print** and click **Verify this ID** to exercise the real QR destination
   without a camera. A phone camera can scan the printed QR when the verification
   server is reachable. Loopback links in a local demo work on this computer; they
   are not reachable from a separate phone. Use browser responsive mode for mobile
   layout review locally. Do not expose the development server publicly to work around it.
4. To print several, select up to 25 records and use **Issue eligible selected IDs
   and open print sheet**, or **Print / download selected active cards**.
5. Reissue a card, then verify the old QR: it must fail with the same generic response
   as an unknown token. The new QR must succeed. Participant numbers remain unchanged.

ID viewing requires active staff with `dic.can_view_dic_ids`. Issuance, portrait
updates, replacement and revocation also require `dic.can_manage_dic_ids`. Preparing
records from registration items additionally needs view permission for those items.
No permissions are granted automatically to real accounts. An existing local superuser
or the isolated demo superuser can inspect all features. Existing source/restriction
review remains governed by its existing dedicated permissions.

Foreground alternatives, only after the corresponding successful preparation and
with the background preview stopped:

```powershell
# Backend, normal dawana_dev preview:
.\backend\.venv\Scripts\python.exe -B scripts\local_preview.py serve
# OR backend, previously prepared isolated demo:
.\backend\.venv\Scripts\python.exe -B scripts\id_demo.py serve
```

In a second PowerShell terminal at the repository root:

```powershell
$env:DJANGO_API_PROXY_TARGET = 'http://127.0.0.1:8000'
$env:VITE_API_BASE_URL = '/api/v1'
npm.cmd --prefix .\dawana-platform run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## Security and scope

QRs carry random 256-bit URL-safe tokens, not names, DOBs, phones, addresses, guardian
details, payment data or house assignments. Indexed SHA-256 digests support lookup;
the random token is encrypted at rest using a domain-separated key derived from the
existing Django SECRET_KEY so authorized staff can reprint cards. No new credential
environment variable is needed. Keep SECRET_KEY stable; rotation may require authorized
QR replacements for reprinting. Never publish database dumps or downloaded cards.

The QR token is in a URL **fragment**, not a server query/path. The verification page
clears it from the address bar and submits it in a CSRF-protected POST. Responses are
no-store, no-referrer and frame-protected. Public responses contain only valid status
and edition. Authorized staff see name, participant number and current safe housing;
no contacts, DOB or payment details. Scans are rate-limited and audited without tokens
or contact data. The local cache rate limit is per process; distributed deployment
rate limits need review when hosting is approved, not new paid infrastructure now.

Revocation, expiry and changed eligibility are checked on every verification/card
request. IDs remain usable with pending housing and without portraits. Portraits use
existing private normalized image storage; there is no public photo URL or R2 launch
dependency in local mode. A missing local portrait file does not make a card unusable.
Reprint after a house change; QR staff verification reads the current assignment,
whereas an already printed house label is necessarily a snapshot.

Children have their own enrollment number/card; approved Phase 2 guardian relations
appear only to authorized staff. No child login is assumed or created. No new Phase 4
portal flows, examinations, attendance state or Phase 8 check-in are implemented.
Printed identification is fully supported without participant smartphone access.

## Files for this phase

Created: `backend/dic/identity_tokens.py`, `identity_cards.py`, `identity_views.py`,
`identity_admin.py`, `identity_demo_data.py`, `test_identity_cards.py`,
`migrations/0023_digital_id_cards.py`, `templates/dic/identity_cards.html`,
`templates/dic/identity_verify.html`, `templates/admin/dic/identity_manage.html`,
`scripts/id_demo.py`, `complete-local-identification.ps1`, and this runbook.

Extended: `backend/dic/models.py`, `admin.py`, `urls.py`, `participant_services.py`
(reject unknown ID operations), `backend/requirements.txt`,
`backend/dic/test_housing_phase2.py` (test the guardian-group prohibition with a fully
authorized reserve), `scripts/HOUSING_LOCAL.md` (correct the old validation status),
`scripts/validate_dic_backend.py`, `validate-dic-backend.ps1`,
`start-local-preview.ps1`, `local_preview.py`.

Registration/Paystack implementations, Phase 1 showcase, Media, pricing, existing
backups and stash are unchanged in this phase. No system-wide installation or new
development workspace is used. The test/demo databases are explicitly isolated data
environments authorized for validation, not additional source repositories.

## Status and Phase 4 readiness

Code and focused tests are prepared. PowerShell syntax and whitespace checks passed.
Backend tests, actual database activation and authenticated desktop/mobile browser
checks have **not** been executed by Codex because Python is denied in its process.
Do not treat implementation or discovery as successful runtime validation. Use the
consolidated command and retain its actual counts. Phase 4 should wait for all 60
focused tests, migration parity, local backup/migration checks and a browser review.
Its age-based access rules (0–13 profiles with optional verified guardian viewing,
14–16 optional independent access, 17+ independent access) remain future work;
this phase preserves existing participant/edition identifiers and approved links.
