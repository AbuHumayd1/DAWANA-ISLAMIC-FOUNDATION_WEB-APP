# Phase 2.4 — Feedback and confidential welfare handover

Code prepared on 25 October 2026. **Not deployed or declared fully verified.** Proposed migration 0027 and the privacy/permission/retention approach require review and explicit approval before application. No existing data, accounts, permissions, privacy secrets or database schema were changed.

## Implementation and reuse

Reused existing verified participant/guardian booking cookies, Operations session login/CSRF/client, active-staff authorisation, edition selector conventions, report export permission, CSV spreadsheet escaping and printable HTML. No new registration, lecturer identity, payment, house, score, allocation or check-in system was introduced.

- Daily camper: six simple ratings (learning, activities, comfort, meals/care, organisation, overall) and optional suggestions.
- Final camper: overall/knowledge ratings, beneficial activities, improvements, future suggestions and recommendation.
- Staff: effectiveness, coordination, participation, facilities, challenges and recommendations; identified.
- Lecturer: organisation, facilities, engagement, time, organiser support and recommendations; identified by an explicit existing-account/lecturer mapping.
- Welfare: six categories, identified verified reporter, person needing assistance, description, server timestamp, status, assigned authorised officer, internal notes and restricted access/change history.

Three ratings are used: Needs improvement, Okay, Good. Question labels use short wording; a guardian may help a younger camper enter the camper's own answers. Dates use existing edition start/end dates, not an invented fixed day count. Future days are rejected; final evaluation opens on the configured final day. Welfare requests are not delayed until camp starts.

## Proposed schema — six tables, no data migration

`0027_feedback_welfare.py` depends on `0026_house_score_transaction` and the configured auth model:

| Model | Fields and purpose |
|---|---|
| AnonymousCamperResponse | Random UUID; edition; camp day; daily/final channel; approved ratings; approved answer fields. **No identity/contact/login/house/booking fields, precise submission timestamp or receipt/request link.** |
| CamperFeedbackReceipt | A single keyed HMAC digest as primary key. No participant FK, response FK, edition FK, request ID or timestamp. Digest input includes participant, edition, day and channel, only transiently in server memory. |
| IdentifiedFeedback | Edition, staff author, optional actual lecturer, staff/lecturer channel, day, ratings, answers, timestamp. Unique author/edition/channel/day. |
| LecturerFeedbackAccess | Edition, existing login account, existing lecturer, enabled flag. Unique edition/account and edition/lecturer. No identities are auto-created. |
| WelfareReport | UUID, edition, exactly one reporter user or primary registrant, assistance-person text, category, description, status, officer, timestamp, version and unique submission UUID. |
| WelfareEvent | Report, responsible staff actor where applicable, create/view/update kind, private note, change snapshot, timestamp and unique update reference. |

Model CRUD permissions are disabled by default. Responses, receipts and welfare records are deliberately not registered as ordinary Admin model browsers. Only explicit lecturer-account mapping is exposed in Admin, through the new configuration permission. No migration/backfill seeds responses, mappings, accounts or permissions. Existing records are untouched.

**Before applying:** review these fields and privacy design; approve schema application and intended target; obtain/check a fresh readable PostgreSQL backup. The previously checked pre-scoring backup is not claimed as a fresh Phase 2.4 deployment backup. No apply command was executed or approval inferred.

## Actual privacy guarantees and limitations

Camper submission is authenticated through existing booking scope, but identity is not copied to its response. Duplicate protection uses a separate, one-way keyed digest; that receipt has no response ID. One daily response per participant/edition/day and one final response per participant/edition are accepted. Retries acknowledge the original without revealing a response identifier or overwriting answers. Multiple bookings for one participant do not create extra allowances.

`DIC_FEEDBACK_PRIVACY_KEY` is a new, separate, stable deployment secret. At least 32 characters are required; use high-entropy secret-store material, not a memorable phrase. It is empty by default; anonymous submission fails closed with a privacy-setup message until configured. No secret was generated, installed or logged. Do not rotate/delete it or receipts while collection is open, because that would reset duplicate prevention.

There is no ordinary Admin receipt browser or receipt-to-response join. Anonymous groups below five responses suppress exact counts, distributions and comments, even for the comment-reader role. Summary exports contain only aggregates; comment/identified-response reading requires a separate permission and is logged. There are no house, age, participant or contact filters.

**This is not absolute anonymity or a cryptographic blind-signature system.** Server/proxy authentication and IP logs, timing, PostgreSQL transaction/WAL/backups, deployment operators with the privacy key, or self-identifying comments can permit correlation. The application creates no named camper-submission audit record and stores no exact response time, but privileged infrastructure operators still have technical visibility. Do not log request bodies, digests or cookies; review proxy/APM/error capture before launch. Users are warned not to enter identifying details in general comments and directed to welfare for confidential identified help.

Welfare is confidential through application permissions, not anonymous and not application-field encrypted. It is absent from general feedback queries, comments, summaries, CSV and print endpoints. Reporter identity for a portal report is the booking's verified **primary registrant**, not an unverified claim that the selected child personally submitted it. Staff reports use the authenticated account. Follow-up and access events stay in the restricted welfare table, not the ordinary Operations audit feed. Authorised detail reads create access events. List views omit descriptions, reporter names and notes.

Retention has deliberately not been invented: there is no automatic purge, blanket retention period or destructive endpoint. Approve response/comment, identified-feedback, welfare/history, receipt, log and backup retention and responsible owners before opening collection. The receipt ledger intentionally has no edition FK; do not perform an ad hoc per-edition receipt purge or key rotation. Schema approval does not itself approve log/backup retention or access assignments.

## Permission plan — no automatic grants

All staff paths require existing active staff Operations access. Existing Django superuser permission semantics remain; review who holds that privilege.

| Permission | Access |
|---|---|
| can_view_dic_feedback | General summaries/distributions/trends |
| can_read_dic_feedback_details | Additionally read authorised comments and identified response details; access logged |
| can_submit_dic_staff_feedback | Submit one's own identified staff feedback |
| can_submit_dic_lecturer_feedback | Submit one's own mapped lecturer feedback |
| can_configure_dic_feedback | Explicitly map an existing staff login to a confirmed lecturer for an edition in Admin |
| can_submit_dic_welfare | Submit an identified staff welfare report; does not grant viewing |
| can_view_dic_welfare | Confidential welfare lists/details/history; does not grant general feedback access |
| can_manage_dic_welfare | Additionally assign officers/change statuses/add notes; view permission also required |
| existing can_export_dic_reports | Additionally print/download general summary aggregates; never grants welfare export |

Lecturers use an explicitly authorised existing Operations staff login; there is no public lecturer login or automatic staff-account creation. Their mapping must match a confirmed existing LecturerAppearance for the edition. Mapping changes are audited. Do not grant generic feedback-view permission to lecturers merely so they can submit; the separate submission page works independently.

Welfare officers must already be active staff with Operations, welfare-view and welfare-manage permissions. The application does not invent officer identities or assign permissions. Any of the four approved statuses may be selected with a required follow-up note; version checks prevent stale overwrites. Same-reference retries do not duplicate updates/history. There is no complex approval workflow.

## Pages and endpoints

Frontend:

- `/dic/feedback`: camper/guardian forms, using an already verified participant session. Portal links here; expired sessions clear loaded participant choices and prompt verification.
- `/dic/operations/feedback`: permission-protected edition/channel/day summaries, daily trends, counts/distributions, optional authorised details, CSV/print.
- `/dic/operations/feedback-submit`: permitted staff/lecturer submission and identified welfare-assistance forms.
- `/dic/operations/welfare`: separate confidential list/detail/status/officer/follow-up view.

API prefix `/api/v1/dic/`:

- GET `participant/feedback/options/`: verified booking choices, questionnaire and session expiry.
- POST `participant/feedback/`: scoped `item_id`, daily/final answers. Returns accepted/duplicate only.
- POST `participant/welfare/`: scoped `item_id`, category, description, assistance person and request UUID. Reporter identity comes from booking scope.
- GET `operations/feedback/options/`: form schema and editions, no submissions.
- POST `operations/feedback/submit/?edition=…`: own identified staff/lecturer response.
- GET `operations/feedback/?edition=…&channel=…&day=…`: summaries. `details=1` separately authorised; `export=csv|print` aggregates only with existing export permission.
- GET/POST `operations/welfare/?edition=…`: restricted listing / permitted staff submission.
- GET/POST `operations/welfare/<uuid>/?edition=…`: logged confidential access / versioned follow-up update.

Writes require the existing CSRF protections and server-side validation. Unapproved channel/question/identity-answer keys and out-of-edition days are rejected; foreign welfare reports are not updated. JSON values are rendered as escaped React/Django text, never arbitrary HTML. All new APIs return no-store. Missing tables return clear setup-pending 503 messages without making other dashboard modules query the new tables.

## Tests and limitations

Actually executed:

- **96 frontend tests passed**, zero failed (five new feedback tests). Covers permission-separated navigation, edition/export queries, empty/suppressed groups, distributions and recommendation display, escaped comments, identity-free camper form fields and welfare notices. Existing navigation matrix expanded to 1024 combinations; old planning assertions updated because Feedback is now live.
- Lint passed without warnings after fixing two initial unused-expression warnings.
- Production build passed; existing >500 kB bundle warning remains (about 550 kB).
- Targeted `git diff --check` passed; existing line-ending conversion warnings remain.
- Backend database-free run attempted: `python -B backend\manage.py test dic.test_feedback.FeedbackPrivacyTests --verbosity 2` through the existing venv launcher. It failed before Django started with base-interpreter Access is denied. No Python reinstall, venv recreation, permissions change or DB operation was attempted.
- Browser automation could not initialise (kernel-assets path, OS error 3). No visual/mobile/print acceptance pass is claimed.

Prepared but **unexecuted**: 13 database-free privacy/permission/CSRF/validation/export/aggregate tests and four isolated-DB integration tests for unlinked daily/final submission, real lecturer mapping, confidential welfare lifecycle/idempotency/history, edition isolation and access logging. The integration tests use synthetic accounts/data only inside an approved isolated test database, never development. Model/migration parity and real transaction/uniqueness behaviour remain unverified here.

## Exact local commands

Before any schema approval, from repository root in the existing activated PowerShell:

```powershell
# SimpleTestCase only; no database creation/migration.
python -B backend\manage.py test dic.test_feedback.FeedbackPrivacyTests --verbosity 2
# Read-only migration/model comparison; no files or schema changes.
python -B backend\manage.py makemigrations dic --check --dry-run --noinput

Set-Location .\dawana-platform
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

After review and explicit approval for schema/privacy validation **in an isolated database only**, from repository root:

```powershell
python -B scripts\validate_dic_backend.py --operations-feedback
```

That new focused option uses the existing runner's unique local PostgreSQL database, model/migration parity checks, external-network blocking and strict discovered/executed test accounting. It retains the new database and refuses reuse; it never migrates or flushes `dawana_dev` or changes role permissions. It has not been executed here. Do not use ordinary `manage.py test dic.test_feedback` against an unreviewed default test database.

Manual acceptance after approval: desktop 1440×900, tablet 768×1024, phones 390×844 and 360×800; verify normal document scrolling, all five forms, expiry/logout clearing, validation/duplicate messages, permission-denied/setup-pending states, summary privacy suppression, CSV/print, confidential welfare access/history and staff/lecturer mapping. Before approved schema installation only denied/setup-pending paths are expected to work. Do not create real development submissions for acceptance.

## Files created

- `backend/dic/feedback_models.py`
- `backend/dic/feedback_schema.py`
- `backend/dic/feedback_services.py`
- `backend/dic/feedback_api.py`
- `backend/dic/feedback_admin.py`
- `backend/dic/migrations/0027_feedback_welfare.py`
- `backend/dic/templates/dic/feedback_summary.html`
- `backend/dic/test_feedback.py`
- `backend/dic/FEEDBACK_WELFARE_PHASE2_4.md`
- `dawana-platform/src/components/operations/FeedbackForms.jsx`
- `dawana-platform/src/pages/CamperFeedback.jsx`
- `dawana-platform/src/pages/Feedback.jsx`
- `dawana-platform/src/pages/Feedback.css`
- `dawana-platform/src/services/feedback.js`
- `dawana-platform/src/services/feedback.test.js`

Modified: `backend/dic/models.py`, `admin.py`, `urls.py`, `operations_api.py`; `backend/config/settings/base.py`; `scripts/validate_dic_backend.py`; `dawana-platform/src/App.jsx`; `src/pages/Operations.jsx`, `ParticipantPortal.jsx`; `src/services/operationsApi.js`, `operationsNavigation.js`, `campsiteModules.js`, `campsiteFoundation.test.js`, `operationsRefinement.test.js`.

Outstanding approvals: six-table schema, privacy/logging/retention approach, separate privacy-secret configuration, intended permission assignments and lecturer mappings. Outstanding execution: all backend tests/parity checks and browser/print acceptance. No subsequent phase was started.
