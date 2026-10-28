# Phase 3 printing cleanup and portal ID access

## Follow-up: three format-related 404s

The retained `20261024T120327Z-5ab86b` report executed all 36 tests: 33 passed,
three failed, no errors/skips. The shared-credential test's default PVC request
passed; its A6 request failed. The guardian A6 request and invalid `format=bulk`
request also failed. URL registration and the UUID helper match the actual route.

Root cause: DRF's default `URL_FORMAT_OVERRIDE='format'` interpreted the physical
format query as a response renderer selector in `APIView.initial()`, before
the portal handler. Its negotiation raises 404 for unrecognized renderers such
as `pvc`, `a6` or `bulk`, so guardian/physical-format validation never ran.

`PortalCardView` now uses a narrowly scoped `CardDownloadNegotiation` with the
renderer query override disabled. Accept-header negotiation remains unchanged.
All other API views retain their default settings. The handler still authorizes
the cookie, booking, enrollment and dependent guardian before validating physical
format: authorized invalid format -> 400; missing portal session -> 403; another
booking's enrollment -> 404, including with an invalid format. No lookup/guardian
checks are bypassed and no credential issuance behavior changes.

The existing tests now explicitly check PVC downloads plus those invalid-format
authorization boundaries, without removing assertions or changing the 36-test
count. The repair has not been executed in Codex: Python remains access-denied.
Run from the repository root:

```powershell
.\scripts\validate-dic-backend.ps1 -IdsOnly
```

Do not restore the preview before a fresh 36/36 result. No existing DB/process
was changed during the repair.

## What existed before this continuation

The participant portal at `/dic/participant/` verifies a **booking reference and
registered primary contact**, using purpose-isolated OTPs and an HttpOnly portal
cookie. It is not an individual age-based participant-login system. The cookie is
scoped to `/api/v1/dic/participant/` and never authenticates staff Admin requests.

Existing GET `/participant/enrollments/<uuid>/id/` returns JSON metadata only:
no QR, embedded private portrait, physical dual-format layout or HTML download.
It checks existing enrollment eligibility and active issue state. The old React
“View / print” action first POSTed the enrollment endpoint when no ID existed;
that explicit legacy endpoint can issue an eligible ID. This continuation does
not change the legacy issuance service or endpoint, but **no new view/download
action calls it**, and no issuance/replacement controls are exposed in the new UI.

There was no guardian-specific portal grant or cross-booking guardian access.
Grouped booking access does not itself establish guardianship. The housing model
only approves dependent relationships for ages 0–5; it is not a general legal or
portal authorization model. No new authentication/guardian-verification system
has been invented here, and no age-based Phase 4 login policy is implemented.

## Implemented

The shared PVC, A6 and batch print template now has a concise heading, physical
format, Print / Save PDF, Download HTML and Return action. Detailed browser and
borderless-printer instructions are in a collapsed **Printing help** disclosure.
Individual/one-page batch previews have no page caption; multi-page batches retain
page numbers. Demo notices are compact. Controls, help and notices are hidden in
print CSS. Synthetic labels on synthetic cards remain, preventing confusion with
real IDs. Physical dimensions, pagination, quiet zones and print rules are unchanged.

The portal now shows **My Digital ID** for an existing active eligible ID. It offers
PVC/A6 view and HTML download links. Missing/revoked/expired IDs stay unavailable;
the portal does not silently issue, activate a legacy QR or replace a credential.
Legacy IDs without QR credentials display an unavailable status and need staff review.

New endpoint, beneath the existing portal-cookie path:

`/api/v1/dic/participant/enrollments/ENROLLMENT_UUID/card/`

- `?format=pvc` (default), `?format=a6`.
- Append `&download=1` for self-contained HTML.
- No bulk, issuance, replacement or revocation controls.
- Uses existing `scoped_enrollment`, booking-grant expiry/revocation, contact match,
  source/eligibility checks and the same `card_context` as staff rendering.
- The staff renderer still requires staff permission. Only the scoped portal
  endpoint calls the internal authorized renderer after its own access checks.
- Reads reuse the same active QR credential; no ID or audit records are written
  by the new download/render path. QR scans retain existing audit behavior.
- Portraits remain embedded from private storage; no unrestricted photo URL.
- Responses are private/no-store, no-referrer and frame-protected.

### Guardian behavior and explicit limitation

A dependent aged 0–5 needs a currently approved relationship, current guardian
eligibility and an eligible guardian enrollment within the **already verified
booking scope**. The child gets its own existing ID; no child login is required.
Unapproved/revoked guardianship, an ineligible guardian, expired portal grant or
revoked booking scope is denied. An approved housing guardian link never expands
the session to another booking, even if both bookings share a contact.

For participants aged 6+, existing verified-booking access is preserved. Do not
describe that as a new independently verified guardian login or legal guardianship.
Cross-booking guardian downloads remain unavailable: there is no existing verified
guardian portal-access grant to reuse. Supporting those would need separately
approved access design; it is not safely inferred from a surname/contact/house link.

## Testing status

User reports all previous 28 identification tests passed before this change.
Current identification suite: **36 tests**, including eight portal/UI regression
tests. Combined housing/ID suite: 78. Tests include actual OTP login, booking and
guardian scoping, staff-session isolation, expired/revoked grants, invalid format,
credential consistency, no rendering writes, missing/revoked/ineligible cards,
and prevention of cross-booking access. Existing QR security tests remain selected.

This session actually ran:

- `node --test src/services/participantApi.test.js`: **5 passed, 0 failed, 0 skipped**.
- Frontend production build: **PASS**.
- Whitespace and embedded browser-script syntax: **PASS**.
- Backend identification tests: **0 executed** — Python executable access denied
  in Codex's tool session. The new access flows are not runtime-signed-off yet.

Run only the focused identification suite from the original Desktop workspace:

```powershell
.\scripts\validate-dic-backend.ps1 -IdsOnly
```

It uses a new uniquely named isolated local PostgreSQL test database and requires
complete execution. It never modifies dawana_dev, test_dawana_dev or existing demo
databases. Report actual 36-test results from the newly generated JSON; do not
reuse old pass counts. No frontend/media/housing reruns are necessary for this task.

## Browser URLs

- Admin directory: http://127.0.0.1:8000/admin/dic/campenrollment/
- Existing admin PVC/A6 links and batch actions remain in that directory.
- Participant portal: http://127.0.0.1:5173/dic/participant/
- Same-origin portal card endpoint: http://127.0.0.1:5173/api/v1/dic/participant/enrollments/ENROLLMENT_UUID/card/?format=pvc
- A6 download: same endpoint with `?format=a6&download=1`.
- QR verification: http://127.0.0.1:8000/api/v1/dic/ids/verify/

Use a real authorized local booking session. No OTP bypass, secret display, fake
participant insertion or independent child login is added. Local code-delivery
availability remains governed by existing configuration; if disabled, the portal
honestly requests staff assistance. Use the same host for login and downloads.
Do not switch between localhost and 127.0.0.1 when testing scoped cookies.

No server was restarted, restored or terminated during this task. Existing running
Vite/Django reloaders may load edits; verify their ownership/configuration before
any restart. No existing database, QR credential, production settings or migration
was changed. Check browser rendering after backend tests pass; no browser interaction
or physical printing success is claimed from the code/build checks alone.

## Files changed in this task

- `backend/dic/templates/dic/identity_cards.html`
- `backend/dic/identity_views.py`, `participant_api.py`, `urls.py`
- `backend/dic/test_identity_cards.py`
- `dawana-platform/src/pages/ParticipantPortal.jsx`
- `dawana-platform/src/services/participantIdentity.js`, `participantApi.test.js`
- `scripts/PORTAL_ID_ACCESS.md` (this report)

No migrations or new dependencies. Registration, Paystack, housing/guardian rules,
QR issuance/revocation and all pre-existing uncommitted work remain preserved.
