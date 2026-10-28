# DIC 2026 Phase 1: QR scanner and camper movements

Runtime verification follow-up and guarded disposable provisioning commands: [DIC_2026_MOVEMENT_RUNTIME_VERIFICATION.md](DIC_2026_MOVEMENT_RUNTIME_VERIFICATION.md). The follow-up supersedes this handover's requirement to arrange provisioning manually; no provisioning or development migration has been executed by Codex.

26 October 2026. Implemented for isolated validation; **not operationally accepted**. No migration or database write was executed during implementation. Smartphone camera operation has not been tested in a real browser.

## Route and operator use

Existing Operations login: `/dic/operations`. Existing workspace: `/dic/operations/check-in`. Select the edition and choose **Scan ID**. Camera permission is requested only by **Start camera** (or an explicit camera-selection action). The frame uses the rear-facing preference; permitted camera devices are listed after permission is obtained. Detection uses the browser's `BarcodeDetector` only when `qr_code` support is reported. No decoder dependency was installed. Unsupported readers, insecure contexts, denied permission and camera failures show guidance to paste the existing QR URL/token or use manual camper lookup.

An accepted scan stops capture and POSTs the token in the request body for a minimal preview. It never navigates to the QR's embedded origin. No token is put into operational URLs, query parameters, console output, localStorage or an audit event. Pasted values are cleared; the accepted token remains transiently in component memory until close/new scan/save/unmount. Camera tracks stop on explicit stop/close, component removal (including edition/search/page changes), page hiding and disposal of a late camera-permission response. Repeated detections cannot automatically record movement.

Preview first, then explicitly confirm **initial check-in**, **departure** or **return**. A saved result shows the server timestamp. Manual check-in also asks for initial-arrival confirmation. Search results continue to show the original check-in, now explicitly labelled initial arrival only. Staff with movement-view authority can choose **Movement history / record** on a searched camper, without requiring a QR scan. That authorized manual path can record a physical return even if the camper's old QR has since become ineligible; it must not create an entry for a person unregistered in the edition.

The public identity verification page remains verification only and still exposes only its pre-existing public response. Its staff link now points to `/dic/operations`, with instructions to sign in and rescan. Local phone use requires a reachable trusted HTTPS origin, correctly proxied Operations sessions and appropriately issued QR origins; another phone cannot access a server through the computer's `127.0.0.1`. No host, credential or environment file was changed.

## Backend API

All new endpoints reuse `OperationsBaseView`: Django session authentication, Operations permission, CSRF on POST and no-store response handling. They additionally require active staff. Explicit edition IDs are mandatory; no write silently selects the current edition.

| Endpoint | Request and behavior |
| --- | --- |
| `POST /api/v1/dic/operations/scan/?edition=<id>` | JSON `action=preview`, `token`. ID-view plus check-in or movement-view authority required. Checks digest, active/nonexpired issue, selected edition and authoritative registration eligibility. Returns name, participant number/UUID, edition and original arrival; presence/version/history are included only with movement-view permission. Preview writes no scan audit or movement. |
| Same scan endpoint | `action=arrive`, token, `confirmed=true`: revalidates the credential after taking existing order/participant locks, then calls existing `check_in_participant()`. Requires check-in permission. 201 first arrival; 200 duplicate with original staff/time. No second arrival model. |
| Same scan endpoint | `action=departure|return`, token, `confirmed=true`, UUID `request_id`, integer `expected_version`, optional `reason`; departures also require `authorization_checked=true` and `authorization_reference`. Credential is revalidated under the participant lock. 201 new event; 200 exact replay. |
| `GET /api/v1/dic/operations/movements/?edition=<id>&participant_id=<uuid>` | Requires movement-view permission. Returns derived presence, version, original arrival and ordered event history. Camper must be registered in the selected edition. |
| `POST /api/v1/dic/operations/movements/?edition=<id>` | Manual alternative with `participant_id` instead of token and the same movement fields/checks. Requires movement-view and movement-recording authority; departure also requires release authority. |

Invalid tokens return a generic 400 without reflecting the token; anonymous/unauthorized actions return 403 under the existing SessionAuthentication configuration. Unsupported actions, missing confirmation, foreign-edition identities, stale versions and invalid transitions return 400. Missing movement storage returns 503, never a fabricated presence state. Initial arrival itself does not depend on movement storage for check-in-only scanner operators; accounts entitled to movement previews fail closed until that storage exists.

The frontend retains the exact request UUID and payload after an uncertain movement response. Input fields are locked for that retry; close/refresh history before choosing a different action. A stale preview is rejected by the backend. No automatic blind write retries or offline movement queue were added.

## Model and authorization

New supporting app: `dic_movement`. New model: `Movement`, linked to existing `Participant`, `CampEdition` and staff user, with departure/return type, server `recorded_at`, optional reason, authorization reference, per-camper sequence and request UUID. The service is append-only; instance update/delete is refused, no CRUD Admin registration or update/delete API is exposed. Trusted direct database/ORM administrators remain outside these API guarantees.

Presence derives from original `CampCheckIn` plus ordered movements:

```text
No initial arrival → not_arrived
Initial arrival → inside
inside → departure → outside
outside → return → inside
```

Return without departure, repeat departure and movement before arrival are rejected. Initial arrival remains historical and is never rewritten as a return. Order/participant locks serialize identity/eligibility checks with existing issuance/arrival operations; edition+request and edition+participant+sequence constraints prevent duplicate ledger entries. Exact replay checks staff, identity, action, reason and authorization reference. New events write `camper_departure`/`camper_return` audit events within the same transaction. Rejected/replayed requests create no extra movement/audit event. A QR scan alone does not attest physical presence.

Required permissions, never automatically granted:

- Baseline: active staff and `dic.can_view_dic_operations`.
- QR preview: `dic.can_view_dic_ids` plus check-in or movement-view authority.
- Initial arrival: existing `dic.can_check_in_dic_participants`; QR arrival additionally needs ID view.
- Presence/history: new `dic_movement.can_view_movements`.
- Departure/return: new `dic_movement.can_record_movements` **and** movement view.
- Every departure: additionally new `dic_movement.can_authorize_departure`, an explicit checked release-authorization attestation and a nonempty reference.

The general Operations Activity Log excludes departure/return audit rows unless its viewer also has movement-view permission, preventing that feed from bypassing the domain history restriction. Direct database administrators remain a privileged trust boundary.

The conservative Phase 1 departure policy applies the extra authorization gate to **all** campers; no unapproved age-dependent exemption was invented. Ordinary scanner/check-in operators cannot release campers. The authorized recorder attests that externally approved release/collection evidence was checked. This is **not a new two-officer approval workflow or automatic guardian-document validation**; operational owners must approve the external authorization procedure, especially for minors, before use. No permissions, named officers, accounts, approval references or real movements were created.

No movement-edit/correction endpoint was requested or added. If an event is wrong, retain it and escalate; do not directly rewrite history. A controlled correction policy must be agreed before operational rollout.

## Migration graph and actual state

New prepared migration: `dic_movement.0001_initial`.

```python
dependencies = [
    ('dic', '0026_house_score_transaction'),
    migrations.swappable_dependency(settings.AUTH_USER_MODEL),
]
```

Static dependency-file traversal executed with Node reached dic 0001–0026, accounts initial, auth through 0012, contenttypes prerequisites and the new movement initial migration. It excluded `dic.0027_feedback_welfare`. The migration creates only the new movement table/constraints/permission definitions; no RunPython, data seeding or historical migration edit. It is a supporting-app sibling of Finance/scoring, not dic 0028 descending from postponed 0027.

**Actual migration status: prepared, not applied anywhere by this task.** No disposable database was provisioned. The previously confirmed development migration state was not re-read. Runtime Django graph/model parity and schema/constraint tests are still required; the static traversal is not a Django MigrationExecutor pass.

## Executed checks versus prepared tests

Executed from `dawana-platform`:

```text
node --test src/services/checkIn.test.js src/services/camperMovement.test.js
11 passed, 0 failed, 0 skipped

oxlint src/pages/CampCheckIn.jsx src/components/operations/CamperScanner.jsx src/services/camperMovement.js src/services/camperMovement.test.js
Passed with no warnings after correcting ref access in rendering.

npm.cmd run build
Passed; existing bundle-size warning (approximately 606 kB minified JS).
```

These tests cover existing check-in presentation, QR parsing/rejection without secret reflection, edition URL validation, track-stop cleanup, scanner initial stopped/manual state and permission-gated manual history entry. SSR/unit checks do not exercise real video capture/detection or authenticated HTTP mutations.

Prepared backend tests:

- `dic_movement.tests.MovementPolicyTests`: **16 database-free tests**, including API denials, token shape/digest/edition/expiry query conditions, eligibility, separate permissions, departure attestation, transition matrix, arrival-service reuse, saved original time/duplicate status, audit attribution/feed privacy, stale versions and exact request replay.
- `dic_movement.test_integration.MovementIntegrationTests`: **five PostgreSQL tests**, for persisted scan arrival/duplicate audit, departure/return/replay/presence, invalid/stale transitions, edition isolation/unauthorized staff and revoked tokens. Synthetic source/ID fixtures use mocked settlement eligibility to isolate movement/storage invariants; these tests do not replace real payment-evidence acceptance or a complete live HTTP role/CSRF/concurrency matrix.

**Neither backend suite nor Django preflight executed.** The configured virtual environment cannot access its Python313 base executable. Both the interpreter probe and `validate_dic_movement.py preflight` failed before Python started. No backend syntax/runtime pass is claimed.

## Safe local validation commands

In normal VS Code PowerShell at repository root, with the previously approved working interpreter:

```powershell
$movementPython = (Resolve-Path -LiteralPath '.\backend\.venv\Scripts\python.exe').Path
& $movementPython -B .\scripts\validate_dic_movement.py preflight
if ($LASTEXITCODE -ne 0) { throw 'Stop: graph/model/system checks did not pass.' }
& $movementPython -B .\scripts\validate_dic_movement.py policy
if ($LASTEXITCODE -ne 0) { throw 'Stop: database-free movement policy tests did not pass.' }
```

The runner reuses the existing Finance helper's synthetic development configuration and external-side-effect/database-connection guards. It does not change `.env`, create a database or invoke migrations. Preflight uses `MigrationLoader(None)` and model-state comparison; policy tests forbid database connections.

Integration requires a **separately approved, provisioned disposable PostgreSQL facility** named `test_dic_movement_<14-digit UTC timestamp>_<8 lowercase hex>`, with exactly the reviewed movement target prerequisites applied and a database comment marker `dawana-movement-validation:<32 lowercase hex>`. The marker must be independently recorded by the provisioner and ownership must match the configured local role. Review the runtime plan before provisioning: target movement 0001 plus prerequisites only, never unrestricted migrate or dic 0027. This task provides no development migration action and has not executed provisioning.

Once the approved disposable schema/marker exist:

```powershell
# Set these to the independently approved disposable database and marker.
$movementDatabase = Read-Host 'Approved disposable movement database name'
$movementMarker = Read-Host 'Independent database-comment marker'
& $movementPython -B .\scripts\validate_dic_movement.py integration --database $movementDatabase --marker $movementMarker
if ($LASTEXITCODE -ne 0) { throw 'Stop and retain disposable evidence; do not retry against development.' }
```

The integration runner refuses other name formats, non-loopback/non-PostgreSQL configuration, wrong ownership/marker, unexpected migration sets and postponed welfare tables. It uses unittest/Django TestCase transaction rollbacks on the already provisioned database; it does not run DiscoverRunner, create/flush/drop a database or migrate. Do not replace these commands with `manage.py test`, which can migrate unrelated app leaves including 0027. Production permission assignment and controlled development schema application remain separate decisions after isolated validation.

## Real-browser acceptance still required

1. On a real supported smartphone over the approved HTTPS origin, verify no permission prompt before Start, rear-camera decoding, camera switching, frame visibility, denied permission, unavailable device and unsupported-reader fallback. Verify tracks stop on close, route/edition/search changes, page hiding and a late permission response.
2. Use an isolated valid card, wrong-edition card, invalid/revoked/expired card and repeated frames. Confirm no raw token in page URLs, console, audit records or analytics. Preview must not create arrival/movement records or expose contact/financial details.
3. Confirm initial arrival and duplicate attempts: original saved server time/staff preserved, one CampCheckIn/audit. Check the ordinary public verifier still performs identity verification only and staff link uses Operations.
4. With separate isolated roles, test direct API requests as anonymous, nonstaff, no Operations, ID-only, check-in-only, movement-view-only, record-without-view and release-authorized staff. Test CSRF failure separately from permission failure. No role gets additional permissions implicitly.
5. Explicit departure with missing release authority, missing checkbox/reference, stale version, two concurrent submissions or no arrival must fail. Valid departure shows outside; return without departure fails; valid return shows inside. Exact retry must not duplicate either ledger or audit. Verify history is absent without view authority.
6. Simulate connection loss after a write: exact retry returns original saved outcome; close/refresh and inspect state before another action. Confirm staff can use authorized manual history/return when a QR is no longer usable. All synthetic writes/download audit checks belong in isolation, never `dawana_dev`.
7. Confirm local current-source API routes are actually served; the previously reported source/runtime mismatch must be resolved before acceptance. Desktop/mobile scrolling and Operations hamburger must remain usable around the scanner.

## Exact files changed in this task

New backend app files:

- `backend/dic_movement/__init__.py`
- `backend/dic_movement/apps.py`
- `backend/dic_movement/models.py`
- `backend/dic_movement/services.py`
- `backend/dic_movement/api.py`
- `backend/dic_movement/migrations/__init__.py`
- `backend/dic_movement/migrations/0001_initial.py`
- `backend/dic_movement/tests.py`
- `backend/dic_movement/test_integration.py`

Backend integration:

- `backend/config/settings/base.py` — register supporting app.
- `backend/dic/urls.py` — two Operations endpoints.
- `backend/dic/operations_api.py` — expose three explicit capability flags in existing session metadata; filter movement audits without movement-view authority.
- `backend/dic/templates/dic/identity_verify.html` — Operations staff link and rescan guidance.

Frontend:

- `dawana-platform/src/pages/CampCheckIn.jsx` — scan/manual movement entry, confirmation and saved-status integration.
- `dawana-platform/src/components/operations/CamperScanner.jsx` — camera, transient-token preview, confirmation, history and exact-request retry UI.
- `dawana-platform/src/components/operations/CamperScanner.css` — responsive frame/forms/focus styling.
- `dawana-platform/src/services/camperMovement.js` — QR parsing, paths and camera cleanup.
- `dawana-platform/src/services/camperMovement.test.js` — focused utility/presentation checks.

Validation/documentation:

- `scripts/validate_dic_movement.py` — guarded preflight/policy and existing-disposable integration runner; no schema/provisioning action.
- `scripts/DIC_2026_QR_MOVEMENT_PHASE1.md` — this handover.

Pre-existing workspace changes were retained. Historical migrations, Finance logic, credentials and staff grants were not changed. No separate Security Dashboard, schedule feature or later phase was started.

**Remaining blockers:** accessible Python and passing runtime graph/parity/policy checks; approved disposable provisioning and passing integration/HTTP concurrency checks; reviewed unapplied movement schema; approved named permission assignments/external release procedure/correction policy; resolved current-source routing; real supported-phone browser acceptance. This implementation is not ready for operational or production movement recording until those gates pass.
