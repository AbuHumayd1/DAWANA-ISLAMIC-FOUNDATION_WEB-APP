# Production deployment when funded

**INITIAL DEVELOPMENT COMPLETE — AWAITING PRODUCTION HOSTING FUNDING AND DEPLOYMENT**

Resume only after organization funding and the relevant operator approvals. This checklist is preparation, not permission to provision, connect, migrate, collect money, publish or deploy. Preserve existing working registration/payments/portal behavior. Both projected games are post-launch scope, not launch blockers.

## 1. Preserve the development baseline

- [ ] Confirm the safe source completion commit reported by the freeze task and its reviewed content. Private dumps/browser profiles/generated artifacts are excluded by `.gitignore` and retained locally; do not bulk-stage unknown evidence or push automatically. See `PROJECT_DEVELOPMENT_COMPLETION.md`.
- [ ] Record approved commit/artifact, owner and release decision. Retain operator-confirmed 180 backend/225 frontend passing results, lint/build and source migration review evidence; rerun focused checks only if changes justify it.

## 2. Funding, hosting and database identity

- [ ] Approve hosting/PostgreSQL plan, region, retention, access ownership and operating budget.
- [ ] Provision only the separately approved production infrastructure. Record actual settings module, server/port/database and role boundaries securely. Never reuse `dawana_dev`/`dic_2026_demo` as an assumed production target.
- [ ] Confirm least-privilege application/migration access, restricted administration and TLS. No role/password changes are authorized by this checklist.
- [ ] Review existing Render build/start/release scripts and `backend/config/settings/production.py`; do not assume staging-specific scripts are a finalized production deployment procedure.

## 3. Configuration, domains and services

- [ ] Supply production secrets through the approved secret manager/environment, never source control or chat. Follow existing settings/example documentation; do not invent hostnames, URLs or credentials.
- [ ] Configure exact domains, HTTPS, ALLOWED_HOSTS, CORS and CSRF trusted origins, secure cookies, proxy trust and API-before-SPA routing. Verify that forwarded security headers cannot be spoofed.
- [ ] Configure shared cache and separately authorize any required cache-table creation. Review static manifest, collectstatic, frontend build/proxy, approved media/storage and required background services.
- [ ] Verify approved email transport and account activation/recovery delivery without exposing tokens or sending unexpected real messages. Review SMS/WhatsApp/worker enablement separately; disabled defaults are not delivery proof.

## 4. Recovery and controlled migrations

- [ ] Obtain read-only connection approval, verify actual identity/history and generate a new exact pending manifest using the existing `release_migrations` inspection mode. See `scripts/DIC_2026_FINAL_EXECUTION_PLAN.md` for exact commands and safe variable setup.
- [ ] Include **all pending dependencies**, including `dic.0033_launch_completion`, not merely the newest file. Do not change dependencies or reuse the historical demo receipt as production approval.
- [ ] Separately approve a current private backup, check its hash/archive integrity and perform an approved disposable restore rehearsal. Record ownership, retention, inventory comparison and post-backup-write considerations. Follow `scripts/DIC_2026_STEP_B_BACKUP_READINESS.md` principles; its executable workflow is demo-only and is not a production backup command.
- [ ] Approve the manifest with the existing required keys: `manifest`, `approved_by`, `approved_at`, `backup_reference`, `restore_procedure`, `rollback_decision`.
- [ ] Only then execute the existing controlled command with `--apply-approved-plan --approval-file`, exact approved target/settings. Never run unrestricted migrations or bypass the rejection of protected local databases.
- [ ] Verify applied state and schema after execution. Stop on drift/failure; do not automatically reverse migrations, overwrite data or restore over production.

## 5. Staff, classes and content

- [ ] Approve named active staff accounts and individual domain grants. Use the exact permission matrix in `scripts/DIC_2026_FINAL_EXECUTION_PLAN.md`; finance/welfare/contacts/timetable publication are not blanket staff privileges.
- [ ] Enter only operator-approved academic class names in Academic classes Admin and assign registered campers in the same edition. Houses/categories remain separate. Do not invent class names.
- [ ] Approve announcement drafts and deliberately publish with the separate publication permission; verify drafts are invisible to campers.
- [ ] Confirm DIC 2026 edition ID, importer/publisher identities and reconciled seed hash. Preview the 188 entries using existing commands.
- [ ] Separately approve **draft timetable import** into the exact target. Confirm idempotency and staff-edit protection; do not overwrite conflicting content.
- [ ] Review dates, Day 6 amendments, Final Night, food text, mobile/print and guardian visibility. Obtain a **distinct publication approval**, then run the guarded publication command or authorized Admin action. Command templates are in the final execution plan; no new command is invented here.

## 6. Contact and donations

- [ ] Verify the operator-supplied public contact record; confirm additional address/WhatsApp only if provided. Telephone publication does not imply WhatsApp availability.
- [ ] After schema/staff/privacy/retention review, separately approve `FOUNDATION_CONTACT_FORM_ENABLED` activation. Assign inbox ownership and verify restricted enquiry/status access, validation, CSRF and spam controls.
- [ ] Foundation donations remain separate from DIC fees. Preserve `FOUNDATION_DONATIONS_ENABLED` default off until approved **test-only** activation. Review approved NGN limits, status-token privacy, checkout, amount/reference/currency/domain checks, replay and uncertain-payment behavior.
- [ ] Current donation/payment code requires test mode and rejects live collection. **Do not simply change to live keys.** Real collection requires a separately reviewed activation/code decision and provider approval/verification.
- [ ] Review the existing working Paystack registration callback/webhook configuration before any provider production configuration. Foundation donation webhook is a separate route; do not replace the DIC webhook automatically. Confirm account-level routing constraints, HTTPS, raw-body signature checks and server-side verification in the approved provider mode.
- [ ] No real charge, refund, external webhook change or message send is authorized by the freeze. Approve each consequential activation separately.

## 7. Smoke tests and launch approval

- [ ] With traffic restricted, verify HTTPS/static/API/health plus actual schema/cache readiness. Health alone is insufficient.
- [ ] Run focused approved synthetic registration/guardian child-isolation, payment callback/replay, portal class/announcement/timetable, officer QR/duplicate scan, restricted enquiry and reporting/finance smoke checks. Never use real camper or welfare data as fixtures.
- [ ] Check desktop/mobile navigation, errors/loading/empty states, keyboard use and print views. Record actual PASS/FAIL/NOT RUN without equating unit tests to production acceptance.
- [ ] Confirm monitoring, sanitized logs, service ownership, backup schedule, restore decision and incident response.
- [ ] Obtain final launch approval before public traffic/registration or payment activation. Record implemented, tested, activated and deployed states independently. Do not label production verified before evidence exists.

## References and command policy

Use the exact context-checked commands already supplied in `scripts/DIC_2026_FINAL_EXECUTION_PLAN.md`, the existing `release_migrations` command, `import_dic2026_timetables`, and `publish_dic2026_timetables`. `scripts/review_dic_launch_migration.py` is source-only; `scripts/validate_dic_launch.ps1` is database-free validation. Neither authorizes writes or deployment. Existing acceptance/demo scripts must not be retargeted to production by editing their guards.

No infrastructure, database, payment, publication or deployment operation was performed while preparing this checklist. Production remains unprovisioned/unverified in this handover until funded execution supplies evidence.
