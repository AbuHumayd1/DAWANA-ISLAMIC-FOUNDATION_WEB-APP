# DIC 2026 isolated end-to-end acceptance: provisioning gate report

Date: 28 October 2026, Africa/Lagos. Baseline: `scripts/DIC_2026_FUNCTIONAL_ACCEPTANCE.md`.

**Verdict: INCOMPLETE — STOPPED BEFORE PROVISIONING.** The request authorizes creation/migration/testing of a new isolated environment once its safety gates pass. That authorization is acknowledged; it is not authorization to guess a provisioning role, use an existing application database, or bypass an unverified isolation configuration.

## Exact proposed environment and actual resource record

- Proposed database: `dic_2026_acceptance_6f90a9b962804378b22fbe95145b05d1`.
- Database status: **NOT CREATED**. A UUID name was generated locally; catalog absence is **NOT VERIFIED** and uniqueness is not claimed from the UUID alone.
- Proposed endpoint: numeric loopback `127.0.0.1:5432`; **actual server identity/version and approved provisioning role NOT VERIFIED**.
- Dedicated acceptance configuration, payment adapter, service runner and fixture harness: design requirements below; **not implemented or runtime-verified**. Ordinary development settings must not be used as a substitute.
- Local backend/frontend services: **NOT STARTED**. No ports were reserved, no application session issued.
- Synthetic rows, users, credentials, QR IDs, timetable entries and finance/welfare records: **none created**.
- No resources require database cleanup. Preserve this report and frontend validation log; no cleanup is authorized by this report.

## Pre-provisioning gate

| Required gate | Result | Evidence / blocker |
|---|---|---|
| Exact PostgreSQL server/port identified | NOT VERIFIED | Prior baseline records a loopback PostgreSQL endpoint. No new connection was opened; installed clients or running services do not identify the server behind that endpoint. |
| Approved local provisioning/application roles | NOT VERIFIED | Earlier investigation identified configured application-role candidate `dawana_app`, without explicit acceptance provisioning approval. Application configuration is not proof of CREATEDB rights or an approved test role. No credentials were read or changed here. |
| Proposed name unused | NOT RUN | Requires a narrowly scoped catalog check using an identified approved role/server. No database connection was attempted. |
| Dedicated config cannot fall back | NOT ESTABLISHED | `config.settings.base` reads `backend/.env`; existing helpers target development/demo names. A complete acceptance bootstrap must reject unsafe inputs before Django/application imports or sockets. |
| Mocked Paystack and network deny policy | NOT ESTABLISHED for new environment | Reusable patch patterns exist, but no new backend process has a verified acceptance payment adapter/network guard. Setting PAYSTACK_MODE=test alone is insufficient. |
| Intercepted outgoing mail | NOT ESTABLISHED for new environment | Required locmem interception is planned, not running. No SMTP/provider call occurred. |
| Background/webhook isolation | NOT ESTABLISHED for new environment | No worker/webhook listener started. Any future runner must disable external delivery workers, OAuth and real provider callbacks, accepting synthetic signed webhooks locally only. |
| Cleanup limited to owned resources | PLAN ONLY | Exact proposed name is recorded, but no provisioning/ownership receipt exists because nothing was created. |
| Python can execute prerequisites/harness | BLOCKED | The virtual environment could not start its configured Python 3.13 executable: access denied. One backend policy attempt; no retry/install or security-policy bypass. |

The mandatory instruction to stop when a safety condition cannot be established was followed. No database was created or migrated. Existing application guards were not weakened.

## Inspection findings and reusable utilities

Reviewed the baseline report, `config/settings/base.py`, `development.py`, migration files/receipt, `validate_dic_finance.py`, `validate_dic_phase3_acceptance.py`, `validate_dic_phase5_demo.py`, `validate_dic_phase5_policy.py`, and Phase 4 validation scripts.

Useful patterns: database-free `SimpleTestCase` allowlists, intercepted network/process calls, local synthetic email settings, sanitized failure receipts, payment-provider patches, explicit target verification and guarded transaction test cases. These can inform a new acceptance harness after prerequisites are established.

Do **not** repurpose an old runner by changing its hardcoded target: Phase 3 is explicitly bound to `dic_2026_demo` and rejects later welfare schema; Phase 5 demo utilities also target that protected database. Their migration/rollback-only assumptions do not satisfy this newly authorized environment. Do not invoke their database modes or weaken their existing guards. The full existing migration graph must be reviewed/applied only within the new disposable environment, not reduced to an older phase target.

The source-reviewed Phase 4 leaf still depends on `dic.0031_phase5_feedback_welfare`; migration files were not modified. The preserved Step A receipt checksum remains `c70fa32d1de80e6e426a2f90d8a030548cdf5bdd96c8063a822a076b05e27d9f`. Live graph/history verification was not repeated.

## Required isolated configuration before execution

This is a design checklist, not an executable configuration or claim that isolation has passed:

1. Use an acceptance-only bootstrap/settings module that validates the full exact database name and numeric loopback host/approved port **before** importing ordinary settings, loading application database configuration or opening sockets. Reject nonempty DATABASE_URL/service/alternate-host inputs, all protected names, additional aliases and test-database fallback names. Do not edit `.env`.
2. Identify an already approved provisioning role able to create only the intended disposable environment under operator control; PostgreSQL CREATEDB is broad, so do not grant it automatically to the application role. Prefer operator provisioning with a pre-existing approved provisioner. Use a non-superuser application/migration owner confined to the new database; no source database grants or inherited production credentials.
3. Before CREATE, verify the actual server endpoint/version/role and inspect `pg_database` solely for the proposed exact name using an approved maintenance connection. Stop if the name exists. Do not connect to the protected application databases or drop/replace an existing target. Record target creation and ownership evidence.
4. Gate every migration/fixture/application connection on the pinned exact database and ownership receipt. A Django test runner can create a separate TEST database unless configured/guarded: do not run unrestricted `manage.py test`, flush, reset or migrate commands. Review the exact migration plan and its hashes for the new target before applying it there.
5. Use a process-lifetime mock payment adapter for initialization/verification, deterministic synthetic references, wrong amount/currency/reference/domain, failed/abandoned and duplicate cases. Do not allow checkout scripts or API calls to Paystack; synthetic verification/webhooks must test the application's real settlement logic with mocked provider evidence.
6. Install network deny guards before application imports, permitting only the owned local frontend/backend and approved PostgreSQL endpoint. Block SMTP, provider HTTP, external webhooks, OAuth, object storage and subprocess escapes. Use locmem mail, local-only cookies/origins/cache/storage and generated test secrets. Start no delivery jobs/cron/worker. No production environment values may supply acceptance targets or credentials.
7. Bind local services to loopback on separately checked unused ports; log sanitized identity only. A browser context must intercept/deny all external requests, use synthetic inputs and hold no existing application cookies. Verify the guards with negative tests before any fixture migration/write.
8. Retain the new database for review; never auto-drop it. A later cleanup approval must reference its exact creation/ownership receipt, database name, run ID and owned process IDs. Recheck exact target/ownership before an operator-controlled drop; no wildcard cleanup or `--if-exists` substitution for proof of ownership.

## Planned deterministic fixture catalogue — none created

| Stable synthetic key | Purpose |
|---|---|
| `acceptance_adult_1` | Adult privacy rules, category/price/profile and individual booking |
| `acceptance_guardian_1`, `acceptance_minor_1`, `acceptance_minor_2` | Minor guardian data, grouped payment, multi-child authorized scope |
| `acceptance_unrelated_1`, `acceptance_unpaid_1` | Unrelated/unpaid order and child access denials |
| `acceptance_tutor_1` | Existing tutor exception; no fabricated house/class/competitive privileges |
| `acceptance_house_a`, `acceptance_house_b` | Real implemented housing relationship and capacity boundaries |
| `acceptance_checkin_officer`, `acceptance_movement_officer`, `acceptance_departure_authorizer` | Existing distinct officer permissions, invalid/duplicate/revoked/expired QR cases |
| `acceptance_admin_limited`, `acceptance_finance_creator`, `acceptance_finance_approver`, `acceptance_welfare_officer` | Least-privilege administration, actor separation and confidential-data denials |
| `acceptance_payment_*` | Verified, pending, failed, abandoned, mismatched and duplicate provider evidence; no real transactions |
| `acceptance_feedback_1`, `acceptance_welfare_1` | Synthetic confidential submissions, status handling and safe/forbidden projections |
| `acceptance_timetable_*` | A few separately labelled synthetic activity/food drafts/publications **only in the disposable database**; date/timezone/scope/empty states |

Use `.example.test` email addresses and test-mail interception. Resolve category IDs/prices from synthetic configured edition/category fixtures, never from copied real orders. Academic classes/announcements are absent, so no class assignment or announcement records should be invented. No existing timetable source import command may run; all 188 prepared entries remain unimported/unpublished.

## Actual test execution

| Check | Result | Evidence |
|---|---|---|
| Frontend suite | PASS: 217/217, zero failed/skipped | `output/acceptance/isolated-e2e-gate-frontend.log` |
| Frontend lint | PASS | Same log |
| Production build | PASS; non-fatal bundle-size warning | Same log |
| Backend database-free policy suite | NOT RUN | Python interpreter startup access denied; no backend assertion executed |
| Browser/mobile/keyboard/accessibility | NOT RUN | Computer-use discovery returned no apps/browsers; native pipe unavailable |
| Disposable identity/name check, provisioning, migrations, fixtures | NOT RUN | Mandatory gate blocked before connection/creation |
| Database-backed API/integration acceptance | NOT RUN | No disposable database or running isolated backend |

The previous operator-confirmed 231 backend and 19 Step B passing tests remain historical baseline, not new results. No PostgreSQL backup/restore troubleshooting resumed.

## Seven-journey execution record

| Journey | Expected outcome | Actual outcome/method | Status |
|---|---|---|---|
| 1 Public registration/payment | Persist validated adult/minor registration, mock initialization/verification, confirmation; reject failed/abandoned/duplicate settlement | Only relevant existing frontend service/component tests executed. No real request-to-database sequence. | NOT RUN end-to-end |
| 2 Guardian/multiple campers | One grouped order, activated account, only eligible linked children; reject unrelated/unpaid access | Relevant frontend tests pass; no synthetic accounts/orders created. | NOT RUN end-to-end |
| 3 Participant portal | Authenticated profile/house, synthetic timetable visibility, empty/draft denial, logout; truthful absent-class state | Frontend tests pass; no portal session or timetable fixtures. | NOT RUN end-to-end |
| 4 QR attendance | Authorized issue/scan/arrival/movement/departure and attendance/audit consistency; duplicate/invalid/unauthorized denial | QR/client tests pass; no actual issued QR, officer session or presence transition. | NOT RUN end-to-end |
| 5 Administration | Staff authentication, least-privilege camper management/filter/search and accurate exports | Navigation/controls tests pass; no authenticated management/export run. | NOT RUN end-to-end |
| 6 Finance | Verified versus pending income, reconciliation and adjustment limits, duplicate protection, permission/audit/report accuracy | Finance client/component tests pass; no persisted accounting sequence/export. | NOT RUN end-to-end |
| 7 Feedback/welfare | Synthetic camper submission, authorized review/status, audit, unrelated-user and internal-note confidentiality | Client tests pass; no persisted confidential submission/review sequence. | NOT RUN end-to-end |

No screenshots are available. No journey is marked PASS based on source code or unit tests alone.

## Updated feature acceptance matrix

Public navigation, registration, participant/guardian portals, house/profile views, QR/client workflows, timetables, feedback/welfare, Operations/report controls and finance retain **PARTIAL** unit/component acceptance. Real browser and backend-integrated acceptance for each remains **NOT RUN**.

Timetable operational population remains unavailable by the preserved baseline. Academic class assignment, portal announcements, contact delivery/official channels, donation checkout/instructions and both projector/host games remain **NOT IMPLEMENTED** as documented in the baseline report. These are not authorized for implementation by this request.

## Prioritized defect register and launch recommendation

- **Execution blockers, not application P0/P1 defects:** unusable agent Python runtime; approved provisioning role/server/name-availability check missing; no verified dedicated acceptance bootstrap/mocks/network guards; browser runtime unavailable. Their consequence is NOT RUN acceptance, not a fabricated application failure.
- **Existing P2 gaps AC-01–AC-04:** contact channels/delivery, donation support, class allocation and announcements; retain the baseline evidence/reproduction procedures and explicit scope decisions.
- **Existing P2 scope discrepancy AC-05:** dormant alternate staff-booking capability remains in source; keep disabled and review against the same-public-registration requirement. Runtime activation remains unverified.
- No new executed application failure, confirmed P0 data exposure or P1 transaction-integrity defect was established. Non-fatal bundle-size warning remains a performance-review item.
- Games remain outside the seven-phase acceptance claim. Whether they are camp-launch critical is an operator programme decision; no game feature was built.

**Launch recommendation: NOT YET VERIFIED.** Do not infer readiness from 217 passing frontend tests or permission/migration source presence. Restore local Python execution, identify the already authorized provisioning role/endpoint and credential source, then implement and prove the acceptance-only bootstrap and guards before catalog checks or database creation. The supplied isolated-environment authorization already covers the intended new-target operations once every gate passes; no repeat blanket approval is requested. Additional privileges, access to protected databases, external services and cleanup remain outside that scope.

## Next safe operator action and repeat command

Provide the exact approved local provisioning role, maintenance endpoint and restricted acceptance application role, without pasting passwords or database URLs. Run Python checks from the operator's working local PowerShell if interpreter access remains restricted to this agent. Do not start the old demo acceptance runners or run migrations on normal settings.

Consolidated **database-free** repeat validation (unit/policy and frontend checks only, not an E2E/provisioning command):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_dic_phase4.ps1
```

No ready-to-run provisioning command is supplied while its required identity/role/isolation gates are unverified. No database connections, writes, creation, migrations, fixture imports/publication, backups, restores, provider calls, external email, credential edits, application feature changes, deployments or cleanup were performed. New artifacts are this report and the frontend validation log only.
