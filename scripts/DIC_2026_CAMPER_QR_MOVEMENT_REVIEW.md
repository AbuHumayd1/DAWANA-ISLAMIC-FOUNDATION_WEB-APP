# DIC 2026 camper management, QR movement and schedule review

26 October 2026. Static inspection and planning only. No runtime/database checks, tests, migrations, credential changes or application implementation performed.

## Current camper management

| Operations route | Implemented functionality |
| --- | --- |
| `/dic/operations/participants` | Searchable, paginated camper directory with name/category/house/payment/date filters. Contact search and fields require contact-information permission. |
| `/dic/operations/participants/<participant-uuid>` | Camper profile, registration references/history, demographic fields, payment indicators and current edition house assignment. |
| `/dic/operations/registrations` and `/<booking-uuid>` | Booking search/detail, participants, registration/payment states and permission-filtered contact/financial information. |
| `/dic/operations/houses` | Existing house/allocation view; authorized housing changes are handled elsewhere in existing housing/Admin workflows. Not a bed-level occupancy or movement ledger. |
| `/dic/operations/participant-ids` | Search by participant number, booking reference or name; view/print IDs, permission-gated enrollment preparation, issue/reissue/revoke and registration-source review. |
| `/dic/operations/id-printing` | Existing controlled ID printing workflow; not a camera scanner. |
| `/dic/operations/check-in` | Search by name/registration/participant number, select edition, see eligibility/house/arrival and explicitly record first camp arrival. |

Records are stored in `Participant` (person), `PrimaryRegistrant` (booking contact), `RegistrationOrder`/`RegistrationOrderItem` (booking and edition-specific participant membership), `PaymentAttempt`/price revisions (payment evidence), `CampEnrollment` (unique participant+edition identity/source and individual participant number), `DigitalIDIssue` (versioned QR credential), `House`/`HouseAllocation` (accommodation assignment), and `CampCheckIn` (first physical arrival). All are in `backend/dic/models.py` or its imported model modules. Enrollment is lazily prepared by an authorized POST; directory/eligibility reads must not manufacture one. Enrollment preparation does not itself verify payment, issue an ID or record arrival.

The authoritative `participant_services.eligibility()` requires a confirmed/paid booking, accepted current price revision, matching successful NGN provider evidence/amount/transaction ID/timestamps and valid payment timing. Unresolved source conflicts, restrictions and reconciliation issues block eligibility. ID issuance and check-in reuse this service. Housing pending does not block otherwise eligible arrival. Older generic Operations `verified_paid` labels use a weaker confirmed/paid/successful-attempt check: do not substitute that display flag for the eligibility service when admitting a camper.

Operations endpoints use the existing Django session, Operations permission and CSRF protection. Campsite/check-in additionally require active staff. Relevant existing permissions are `dic.can_view_dic_operations`, `dic.can_view_dic_contact_information`, `dic.can_view_dic_ids`, `dic.can_manage_dic_ids`, `dic.can_review_dic_enrollment_sources`, `dic.can_check_in_dic_participants`, `dic.can_view_dic_audit` and report-export permission where applicable. ID verification's richer staff response requires active staff plus ID-view permission; it does not itself require Operations permission. No grants were inspected or changed.

## What an existing smartphone QR scan actually does

There is **no in-app camera-scanning interface** found in the frontend or verification template. No `getUserMedia`, BarcodeDetector or QR-scanner library is wired into these flows. A phone's normal camera/QR application can decode the printed/digital card and open its URL, subject to device capability and network reachability.

1. `identity_cards.card_context()` reads the active eligible `DigitalIDIssue`, decrypts its random QR token and generates an SVG QR. Its payload is an absolute URL of the form `https://<issued-origin>/api/v1/dic/ids/verify/#<43-character-random-token>`. It does not encode name, phone, payment data or a numeric participant ID. The server stores a token digest and encrypted secret linked through the ID issue to the enrollment, participant and edition.
2. The native phone camera opens that URL. The browser GETs `/api/v1/dic/ids/verify/`; URL fragments are not sent in that HTTP request. Django renders `templates/dic/identity_verify.html` and establishes CSRF support.
3. The page reads the fragment, removes it from the displayed URL/history entry, and automatically POSTs JSON `{ "token": "..." }` back to that same endpoint, with same-origin cookies and its CSRF token. A manual token field is also provided. This is a web verification form, not camera capture.
4. `identity_views.verify_view()` applies a 30/minute per-address throttle, limits request body size and calls `identity_cards.verify()`. It checks token shape/digest, revocation, expiry and current eligibility. Invalid/ineligible/revoked/expired tokens yield generic 404 JSON; throttling yields 429; successful verification yields 200 JSON. CSRF middleware protects the POST.
5. A public bearer of a valid QR receives only validity and edition name. An authenticated active ID-view staff member additionally receives camper name, participant number and house/accommodation label. The response does **not** provide the participant UUID/edition primary key needed by check-in.
6. Success saves a `DICAdminAuditEvent`: action `participant_qr_verified`, target type `CampEnrollment`, target ID enrollment UUID, details including issue UUID and whether the response was staff-authorized; `created_at` is the server timestamp. The actor is the authenticated authorized ID-view staff user, otherwise null. The enrollment provides the participant/edition association. Repeated valid verification creates repeated audit events; invalid codes do not create this success event. This is identity verification, not a presence/movement record.

The page's current **Staff sign in** link goes to `/admin/login/`, not Operations. Both use Django sessions, but the workflow does not carry the scan securely through an Operations login. The token has already been removed from the address bar, so simply navigating away and back does not reliably resume verification; staff should sign in on the same origin first and rescan. This is a usability/integration gap, not evidence of a second authentication backend.

## How physical arrival is actually saved

Today, after identifying a camper, staff must separately open `/dic/operations/check-in`, select the edition, search and choose **Check In**. `CampCheckIn.jsx` sends:

```text
POST /api/v1/dic/operations/check-in/?edition=<edition-primary-key>
JSON: { "participant_id": "<participant-uuid>" }
Existing Operations session cookie + X-CSRFToken
```

`CampCheckInView.post()` requires active authorized check-in staff, available storage, explicit edition and a valid participant UUID. `check_in_participant()` locks source orders/participant, verifies registration within that edition and rechecks authoritative eligibility. It creates `CampCheckIn(participant, edition, checked_in_at=server time, checked_in_by=staff)` and an audit event `participant_checked_in`. The model has no event-type field: its record means initial arrival only. A unique participant+edition constraint and idempotent service preserve the original staff/time on repeat requests: first save returns 201/created=true, repeat returns 200/created=false.

**There is currently no automatic QR-to-arrival handoff.** The token-verification POST and the participant-UUID check-in POST are different operations. Presenting or scanning a QR never calls the check-in service automatically.

## Missing movement capabilities

- No exit, return, temporary leave, final departure, guardian collection or movement-correction endpoint/model/UI was found.
- No current inside/outside state or authorized camper movement-history timeline exists. Check-in shows the original arrival and staff/time; Camper Portal receives a checked-in boolean; the restricted Activity Log can show audit events but is not a movement ledger.
- No daily/session attendance capture is provided by `CampCheckIn`; do not use repeated arrivals or QR-verification audit rows as daily attendance.
- No camera permission/error/rear-camera/duplicate-detection loop, offline scanning or retry queue exists in the reviewed scanning path.

## Smallest integration plan — proposed, not implemented

1. Keep camper search, profiles, ID management and Camp Check-in in Operations. Add a **Scan ID** mode within Camp Check-in, with native-camera support where available and a tested fallback/paste/search path. Provide clear camera/network failures and explicit stop-camera behavior. Production phone camera capture needs a supported secure origin; local `127.0.0.1` QR URLs are not reachable from another phone. Confirm a reachable trusted hostname and same-origin session/proxy behavior before issuing cards; do not replace credentials or regenerate IDs during this review.
2. Add a narrow authenticated token-resolution/preview integration that reuses current token/expiry/revocation/eligibility logic but returns a minimal authorized camper identity plus participant UUID and edition ID. Do not weaken the public verifier or expose UUID/contact fields publicly. Require active Operations staff and explicit ID-view authority for scanning identity; require the existing check-in permission separately for recording arrival. Backend selected-edition checks must reject mismatch. Do not search every camper client-side to map tokens/names.
3. Scan → preview identity/photo if already authorized, edition, current arrival and eligibility → explicit **Record camp arrival** confirmation → reuse `check_in_participant()` and existing `CampCheckIn`. Prefer resolving/revalidating the scanned credential again on confirmation before invoking that service, so expiry/revocation/edition context cannot be bypassed with stale browser state. Preserve the existing manual check-in path and its permissions. No new attendance/enrollment/check-in ledger is needed for this stage. Repeated camera detections must not cause automatic POST writes.
4. Route staff sign-in through existing Operations authentication on the same origin, preserving scan context only transiently and securely or asking for a rescan. Never put QR secrets in query parameters, analytics, logs or persistent browser storage. Do not create a separate Security login/dashboard.
5. Specify departures/returns separately before any schema work. An eventual edition-scoped append-only movement history should reference existing participant/enrollment identities, record event type, server time and responsible staff, support idempotent requests and explicit corrections, and validate permitted state transitions. Approve distinct movement-view and departure/return-recording permissions rather than granting them to all Operations users. **Departure must require explicit confirmation**, reason/destination and appropriate collection/guardian evidence for minors; a valid QR, paid registration or house assignment does not authorize collection. Existing `GuardianRelationship` records are useful context, not proof of collection authority by themselves. Do not repurpose first arrival or generic audit rows as the operational movement ledger. New models/migrations require separate approval.

## Proposed Camper Portal schedule feature — future work only

No structured camper timetable, duty roster, meal timetable or schedule publishing API was found. `CampEdition` already provides dates/venue and general information; `CampActivity` is moderated programme-highlight content, without scheduled start/end times, house duties or menus. `CamperExperience.jsx` currently shows camp essentials and links to public highlights. Public Programs/Events schedule strings are presentation content, not an editable edition programme.

Reuse edition/house identities, Camper Portal booking scope, Operations sessions, moderated draft/publish patterns in `showcase_models.py`/`showcase_admin.py`, and the existing report-generation approach in `operations_exports.py`. Reuse patterns rather than treating existing highlights or scoring activity definitions as timetable records.

Requirements for subsequent design:

- Daily activities and full programme, edition-scoped with actual dates/start/end times, venue, ordering, cancellations and Africa/Lagos display. Do not seed invented activities.
- House cleaning and plate-washing duties by date/time and assigned house, using current house identity; keep personal sensitive data out of public/shared downloads.
- Daily food timetable and upcoming meals visible ahead of serving time, with organizer-approved menus and clear changes; do not infer meals from scoring/cleanliness tasks.
- Camper Portal “Today”, upcoming meals, full programme and relevant house duties, with only published content visible and clear empty/last-updated states.
- PDF and Word downloads generated from the **same published edition revision** as the screen, with edition/date/version and audience-appropriate privacy. Existing report permissions are not automatically schedule publishing permissions.
- Authorized organizer editing, separate explicit publishing authority, draft preview, validation, revision/audit history and publish/unpublish behavior. Existing Operations authentication should be reused; campers/guardians remain under their existing booking scope. Editing/publishing permissions must be approved, not automatically granted.
- Decide programme ownership, revision retention, audience, timing rules, offline/download freshness and any required future schema separately. No schedule code/model/migration implemented here.

## Relevant source paths and evidence limits

- `backend/dic/models.py`: identities, booking/payment, housing, ID issue, audit and initial-arrival models.
- `backend/dic/participant_services.py`: eligibility, lazy enrollment creation and ID lifecycle.
- `backend/dic/identity_cards.py`, `identity_tokens.py`, `identity_views.py`, `templates/dic/identity_verify.html`: QR issuance, verification and automatic token POST.
- `backend/dic/checkin_api.py`, `checkin_services.py`, `campsite_api.py`: arrival endpoint, permissions, locks, idempotence and storage guard.
- `backend/dic/operations_api.py`, `participant_api.py`, `portal_dashboard.py`, `urls.py`: staff directories/profiles, scoped camper projections and routes.
- `dawana-platform/src/pages/Operations.jsx`, `StaffParticipantIDs.jsx`, `CampCheckIn.jsx`, `ParticipantPortal.jsx`, `components/dic/CamperExperience.jsx`: existing staff/camper interfaces.
- `backend/dic/showcase_models.py`, `showcase_admin.py`, `operations_exports.py`: reusable content-publication/report patterns.

Safety findings are code-inspection findings, not claims of live browser acceptance. Public QR verification intentionally discloses minimal validity/edition and writes a success audit; richer information is permission-protected. Shared staff accounts or public scans cannot establish an individual officer's movement attestation. HTTP verification/search/download paths can write audit events, so no live requests were made during this read-only review. The earlier local Finance routing issue does not certify or invalidate these source-level QR/check-in findings; deployed route/service availability still needs targeted verification before use.

Only this review document was added. No application changes, database writes, migrations, accounts, permission grants, credentials, schedule work or standalone Security Dashboard were introduced.
