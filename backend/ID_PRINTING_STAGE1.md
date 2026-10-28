# Stage 1 participant ID printing

Implementation is present; backend execution and visual PDF validation are pending.
For the current security remediation, compatibility decision, credential-version
history format, and approval-gated validation commands, see
[STAGE1_REMEDIATION.md](STAGE1_REMEDIATION.md).
This environment denies execution of both installed Python interpreters. No
database migration, test database creation, or participant data change was run.

## Use

Open `/dic/operations/id-printing` after signing into Operations. Access requires
an active staff account with `dic.can_view_dic_operations` and
`dic.can_manage_dic_ids`. Issue IDs through the existing authorized issuance UI.
The directory includes only eligible enrollments with an unexpired, unrevoked,
activated credential. Select a house/category/status filter, select participants,
then choose **Download Bulk ID Cards (A4 PDF)**. Reprints are allowed and logged
as new exports. Mark a batch physically printed only after printing it.

PDFs use A4 portrait, four 90 x 130 mm badges per page, a 6 mm gap,
12 mm horizontal margins, 15.5 mm vertical margins, and external cutting guides.
Print at 100% / actual size. One individual portrait download also uses A4 with
one badge placed in the first slot. Existing PVC/A6 HTML downloads remain.
Participant portal downloads use existing booking and guardian authorization.

## Configuration and schema

Additive migration `0024_house_badge_colour` adds an optional validated
`House.badge_colour` hex value, editable in existing House Admin and edition
house inline. Names and colours have no invented defaults. Unassigned or
unapproved colours use a neutral grey section. Eight distinct approved colours
can be configured through existing house records; house count/names are not seeded.

`DIC_ID_BADGE_SIZE_MM = (90, 130)` controls dimensions. The current composition
supports widths 85–92 mm and heights 130–135 mm; other sizes require layout review.
`DIC_ID_FONT_FILE` / `DIC_ID_BOLD_FONT_FILE` can specify approved Unicode fonts.
Automatic choices are Windows Arial, Linux DejaVu Sans, then ReportLab Vera.
Review non-Latin script coverage and shaping before issuing those cards.
Existing cached official logo asset is reused. No replacement logo is created.

Registration calls existing transactional, idempotent `ensure_enrollment` for
each new item. It neither verifies payment nor issues credentials. Existing
registrations can still be prepared with the existing staff Prepare enrollment
action. Explicit authorized issuance/reissue now prepares a QR in the shared
service; the Admin command retains explicit activation for legacy IDs.

## APIs (under `/api/v1/dic/`)

- GET `operations/id-printing/`: eligible directory and latest 100 history events.
- POST `operations/id-printing/export/`: `{ "enrollment_ids": ["uuid", ...] }`.
  Deduplicates input; validates the entire selection; returns PDF or an error.
  Maximum 5,000 submitted IDs. Session authentication and CSRF required.
- POST `operations/id-printing/<batch_uuid>/printed/`: `{}`. Records physical
  print confirmation once per batch, independently of the export event.
- Existing `ids/cards/<enrollment_uuid>/?format=portrait`: staff individual PDF.
- Existing `participant/enrollments/<enrollment_uuid>/card/?format=portrait`:
  scoped participant/guardian individual PDF.

Existing immutable `DICAdminAuditEvent` stores batch UUID, actor, timestamp,
card count, enrollment IDs, participant numbers, and the issue ID/version for each
card. Historical unversioned events remain unchanged and are labelled unknown;
they never establish that the current credential was printed. Export and physical-print
confirmation use separate events. Credentials and QR payloads are not logged.
Exports lock registration orders, participants, enrollments and credentials during
eligibility checks and rendering. PDF generation failure rolls back export history.

## Files

Created: `dic/portrait_pdf.py`, `dic/printing_api.py`, `dic/test_id_printing.py`,
`dic/migrations/0024_house_badge_colour.py`, `requirements-test-ids.txt`, this guide,
and `../dawana-platform/src/pages/ParticipantIDPrinting.jsx`.

Modified backend: `dic/models.py`, `dic/admin.py`, `dic/views.py`,
`dic/participant_services.py`, `dic/participant_api.py`, `dic/identity_cards.py`,
`dic/identity_views.py`, `dic/urls.py`, `dic/tests.py`, `requirements.txt`,
and `../scripts/validate_dic_backend.py`.

Modified frontend: `src/pages/Operations.jsx`, `src/pages/ParticipantPortal.jsx`,
`src/services/operationsNavigation.js`, `src/services/operationsApi.js`,
`src/services/participantIdentity.js`, `src/services/participantApi.test.js`.
Pre-existing workspace modifications were retained.

## Verification

Passed: frontend production build, 64 service tests, and oxlint.
Backend tests have been added but NOT executed. Install dependencies from
`requirements-test-ids.txt` in a working Python environment, then run the existing
`scripts/validate_dic_backend.py --ids-only` isolated validation workflow. It
uses a unique local validation database and retains it; never point destructive
test commands at `dawana_dev` or production. Run `--phase2-and3` for broader housing
and identity regression checks. Review migration parity before applying 0024.

Tests cover geometry/cutting guides, 1/4/30/240 pagination, partial final pages,
duplicate selection, house colours, pending housing, eligibility and revoked /
expired / legacy credentials, staff/CSRF restrictions, export/reprint history,
idempotent print confirmation, registration preparation, scoped individual PDFs,
and QR decoding from a rasterized PDF using OpenCV and PyMuPDF.

Still required: execute backend tests; render and visually inspect generated PDF
pages with real-length names, approved photos, logo and house colours; verify
Unicode/script rendering; inspect dashboard in desktop/mobile browsers; check
participant/guardian downloads; scan printed QR codes on physical devices; measure
90 x 130 mm cards after actual-size printing and check badge-holder fit. A
download audit cannot establish printer success. Large exports synchronously
render in memory and need deployment load/timeout checks before high-volume use.
