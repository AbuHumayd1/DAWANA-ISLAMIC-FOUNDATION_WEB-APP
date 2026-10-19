# Milestone 1L-A implementation report

19 October 2026. Baseline: branch `main`, approved checkpoint `fb24dfa`. The existing untracked architecture, editor settings, Git snapshots and acceptance artifacts were preserved. No commit, push or deployment was performed.

## Delivery and remaining dependencies

Participant portal, isolated OTP/session backend, per-participant enrollment/ID lifecycle, print template and staff ID tools are implemented. **Operational release is not accepted yet:** no delivery channel is currently configured, the verified original logo asset remains unavailable, and browser/print-layout acceptance has not been performed. The interface reports unavailable delivery honestly and does not expose a development OTP fallback.

No initial arrival/check-in, departure/return, movement ledger, guardian/collector authority, safety incidents, activity attendance, QR, scanning or camera infrastructure was added. No permanent parent passwords, child accounts, production users, live payments or fabricated operational registrations were created.

## Data model and migration

Added **`backend/dic/migrations/0014_participant_portal_and_ids.py`**, depending on existing 0013. It creates:

- `CampEnrollment`: existing participant UUID, edition, selected order item, immutable readable number, source-review fingerprint, short ID restriction and creation time. Unique participant/edition pair and globally unique number.
- `ParticipantPortalChallenge`: booking-scoped OTP evidence, encrypted delivery payload, browser-binding digest, attempt count, delivery/expiry/consumption timestamps. It is separate from recovery challenges, so neither purpose can authenticate through the other endpoint.
- `ParticipantPortalGrant`: digest-only opaque credential, verified-contact digest/channel, expiry and revocation.
- `ParticipantPortalScope`: explicit grant/order link with scope revocation. No guardian, collector or staff authority.
- `DigitalIDIssue`: enrollment, monotonically increasing version, expiry, issuing/revoking staff and reason metadata; database uniqueness permits one unrevoked issue and one version per enrollment.

Database triggers enforce enrollment source participant/edition/category consistency, immutable enrollment identity/number, and protection against reassignment of an enrolled source item/order. Services also validate under locks. No payment or registration history is rewritten and no data is automatically backfilled.

Migration SQL was inspected (9,182 characters; no destructive forward DDL/data deletion). **0014 was applied successfully to `dawana_dev`**. Migration history is consistent and drift checks report no changes. Before/after checks confirmed unchanged users and group permission assignments. All enrollment/challenge/grant/ID/order/participant counts in development remain zero.

The schema migration has reverse SQL for the source guards. Reversing after actual portal/ID use would delete new access/ID records and must not be done as routine cleanup; first agree evidence/retention/export requirements. Cleanup commands never delete enrollment, ID or administrative audit history.

## Authentication and booking scope

The portal asks for a **full booking reference and its registered primary contact**. This intentionally limits a grant to one verified booking, including all its individual participants. Matching an email/phone across other orders does not combine them. To access another booking, sign out and verify it separately. Participant contacts are not silently promoted into primary-booking ownership.

The request response is generic for known/unknown valid references and contacts. Normalization, cryptographically random six-digit OTP generation, ten-minute lifetime, five-attempt limit, encrypted delivery and contact/IP throttling reuse the existing recovery security primitives. A 60-second contact cooldown and hourly request limits apply; the client resend action creates a new challenge and invalidates the previous challenge for that browser. Failed verification counters are committed, not rolled back with an exception. Existing recovery challenges/grants and checkout/order-token expiry are unchanged.

Delivery uses the existing configured `send_recovery_code` adapters and provider configuration, through a separate bounded **`send_dic_portal_messages --limit 50`** worker. This preserves recovery authorization semantics and prevents the recovery worker from widening a portal challenge to every matching contact. Unknown, cancelled, revoked-access or changed-contact bookings are suppressed. Delivery payloads are scrubbed after sent/failed/suppressed processing. Codes are not returned or logged.

Successful verification consumes the challenge and rotates a dedicated random 32-byte URL-safe credential. Only its SHA-256 digest is stored. Cookie **`dawana_participant`** is HttpOnly, SameSite=Lax, Secure when production session cookies are Secure, and scoped to **`/api/v1/dic/participant/`**. The separate browser-binding cookie is also HttpOnly. Server-side grants expire after **30 minutes**, are checked on every protected request and can be revoked independently of the cookie. No portal credential is placed in a URL, browser storage, analytics or printable ID.

This is deliberately a separate cookie/grant namespace, not a Django login. It cannot satisfy Operations/Admin authentication and does not overwrite/flush existing Django staff sessions. Participant logout revokes only its grant and cookies. The client clears participant data on session expiry. All mutations require CSRF; requests initialize a fresh masked CSRF token so a staff-login token rotation cannot leave a stale participant token cached. Responses use no-store headers. Session/OTP endpoint throttles supplement the shared database-backed recovery request limits.

Per-request scope checks re-evaluate scope revocation, order cancellation/access revocation and current primary-contact digest. OTP/contact control is booking access only, not guardianship, custody, collection, entry or departure authority. No sensitive child profile fields are serialized by these APIs.

## Eligibility, numbering and ID lifecycle

`participant_services.eligibility` is a shared **read-only** evaluator for participant and staff flows. It requires:

- Matching participant/edition/source and no unresolved multi-source ambiguity or explicit ID restriction.
- Current confirmed/paid order, not cancelled/refunded/pending/failed.
- Successful settlement for that exact order/current accepted price revision, with matching expected/provider amount, NGN currency, provider status, provider transaction identity, verification time and trusted provider-paid time.
- The existing payment service's read-only price-window validation passes, with no relevant unresolved amount-mismatch/reconciliation attempt.

Incomplete legacy settlement evidence returns a review result. Failed or duplicate later attempts alone do not revoke otherwise valid settled eligibility. Lookup never calls Paystack, creates a payment or changes status. Existing registration/settlement/allocation services were not weakened or rewritten.

Numbers use **`DIC-{edition year}-{10 random characters}`**, excluding ambiguous characters. They are backend-generated, database-unique, non-PII identifiers and do not authenticate anything. A participant/edition lock and unique constraint prevent concurrent duplicate enrollment; a bounded collision retry handles the random-number uniqueness edge case. Each sibling in a family order receives its own number.

Initial eligible issuance is explicit POST; GET list/eligibility requests do not create enrollments or issues. Reprinting/reopening a current card does not create another issue or number. Revocation and justified replacement require staff ID-management permission, checked in both API and service. Replacement increments issue version and preserves the enrollment number. A revoked/expired existing issue cannot be silently resurrected through the participant initial-issue endpoint. Current ID eligibility is checked again before returning printable card data; a paper copy cannot be remotely erased.

All source orders are locked before participant/enrollment during issuance, consistent with settlement lock ordering. A changed source set triggers refresh/review. Explicit source resolution requires its own permission/reason, snapshots the set of reviewed source IDs, and revokes the existing ID. Any new source reopens ambiguity. No fuzzy participant merging or payment-history deletion occurs.

Digital cards expose only name, readable number, category, actual edition/dates/venue, an active verified house assignment when available, and issue version. They omit participant UUID from the visible card, DOB, health measurements, address/contact/guardian data, credentials, photos and QR. The print stylesheet suppresses shared navigation, theme/session controls and staff lookup controls, uses an A4 page with a readable individual card, long-name wrapping and break-inside protection. Physical print behavior still needs review.

## Routes and staff capabilities

Frontend:

- **`/dic/participant`**: secure-access form, resend timer, authorized booking/individual summaries, eligibility reasons, issue/view/print ID, refresh, expiry and logout.
- **`/dic/operations/participant-ids`**: permission-gated enrollment number/name/booking lookup, bounded registration candidates, prepare enrollment, live eligibility/current issue, view/print, issue/reissue/revoke, explicit source/restriction review.

The public navigation links to the portal. Both interfaces reuse existing semantic colours, Light/Dark/System, reading sizes, focus/touch patterns and normal document scrolling. No competing theme or fixed viewport shell was introduced.

APIs under **`/api/v1/dic/`**:

| Endpoint | Method |
| --- | --- |
| `participant/auth/csrf/` | GET |
| `participant/auth/options/` | GET; actual available channels |
| `participant/auth/challenges/` | POST; reference/contact/channel |
| `participant/auth/verify/` | POST; challenge ID and code in body |
| `participant/auth/me/` | GET |
| `participant/auth/logout/` | POST |
| `participant/enrollments/` | GET summaries / POST initial enrollment and eligible ID |
| `participant/enrollments/{uuid}/id/` | GET minimal live card data |
| `operations/enrollments/` | GET search/pagination / POST prepare from an existing item |
| `operations/enrollments/{uuid}/id/` | GET card / POST issue, reissue, revoke or review_source |

Explicit new permissions on `CampEnrollment`: **`can_view_dic_ids`**, **`can_manage_dic_ids`**, **`can_review_dic_enrollment_sources`**. Existing operations access is also required for staff APIs. These are **not assigned automatically**. The old administrator provisioning command now excludes the new model permission sets, while preserving earlier grants and all memberships; an authorized administrator must deliberately assign the required permissions to existing accounts. Existing superuser semantics remain intact. No real accounts or memberships were created/changed during implementation.

Administrative audit records capture OTP request/rejection, successful scoped authentication/logout, enrollment creation, access/view, ID issuance/revocation and source review, with actor/target/version/reason references. Portal grant UUIDs in audit details are non-secret record references, never raw session credentials. General audit records do not contain OTPs, raw contacts or delivery payloads.

## Configuration and operational prerequisites

Actual inspected local state: **email unavailable, SMS unavailable, WhatsApp unavailable; recovery delivery worker disabled; verified logo URL unset**. These settings were not silently enabled, and no real messages were sent. The tests mock delivery using isolated fixtures; that does not establish live provider delivery acceptance.

Before operational use, configure an approved existing recovery delivery channel, encryption key and provider through the established environment configuration, then schedule:

```text
python manage.py send_dic_portal_messages --limit 50
python manage.py cleanup_dic_participant_access --limit 500
```

Run the delivery worker frequently enough for a ten-minute OTP lifetime. Cleanup is bounded, scrubs consumed/expired code/payload material and revokes expired grants while retaining ID/audit evidence. Verify delivery end-to-end with an authorized test contact after configuration; never put provider secrets/OTPs in reports or chat.

**`DIC_OFFICIAL_LOGO_URL`** must point to the approved original asset only after it is supplied/verified. No verified standalone local logo was found; the existing external public-site logo reference was not redrawn, cropped or substituted. With no configured verified asset the card displays an explicit branding-pending message. Final branding/print acceptance is outstanding.

Existing `dawana_dev` registration remains draft/closed, Paystack remains test, and the confirmed 23 December 2026–1 January 2027 dates/Faisal Omar Memorial School venue remain unchanged. Existing checkout/recovery tokens and contract were not changed.

## Testing and review status

New tests cover OTP validity/incorrect/expired/reused codes, browser binding, five-attempt lockout, request cooldown, generic responses, unavailable channels, session expiry/rotation/logout, Secure/HttpOnly/path/CSRF, staff-session coexistence and isolation, booking/contact/scope boundaries, minimal card data, verified/failed/pending/refunded/cancelled/manual-paid/legacy eligibility, multi-participant numbers, source ambiguity, source DB guards, collision retry, one current issue, replacement/revocation, staff permissions/audit, payload cleanup and real PostgreSQL concurrent enrollment/issuance.

Frontend tests cover cookie/CSRF-only requests, purpose-specific expiry notification, permission-controlled navigation, review labels and safe print-template field contract alongside existing appearance/session tests. Lint and build pass. No browser surfaces are connected (`apps=[]`, `browsers=[]`), so no browser or physical print-layout verification is claimed. Backend-generated data allowlists and print CSS checks do not substitute for visual inspection.

Final results:

| Check | Result |
| --- | --- |
| Complete Django suite | **173 passed**, 198.661 seconds, existing PostgreSQL test DB, `--keepdb --noinput` |
| New participant tests | 18 security/eligibility/lifecycle/concurrency cases included in the full suite |
| Frontend tests | **15 passed**, including 4 new participant-service/print-contract checks |
| Frontend lint | Passed without warnings |
| Frontend production build | Passed, Vite 8.3.0 |
| Django system checks | Passed, zero issues |
| Migration drift/history | No changes detected; history consistent; 0014 applied |
| Python syntax | 71 project files parsed successfully |
| `git diff --check` | Passed (only CRLF normalization notices) |
| Browser/physical print review | Unavailable/not performed |

One intermediate regression run rejected an ID-manager test fixture because the older fixture helper assigned only CampEdition permissions, not the new CampEnrollment permission. Explicit fixture assignment was corrected; the isolated lifecycle test and the subsequent full 173-test run pass. No failing authentication/authorization/payment/ID test remains. The expected recovery-delivery failure log comes from an existing failure-path test, not a failed suite.

Manual acceptance after configuring an authorized test environment: at desktop/tablet/mobile, test valid/invalid/resend/expiry flows, staff/participant coexistence, one family with multiple participants, a different booking at the same contact, ineligible and ambiguous sources, issue/reprint/revoke/reissue, each theme/reading size, keyboard focus, long-name A4/grayscale print preview, and absence of sensitive fields/QR. Use isolated test data, not fabricated operational registrations.

## Files changed

Created: `backend/dic/participant_services.py`, `participant_api.py`, `test_participant_portal.py`; `backend/dic/migrations/0014_participant_portal_and_ids.py`; `backend/dic/management/commands/send_dic_portal_messages.py`, `cleanup_dic_participant_access.py`; `dawana-platform/src/pages/ParticipantPortal.jsx`, `ParticipantPortal.css`, `StaffParticipantIDs.jsx`; `dawana-platform/src/services/participantApi.js`, `participantApi.test.js`, `participantIdentity.js`; this report.

Modified: `backend/dic/models.py`, `urls.py`, `operations_api.py`, `management/commands/setup_dic_staff_roles.py`, `backend/config/settings/base.py`; `dawana-platform/src/App.jsx`, `components/layout/SiteChrome.jsx`, `pages/Operations.jsx`, `services/operationsApi.js`, `services/operationsNavigation.js`.

Existing untracked files remain, including `MILESTONE_1L_ARCHITECTURE.md`, local editor settings and generated 1K acceptance artifacts. New implementation files remain untracked until reviewed/staged. `.vscode/settings.json` is untouched (SHA-256 `77E594534D02F33D324DBF54097A13EE3F5E3028E6410B3FB119347C2B714E12`). Nothing was committed, pushed or deployed.
