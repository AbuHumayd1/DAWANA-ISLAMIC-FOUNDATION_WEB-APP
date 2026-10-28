# DIC 2026 final launch completion

Implemented the remaining requested features without changing DIC registration/payment settlement, house allocation, credentials or production configuration. The operator's successful multi-camper registration, fees, Paystack test payment/verification and portal access remain **operator-reported evidence**, not newly executed tests. Both games are deferred post-launch and are **not launch blockers**; no game was implemented or tested.

## Completed code

- Academic classes and camper assignments are edition-scoped, separate from houses and categories. Authorized officers manage operator-approved names/assignments in Django Admin. Cross-edition/inactive classes and tutor assignments are rejected. The participant portal displays assigned class names, with pending/unassigned states before setup. No class structure or assignments were seeded.
- Announcements have draft/published state, optional visibility windows, separate edit/publication rights, edition isolation and audit records. Published content is escaped as text in the desktop/mobile portal. Drafts never enter the camper query. Unpublish before editing.
- Contact now displays the operator-confirmed `dawanaislamicfoundation@gmail.com`, `+2347062956559`, `+2348105320528`, and `+2349018076534`. Phone/email actions are real links. WhatsApp and address were not inferred. Enquiries support required validation, CSRF, rate limiting, honeypot/deduplication and a permission-protected staff inbox; no public enquiry listing or unsolicited outbound email exists.
- Donations are a separate Foundation ledger and endpoint family, with random request IDs/private status tokens, exact decimal/kobo handling, idempotent initialization, trusted checkout URLs, server verification, signed webhooks, immutable successful settlement and a restricted audit view. Pending, failed, abandoned, mismatch/review and uncertain-initialization states do not become successful donations. DIC registration payments and Finance totals are not repurposed. Test mode/key is mandatory; collection remains disabled. No business amount limit was invented: NGN 0.01 through the signed 64-bit kobo storage ceiling is supported by the application; provider/precision limits still apply.

## Timetable reconciliation and procedures

The operator reconfirmed the supplied PDF/DOCX as the latest sources, with only the confirmed Day 6 health/sports swap, and explicitly retained the December 31 sisters' workshop / brothers' activity for later staff editing. The requested evening label is now **Final Night**.

Verified by executed frontend source-data assertions: **188 entries, two types, ten dates**; December 23 arrival; December 24 opening **09:00–11:00**, Basic Islam **11:00–13:00**; December 28 Health Forum / Health Symposium **11:00–13:00**, Sports Activities **17:00–18:30**; unchanged December 31 workshop/activity time; Final Night retains its source time slots. Food remains unchanged, including blanks and original spelling. No invented programme or food-serving times.

Reviewed seed SHA-256: `046fa64c9fd99de6c4e18e1c38ab8557d3879128cd131696e4ea94b553282bbf`.

Import and publication remain **separate approvals**. Both commands default to no-database previews:

```text
manage.py import_dic2026_timetables --edition <approved-id>
manage.py publish_dic2026_timetables --edition <approved-id>
```

Only after separate target-specific approval, each write operation requires `--apply --database-name <exact-target> --approved-by <authorized-username> --approved-seed-sha256 <reviewed-hash>`. Do not run either write mode merely because isolated acceptance was previously authorized. Actual PostgreSQL identity must match. Import uses stable keys and a durable receipt, preserving edits/deletions on reruns. Publication requires the matching import receipt and an exact seed snapshot; reruns do not create entries or republish already published rows. Edited/extra/outdated data blocks the command and requires deliberate full-day Admin review/publication instead. No import or publication occurred.

## Files

New backend: `launch_models.py`, `launch_services.py`, `launch_api.py`, `launch_admin.py`, `foundation_models.py`, `foundation_api.py`, `foundation_urls.py`, `foundation_admin.py`, `test_launch_completion.py`, `migrations/0033_launch_completion.py`, `data/foundation_contact.json`, and `management/commands/publish_dic2026_timetables.py`.

Existing backend changes: model/admin/URL registration; `participant_api.py` and `portal_phase3.py` class projection; reconciled timetable JSON and its test; seed-command exact-hash guard; `config/urls.py` Foundation routes; `config/settings/base.py` disabled-by-default Foundation settings and the donation status CORS header. No environment file changed.

Frontend: new `components/foundation/FoundationExperience.jsx`, `components/dic/CampUpdates.jsx`, `services/foundation.js`, `foundation.test.js`, `foundationPages.test.js`; integrated existing Contact/Donate layouts, class/announcement portal components, focused portal/timetable tests and minimal existing-theme form styling in `App.css`.

Validation: `scripts/validate_dic_launch.ps1`, `scripts/validate_dic_launch_policy.py`, and this handover.

## Verification

- **PASS:** 225 frontend tests, zero failures; lint; production build. Log: `output/acceptance/launch-completion-verified.log`. Contact/Donate page render regressions are covered. Non-fatal Vite bundle-size warning remains.
- **PASS:** PowerShell runner syntax and targeted whitespace checks. Original Step A receipt checksum unchanged.
- **NOT RUN:** focused Django checks/tests, new model/migration parity, guardian activation/isolation and QR backend policy regressions: the configured Python 3.13 interpreter could not start due to access denial. One attempt; no alternate runtime retry or installation.
- **NOT RUN:** actual database-backed donation/contact/assignment/announcement workflows, hosted checkout/provider-limit acceptance, real browser/mobile/print presentation. Database-free mocks/source checks do not prove those workflows. The existing browser service is unavailable in this agent environment.
- No database connection, migration, timetable import/publication, grant, payment request, email/SMS, deployment or cleanup was performed. No real camper records changed.

## Necessary release actions

1. Run the command below locally and resolve any backend test/model-parity failures before migration approval. New policy tests cover classes, announcement visibility/permissions, contact validation, donation CSRF/token/signature/amount/domain/idempotency, source previews and focused existing guardian/QR policies.
2. Review additive **`dic.0033_launch_completion`**, depending on 0032; regenerate the controlled migration manifest and obtain target-specific approval. Historical migrations/receipt were not altered. Apply no migration to an existing database without that approval.
3. Grant named staff only the required rights: `dic.manage_dic_classes`; `dic.manage_dic_announcements`; separate `dic.publish_dic_announcements`; `dic.view_contactenquiry` / `dic.change_contactenquiry`; and `dic.view_foundation_donations`. Existing timetable edit/publication permissions remain separate. No role grants were automatic.
4. Supply approved academic class names for the edition in Admin, then assign campers. Create/review/publish announcements deliberately. No academic class names were invented.
5. Approve the target and exact reconciled seed, import drafts, review portal previews, then separately approve publication. Validate mobile/print and guardian/QR negative cases in the authorized isolated environment.
6. After schema/staff review, enable the contact inbox with `FOUNDATION_CONTACT_FORM_ENABLED=True`. Confirm staff ownership/response handling and private-record retention. The supplied verified public channels already have a source record. Additional address/WhatsApp data are optional, requiring operator confirmation before display; verified override settings are available.
7. Separately approve **test** donation activation with `FOUNDATION_DONATIONS_ENABLED=True` and the already configured test-mode Paystack architecture, then test checkout/status/webhook replay against the approved target. No new real credential is required by this code. Do not enable live collection; it is deliberately rejected and requires a separate reviewed activation change. Do not mix donation revenue into DIC registration totals.
8. Deployment remains separately approved. Complete only the applicable controlled release gates; this handover is not deployment authorization.

One consolidated safe local command (database-free backend policies plus frontend tests/lint/build):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_launch.ps1
```
